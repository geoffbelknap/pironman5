import asyncio
import glob
import logging
import re
import select
import threading
import time
from enum import IntEnum
from math import cos, pi
from os import path

from . import host

try:
    from pm_auto.addons import Addons
except ImportError:
    Addons = None


class TaskScheduler:
    def __init__(self):
        self.tasks = {}
        self._stop_event = asyncio.Event()

    async def run_once(self, func, delay=0):
        task_id = f"once-{len(self.tasks)}"

        async def _wrapper():
            await asyncio.sleep(delay)
            if not self._stop_event.is_set():
                func()
            self.tasks.pop(task_id, None)

        self.tasks[task_id] = asyncio.create_task(_wrapper())
        return task_id

    async def run_periodically(self, func, interval):
        task_id = f"periodic-{len(self.tasks)}"

        async def _wrapper():
            while not self._stop_event.is_set():
                func()
                await asyncio.sleep(interval)

        self.tasks[task_id] = asyncio.create_task(_wrapper())
        return task_id

    async def stop(self):
        self._stop_event.set()
        for task in self.tasks.values():
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()


class EventBus:
    def __init__(self, log=None):
        self.log = log or logging.getLogger(__name__)
        self.subscribers = {}

    def subscribe(self, event_name, callback):
        self.subscribers.setdefault(event_name, []).append(callback)

    def unsubscribe(self, event_name, callback):
        if event_name in self.subscribers:
            self.subscribers[event_name].remove(callback)

    def publish(self, event_name, *args, **kwargs):
        for callback in self.subscribers.get(event_name, []):
            callback(*args, **kwargs)

    def connect(self, pub_event_name, sub_event_name):
        def bridge(*args, **kwargs):
            self.publish(sub_event_name, *args, **kwargs)

        self.subscribe(pub_event_name, bridge)


FAN_LEVELS = [
    {"name": "OFF", "low": -200, "high": 55, "percent": 0},
    {"name": "LOW", "low": 45, "high": 65, "percent": 40},
    {"name": "MEDIUM", "low": 55, "high": 75, "percent": 80},
    {"name": "HIGH", "low": 65, "high": 100, "percent": 100},
]
GPIO_FAN_MODES = ["Always On", "Performance", "Cool", "Balanced", "Quiet"]
LOCAL_PERIPHERALS = {
    "system",
    "storage",
    "cpu",
    "network",
    "memory",
    "history",
    "log",
    "cpu_temperature",
    "gpu_temperature",
    "temperature_unit",
    "clear_history",
    "delete_log_file",
    "debug_level",
    "ip_address",
    "mac_address",
    "restart_service",
    "reboot",
    "shutdown",
    "gpio_fan",
    "gpio_fan_state",
    "gpio_fan_mode",
    "gpio_fan_led",
    "pi5_power_button",
    "ws2812",
    "pwm_fan_speed",
    "pwm_fan",
    "rtl8125",
}
RGB_STYLES = ["solid", "breathing", "flow", "flow_reverse", "rainbow", "rainbow_reverse", "hue_cycle"]


class ButtonStatus(IntEnum):
    RELEASED = 0
    PRESSED = 1
    CLICK = 2
    DOUBLE_CLICK = 3
    LONG_PRESS_2S = 4
    LONG_PRESS_2S_RELEASED = 5
    LONG_PRESS_5S = 6
    LONG_PRESS_5S_RELEASED = 7


def parse_input_devices(devices_text):
    device_blocks = re.split(r"\n(?=I: Bus=)", devices_text.strip())
    devices = {}
    for block in device_blocks:
        device_info = {}
        for line in [line.strip() for line in block.split("\n") if line.strip()]:
            match = re.match(r"^([A-Z]): (.*)$", line)
            if not match:
                continue
            key, value = match.groups()
            if key == "N":
                name_match = re.search(r'Name="([^"]+)"', value)
                if name_match:
                    device_info["name"] = name_match.group(1)
            elif key == "H":
                handlers_match = re.search(r"Handlers=(.*)", value)
                if handlers_match:
                    handlers = handlers_match.group(1).split()
                    device_info["handlers"] = handlers
                    for handler in handlers:
                        if handler.startswith("event"):
                            device_info["path"] = f"/dev/input/{handler}"
                            break
        if "name" in device_info:
            devices[device_info["name"]] = device_info
    return devices


def find_input_device_path(name, devices_file="/proc/bus/input/devices"):
    try:
        with open(devices_file, "r", encoding="utf-8") as f:
            devices = parse_input_devices(f.read())
    except OSError:
        return None
    return devices.get(name, {}).get("path")


class Pi5PowerButton:
    DOUBLE_CLICK_INTERVAL = 0.25
    READ_INTERVAL = 0.1

    def __init__(self, device_path=None, grab=True):
        from evdev import InputDevice, ecodes

        self.ecodes = ecodes
        self.event_code = ecodes.KEY_POWER
        device_path = device_path or find_input_device_path("pwr_button")
        if not device_path:
            raise RuntimeError("Power button device not found")
        self.dev = InputDevice(device_path)
        if grab:
            self.dev.grab()
        self.status = ButtonStatus.RELEASED
        self.last_key_down_time = 0
        self.last_key_up_time = 0
        self.is_pressed = False
        self.double_click_ready = False
        self.running = False
        self._watch_thread = None
        self._process_thread = None
        self._button_callback = None

    def set_button_callback(self, callback):
        self._button_callback = callback

    def start(self):
        self.running = True
        self._process_thread = threading.Thread(target=self.process_loop, daemon=True)
        self._process_thread.start()

    def stop(self):
        self.running = False
        try:
            self.dev.ungrab()
        except Exception:
            pass
        try:
            self.dev.close()
        except Exception:
            pass
        self._join_thread(self._watch_thread)
        self._join_thread(self._process_thread)

    def process_loop(self):
        self.start_watcher()
        while self.running:
            state = self.read()
            if self._button_callback is not None and state != ButtonStatus.RELEASED:
                self._button_callback(state)
            time.sleep(self.READ_INTERVAL)

    def start_watcher(self):
        if self._watch_thread is None or not self._watch_thread.is_alive():
            self._watch_thread = threading.Thread(target=self.watch_loop, daemon=True)
            self._watch_thread.start()

    def watch_loop(self):
        while self.running:
            try:
                if not self._device_ready(self.READ_INTERVAL):
                    continue
                event = self.dev.read_one()
                while event is not None:
                    self._handle_event(event)
                    event = self.dev.read_one()
            except (OSError, ValueError):
                if self.running:
                    raise
                break

    def _handle_event(self, event):
        if event.type != self.ecodes.EV_KEY or event.code != self.event_code:
            return
        event_time = event.timestamp()
        if event.value == 0:
            self.is_pressed = False
            self.last_key_up_time = time.time()
            if self.double_click_ready:
                self.status = ButtonStatus.DOUBLE_CLICK
                self.double_click_ready = False
                return
            interval = event_time - self.last_key_down_time
            if interval > 5:
                self.status = ButtonStatus.LONG_PRESS_5S_RELEASED
            elif interval > 2:
                self.status = ButtonStatus.LONG_PRESS_2S_RELEASED
            else:
                self.status = ButtonStatus.CLICK
        elif event.value == 1:
            self.is_pressed = True
            if event_time - self.last_key_down_time < self.DOUBLE_CLICK_INTERVAL:
                self.double_click_ready = True
            self.status = ButtonStatus.PRESSED
            self.last_key_down_time = event_time

    def read(self):
        status = self.status
        if self.is_pressed:
            if time.time() - self.last_key_down_time > 5:
                status = ButtonStatus.LONG_PRESS_5S
            elif time.time() - self.last_key_down_time > 2:
                status = ButtonStatus.LONG_PRESS_2S
        elif self.status == ButtonStatus.CLICK:
            if time.time() - self.last_key_up_time > self.DOUBLE_CLICK_INTERVAL:
                status = ButtonStatus.CLICK
                self.status = ButtonStatus.RELEASED
            else:
                status = ButtonStatus.RELEASED
        else:
            self.status = ButtonStatus.RELEASED
        return status

    def _join_thread(self, thread):
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=1)

    def _device_ready(self, timeout):
        return bool(select.select([self.dev.fd], [], [], timeout)[0])


class Pi5PowerButtonModule:
    def __init__(self, event, log=None, button_factory=None):
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.button = (button_factory or Pi5PowerButton)()
        self.button.set_button_callback(self.button_callback)

    def button_callback(self, state):
        if state == ButtonStatus.CLICK:
            self.event.publish("pi5_power_button_click", state)
        elif state == ButtonStatus.DOUBLE_CLICK:
            self.event.publish("pi5_power_button_double_click", state)
        elif state == ButtonStatus.LONG_PRESS_2S:
            self.event.publish("pi5_power_button_long_press", "button_long_press")
        elif state == ButtonStatus.LONG_PRESS_2S_RELEASED:
            self.event.publish("pi5_power_button_long_press_released", "button_long_press_released")

    async def start(self):
        self.button.start()

    async def stop(self):
        self.button.stop()


class GPIOOutputPin:
    def __init__(self, pin):
        from RPi import GPIO

        self.pin = pin
        self.gpio = GPIO
        self.gpio.setmode(self.gpio.BCM)
        self.gpio.setup(self.pin, self.gpio.OUT)
        self.set(False)

    def set(self, value):
        self.gpio.output(self.pin, bool(value))

    def close(self):
        self.set(False)
        self.gpio.cleanup(self.pin)

    @classmethod
    def cleanup_all(cls):
        import warnings
        from RPi import GPIO

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            GPIO.cleanup()
        cls._stop_lgpio_notify_thread()

    @classmethod
    def _stop_lgpio_notify_thread(cls):
        try:
            import lgpio

            notify_thread = getattr(lgpio, "_notify_thread", None)
            if notify_thread is None:
                return
            notify_thread.stop()
            notify_handle = getattr(notify_thread, "_notify", None)
            if notify_handle is not None:
                lgpio._notify_close(notify_handle)
            if notify_thread is not threading.current_thread() and notify_thread.is_alive():
                notify_thread.join(timeout=1)
        except Exception:
            pass


class GPIOFanModule:
    def __init__(self, config, event, log=None, pin_factory=None):
        self.config = dict(config or {})
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.pin_factory = pin_factory or GPIOOutputPin
        self.level = 0
        self.fan_pin = None
        self.led_pin = None
        self._configure_pins()

    def update_config(self, config):
        patch = {}
        if "gpio_fan_pin" in config:
            self.config["gpio_fan_pin"] = int(config["gpio_fan_pin"])
            patch["gpio_fan_pin"] = self.config["gpio_fan_pin"]
            self._replace_fan_pin()
        if "gpio_fan_mode" in config:
            mode = int(config["gpio_fan_mode"])
            if 0 <= mode < len(FAN_LEVELS):
                self.config["gpio_fan_mode"] = mode
                patch["gpio_fan_mode"] = mode
        if "gpio_fan_led_pin" in config:
            self.config["gpio_fan_led_pin"] = int(config["gpio_fan_led_pin"])
            patch["gpio_fan_led_pin"] = self.config["gpio_fan_led_pin"]
            self._replace_led_pin()
        if "gpio_fan_led" in config:
            led = str(config["gpio_fan_led"]).lower()
            if led in ("follow", "on", "off"):
                self.config["gpio_fan_led"] = led
                patch["gpio_fan_led"] = led
                self._set_led(None)
        return patch

    def task_1s(self):
        temperature = host.get_cpu_temperature()
        temperature = float(temperature) if temperature is not None else 0.0
        if temperature < FAN_LEVELS[self.level]["low"]:
            self.level -= 1
        elif temperature > FAN_LEVELS[self.level]["high"]:
            self.level += 1
        self.level = max(0, min(self.level, len(FAN_LEVELS) - 1))
        state = self.level >= self.config.get("gpio_fan_mode", 1)
        if self.fan_pin is not None:
            self.fan_pin.set(state)
        self._set_led(state)
        self.event.publish("data_changed", {"gpio_fan_state": state})

    async def start(self):
        self.tasks = TaskScheduler()
        await self.tasks.run_periodically(self.task_1s, 1)

    async def stop(self):
        if hasattr(self, "tasks"):
            await self.tasks.stop()
        for pin in (self.fan_pin, self.led_pin):
            if pin is not None:
                pin.close()
        if self.pin_factory is GPIOOutputPin:
            GPIOOutputPin.cleanup_all()

    def _configure_pins(self):
        self._replace_fan_pin()
        if "gpio_fan_led_pin" in self.config:
            self._replace_led_pin()
        self._set_led(None)

    def _replace_fan_pin(self):
        if self.fan_pin is not None:
            self.fan_pin.close()
        self.fan_pin = self.pin_factory(int(self.config.get("gpio_fan_pin", 6)))

    def _replace_led_pin(self):
        if self.led_pin is not None:
            self.led_pin.close()
        self.led_pin = self.pin_factory(int(self.config.get("gpio_fan_led_pin", 5)))

    def _set_led(self, fan_state):
        if self.led_pin is None:
            return
        mode = self.config.get("gpio_fan_led", "follow")
        if mode == "follow" and fan_state is not None:
            self.led_pin.set(fan_state)
        elif mode == "on":
            self.led_pin.set(True)
        elif mode == "off":
            self.led_pin.set(False)


def map_value(value, from_low, from_high, to_low, to_high):
    return (value - from_low) * (to_high - to_low) / (from_high - from_low) + to_low


class WS2812Strip:
    def __init__(self, led_count):
        if not path.exists("/dev/spidev0.0"):
            raise RuntimeError("SPI not enabled")
        import board
        import neopixel_spi as neopixel

        spi = board.SPI()
        self.strip = neopixel.NeoPixel_SPI(
            spi,
            led_count,
            pixel_order=neopixel.GRB,
            auto_write=False,
        )
        time.sleep(0.01)
        self.fill(0)
        self.show()

    def fill(self, color):
        self.strip.fill(color)

    def show(self):
        self.strip.show()

    def __setitem__(self, index, value):
        self.strip[index] = value


class WS2812Module:
    def __init__(self, config, event, log=None, strip_factory=None):
        self.config = dict(config or {})
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.strip_factory = strip_factory or WS2812Strip
        self.task = None
        self.strip = None
        self.counter = 0
        self.counter_max = 100
        self.position = []
        self.led_count = 4
        self.enable = True
        self.color = (0, 255, 255)
        self.brightness = 100
        self.style = "breathing"
        self.speed = 50
        self.update_config(
            {
                "rgb_led_count": self.config.get("rgb_led_count", 4),
                "rgb_enable": self.config.get("rgb_enable", True),
                "rgb_color": self.config.get("rgb_color", "#00ffff"),
                "rgb_brightness": self.config.get("rgb_brightness", 100),
                "rgb_style": self.config.get("rgb_style", "breathing"),
                "rgb_speed": self.config.get("rgb_speed", 50),
                "rgb_position": self.config.get("rgb_position", []),
            }
        )
        self._init_strip()

    def update_config(self, config):
        patch = {}
        if "rgb_led_count" in config:
            led_count = config["rgb_led_count"]
            if isinstance(led_count, int):
                minimum = self.config.get("rgb_led_count_min")
                if minimum is not None and led_count < minimum:
                    led_count = minimum
                    self.log.warning(f"rgb_led_count {led_count} too small, available led count: >= {minimum}")
                self.led_count = led_count
                self.config["rgb_led_count"] = led_count
                if not self.position:
                    self.position = list(range(self.led_count))
                patch["rgb_led_count"] = led_count
            else:
                self.log.error(f"Invalid rgb_led_count: {led_count}")
        if "rgb_enable" in config:
            enable = config["rgb_enable"]
            if isinstance(enable, bool):
                self.enable = enable
                self.config["rgb_enable"] = enable
                patch["rgb_enable"] = enable
            else:
                self.log.error(f"Invalid rgb_enable: {enable}")
        if "rgb_color" in config:
            color = config["rgb_color"]
            if isinstance(color, str):
                try:
                    self.color = self.hex_to_rgb(color)
                    self.config["rgb_color"] = color
                    patch["rgb_color"] = color
                except ValueError:
                    self.log.error(f"Invalid rgb_color: {color}")
            else:
                self.log.error(f"Invalid rgb_color: {color}")
        if "rgb_brightness" in config:
            brightness = config["rgb_brightness"]
            if isinstance(brightness, int):
                self.brightness = brightness
                self.config["rgb_brightness"] = brightness
                patch["rgb_brightness"] = brightness
            else:
                self.log.error(f"Invalid rgb_brightness: {brightness}")
        if "rgb_speed" in config:
            speed = config["rgb_speed"]
            if isinstance(speed, int):
                self.speed = speed
                self.config["rgb_speed"] = speed
                patch["rgb_speed"] = speed
            else:
                self.log.error(f"Invalid rgb_speed: {speed}")
        if "rgb_style" in config:
            style = config["rgb_style"]
            if isinstance(style, str) and style in RGB_STYLES:
                self.style = style
                self.config["rgb_style"] = style
                patch["rgb_style"] = style
            else:
                self.log.error(f"Invalid rgb_style: {style}")
        if "rgb_position" in config:
            position = config["rgb_position"]
            if isinstance(position, list):
                self.position = list(position)
                if len(position) != self.led_count:
                    self.position += [i for i in range(self.led_count) if i not in self.position]
                self.config["rgb_position"] = self.position
                patch["rgb_position"] = self.position
            else:
                self.log.error(f"Invalid rgb_position: {position}")
        return patch

    def render_once(self):
        if self.strip is None:
            return 1
        if not self.enable:
            self.clear()
            self.strip.show()
            return 1
        style_func = getattr(self, self.style)
        delay = style_func()
        self.counter += 1
        if self.counter >= self.counter_max:
            self.counter = 0
        return delay

    def clear(self):
        if self.strip is not None:
            self.strip.fill(0)

    async def start(self):
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        self.clear()
        if self.strip is not None:
            self.strip.show()

    async def _run(self):
        while True:
            try:
                delay = self.render_once()
            except Exception:
                self.log.exception("WS2812 service error")
                delay = 5
            await asyncio.sleep(delay)

    def solid(self):
        self.strip.fill(self._brightness_color(self.color))
        self.strip.show()
        return 1

    def breathing(self):
        self.counter_max = 200
        if self.counter >= self.counter_max:
            self.counter = 0
        delay = map_value(self.speed, 0, 100, 0.1, 0.001)
        color = self._brightness_color(self.color)
        level = self.counter if self.counter < 100 else 200 - self.counter
        self.strip.fill(tuple(int(x * level * 0.01) for x in color))
        self.strip.show()
        return delay

    def flow(self, reverse=False):
        self.counter_max = self.led_count
        if self.counter >= self.counter_max:
            self.counter = 0
        delay = map_value(self.speed, 0, 100, 0.5, 0.1)
        order = list(self.position)
        if reverse:
            order.reverse()
        self.strip.fill(0)
        self.strip[order[self.counter]] = self._brightness_color(self.color)
        self.strip.show()
        return delay

    def flow_reverse(self):
        return self.flow(reverse=True)

    def rainbow(self, reverse=False):
        self.counter_max = 360
        if self.counter >= self.counter_max:
            self.counter = 0
        delay = map_value(self.speed, 0, 100, 0.1, 0.005)
        pattern = self.create_rainbow_pattern(self.led_count, self.counter)
        order = list(self.position)
        if reverse:
            order.reverse()
        for i, led in enumerate(order):
            self.strip[led] = self.hsl_to_rgb(pattern[i], 1, self.brightness * 0.01)
        self.strip.show()
        return delay

    def rainbow_reverse(self):
        return self.rainbow(reverse=True)

    def hue_cycle(self):
        self.counter_max = 360
        if self.counter >= self.counter_max:
            self.counter = 0
        delay = map_value(self.speed, 0, 100, 0.1, 0.005)
        self.strip.fill(self.hsl_to_rgb(self.counter, 1, self.brightness * 0.01))
        self.strip.show()
        return delay

    def create_rainbow_pattern(self, num, offset=0):
        return [(i * 360.0 / num) + offset for i in range(num)]

    def create_gradient_pattern(self, num, offset=0):
        pattern = []
        for i in range(num):
            x = i / num * 2 * pi - pi
            pattern.append(int(cos(x + offset) * 50 + 50))
        return pattern

    def hsl_to_rgb(self, hue, saturation=1, brightness=1):
        hue = hue % 360
        hi = int((hue / 60) % 6)
        f = hue / 60.0 - hi
        p = brightness * (1 - saturation)
        q = brightness * (1 - f * saturation)
        t = brightness * (1 - (1 - f) * saturation)
        values = {
            0: (brightness, t, p),
            1: (q, brightness, p),
            2: (p, brightness, t),
            3: (p, q, brightness),
            4: (t, p, brightness),
            5: (brightness, p, q),
        }[hi]
        return tuple(int(value * 255) for value in values)

    def hex_to_rgb(self, value):
        value = value.strip().replace("#", "")
        if len(value) != 6:
            raise ValueError("RGB color must be six hex characters")
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))

    def _brightness_color(self, color):
        return tuple(int(value * self.brightness * 0.01) for value in color)

    def _init_strip(self):
        try:
            self.strip = self.strip_factory(self.led_count)
        except Exception as exc:
            self.log.error(f"Failed to initialize WS2812 service: {exc}")
            self.strip = None


class PWMFanDevice:
    TEMP_CONTROL_INTERVENE_OS = set()

    def __init__(
        self,
        thermal_glob=None,
        speed_glob=None,
        reader=None,
        writer=None,
        log=None,
    ):
        self.log = log or logging.getLogger(__name__)
        self.thermal_glob = thermal_glob or glob.glob
        self.speed_glob = speed_glob or glob.glob
        self.reader = reader or self._read_file
        self.writer = writer or self._write_file
        self.state_path = self._first_path("/sys/class/thermal/cooling_device*/cur_state")
        self.speed_path = self._first_path("/sys/devices/platform/cooling_fan/hwmon/*/fan1_input")
        self.ready = bool(self.state_path and self.speed_path)
        self.kernel_controlled = True

    def get_state(self):
        if not self.ready:
            return 0
        try:
            return int(self.reader(self.state_path).strip())
        except Exception as exc:
            self.log.error(f"read pwm fan state error: {exc}")
            return 0

    def set_state(self, level):
        if not self.ready:
            return
        level = max(0, min(3, int(level)))
        self.writer(self.state_path, f"{level}\n")

    def get_speed(self):
        if not self.ready:
            return 0
        try:
            return int(self.reader(self.speed_path).strip())
        except Exception as exc:
            self.log.error(f"read fan1 speed error: {exc}")
            return 0

    def close(self):
        if self.ready and not self.kernel_controlled:
            self.set_state(0)

    def _first_path(self, pattern):
        paths = self.thermal_glob(pattern) if "thermal" in pattern else self.speed_glob(pattern)
        return paths[0] if paths else None

    def _read_file(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def _write_file(self, file_path, value):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(value)


class PWMFanModule:
    def __init__(self, event, log=None, fan_factory=None):
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.fan = (fan_factory or (lambda: PWMFanDevice(log=self.log)))()
        self.level = 0
        self.tasks = TaskScheduler()
        if not self.fan.ready:
            self.log.warning("PWM Fan is not supported")

    def task_1s(self):
        data = {}
        if self.fan.ready and self.fan.kernel_controlled:
            data["pwm_fan_speed"] = self.fan.get_speed()
            data["pwm_fan_state"] = self.fan.get_state()
        elif self.fan.ready:
            self._set_fallback_level()
            self.fan.set_state(self.level)
            data["pwm_fan_speed"] = self.fan.get_speed()
            data["pwm_fan_state"] = self.level
        if data:
            self.event.publish("data_changed", data)

    async def start(self):
        await self.tasks.run_periodically(self.task_1s, 1)

    async def stop(self):
        await self.tasks.stop()
        self.fan.close()

    def _set_fallback_level(self):
        temperature = host.get_cpu_temperature()
        temperature = float(temperature) if temperature is not None else 0.0
        if temperature < FAN_LEVELS[self.level]["low"]:
            self.level -= 1
        elif temperature > FAN_LEVELS[self.level]["high"]:
            self.level += 1
        self.level = max(0, min(self.level, len(FAN_LEVELS) - 1))


class SystemStatusModule:
    def __init__(self, event, log=None):
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.tasks = TaskScheduler()
        self.disk_keys = []
        self.event.subscribe("shutdown", self._on_shutdown)
        self.event.subscribe("reboot", self._on_reboot)
        self.event.subscribe("restart_service", self._on_restart_service)

    def task_once(self):
        data = {"cpu_count": int(host.get_cpu_count() or 0)}
        for name, mac in host.get_macs().items():
            data[f"mac_{name}"] = mac
        self.event.publish("data_changed", data)

    def task_1s(self):
        data = {"boot_time": float(host.get_boot_time() or 0)}
        cpu_temperature = host.get_cpu_temperature()
        gpu_temperature = host.get_gpu_temperature()
        data["cpu_temperature"] = float(cpu_temperature) if cpu_temperature is not None else None
        data["gpu_temperature"] = float(gpu_temperature) if gpu_temperature is not None else None
        data["cpu_percent"] = float(host.get_cpu_percent())
        for i, percent in enumerate(host.get_cpu_percent(percpu=True)):
            data[f"cpu_{i}_percent"] = float(percent)

        cpu_freq = host.get_cpu_freq()
        data["cpu_freq"] = float(cpu_freq.current)
        data["cpu_freq_min"] = float(cpu_freq.min)
        data["cpu_freq_max"] = float(cpu_freq.max)

        memory = host.get_memory_info()
        data["memory_total"] = int(memory.total)
        data["memory_available"] = int(memory.available)
        data["memory_percent"] = float(memory.percent)
        data["memory_used"] = int(memory.used)

        network_speed = host.get_network_speed()
        data["network_upload_speed"] = int(network_speed.upload)
        data["network_download_speed"] = int(network_speed.download)
        self.event.publish("data_changed", data)

    def task_3s(self):
        data = {}
        ips = host.get_ips()
        data["ips"] = ips
        for name, values in ips.items():
            data[f"ip_{name}"] = values
        data["network_type"] = "&".join(host.get_network_connection_type())
        self.event.publish("data_changed", data)

    def task_5s(self):
        data = {"disk_list": host.get_disks()}
        disks = host.get_disks_info(temperature=True)
        data["disks"] = disks
        for disk_name, disk in disks.items():
            data[f"disk_{disk_name}_mounted"] = int(disk.mounted)
            data[f"disk_{disk_name}_total"] = int(disk.total)
            data[f"disk_{disk_name}_used"] = int(disk.used)
            data[f"disk_{disk_name}_free"] = int(disk.free)
            data[f"disk_{disk_name}_percent"] = float(disk.percent)
            if disk.temperature is not None:
                data[f"disk_{disk_name}_temperature"] = float(disk.temperature)

        keys = list(data.keys())
        delete_keys = [key for key in self.disk_keys if key not in keys]
        self.disk_keys = keys
        self.event.publish("data_changed", data, delete_keys=delete_keys)

    async def start(self):
        await self.tasks.run_once(self.task_once, 1)
        await self.tasks.run_periodically(self.task_1s, 1)
        await self.tasks.run_periodically(self.task_3s, 3)
        await self.tasks.run_periodically(self.task_5s, 5)

    async def stop(self):
        await self.tasks.stop()

    def _on_shutdown(self, reason=None):
        self.log.info(f"Shutdown reason: {reason}")
        self.event.publish("before_shutdown", reason)
        time.sleep(2)
        host.shutdown()

    def _on_reboot(self, *_args):
        host.reboot()

    def _on_restart_service(self, *_args):
        host.restart_service()


class LegacyHardwareRuntime:
    def __init__(self, config, peripherals, device_info, event, log=None):
        self.log = log or logging.getLogger(__name__)
        self.event = event or EventBus(log=self.log)
        self.peripherals = [peripheral for peripheral in peripherals if peripheral not in LOCAL_PERIPHERALS]
        self.addons = None
        if self.peripherals:
            if Addons is None:
                raise RuntimeError("pm_auto is required for legacy hardware modules")
            self.addons = Addons(
                peripherals=self.peripherals,
                config=config,
                device_info=device_info,
                event=self.event,
                log=self.log,
            )

    def update_config(self, config):
        if self.addons is None:
            return {}
        return self.addons.update_config(config)

    def test_smtp(self):
        if self.addons is None:
            return None
        return self.addons.pipower5.test_smtp()

    async def start(self):
        if self.addons is None:
            return
        await self.addons.start()

    async def stop(self):
        if self.addons is None:
            return
        await self.addons.stop()


class PironmanRuntime:
    def __init__(self, config, peripherals, device_info, event_map, log=None):
        self.log = log or logging.getLogger(__name__)
        self.event = EventBus(log=self.log)
        self.data = {}
        self.loop = None
        self.thread = None
        self.system = SystemStatusModule(event=self.event, log=self.log)
        self.gpio_fan = (
            GPIOFanModule(config=config, event=self.event, log=self.log)
            if any(peripheral in peripherals for peripheral in ("gpio_fan", "gpio_fan_state", "gpio_fan_led"))
            else None
        )
        self.pwm_fan = (
            PWMFanModule(event=self.event, log=self.log)
            if any(peripheral in peripherals for peripheral in ("pwm_fan_speed", "pwm_fan"))
            else None
        )
        self.pi5_power_button = (
            Pi5PowerButtonModule(event=self.event, log=self.log)
            if "pi5_power_button" in peripherals
            else None
        )
        self.ws2812 = (
            WS2812Module(config=config, event=self.event, log=self.log)
            if "ws2812" in peripherals
            else None
        )
        self.hardware = LegacyHardwareRuntime(
            config=config,
            peripherals=peripherals,
            device_info=device_info,
            event=self.event,
            log=self.log,
        )
        for pub_event_name, sub_event_name in (event_map or {}).items():
            self.event.connect(pub_event_name, sub_event_name)
        self.event.subscribe("data_changed", self.handle_data_changed)

    def handle_data_changed(self, data, delete_keys=None):
        for key in delete_keys or []:
            self.data.pop(key, None)
        self.data.update(data)

    def read(self):
        return self.data

    def update_config(self, config):
        patch = {}
        if self.gpio_fan is not None:
            patch.update(self.gpio_fan.update_config(config))
        if self.ws2812 is not None:
            patch.update(self.ws2812.update_config(config))
        patch.update(self.hardware.update_config(config))
        return patch

    def test_smtp(self):
        return self.hardware.test_smtp()

    def start(self):
        def run_event_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._start())
            self.loop.run_forever()
            self.loop.run_until_complete(self._stop())
            self.loop.close()

        self.thread = threading.Thread(target=run_event_loop, daemon=True)
        self.thread.start()

    def stop(self):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread and self.thread.is_alive():
            self.thread.join()

    async def _start(self):
        await self.system.start()
        if self.gpio_fan is not None:
            await self.gpio_fan.start()
        if self.pwm_fan is not None:
            await self.pwm_fan.start()
        if self.pi5_power_button is not None:
            await self.pi5_power_button.start()
        if self.ws2812 is not None:
            await self.ws2812.start()
        await self.hardware.start()

    async def _stop(self):
        await self.hardware.stop()
        if self.ws2812 is not None:
            await self.ws2812.stop()
        if self.pi5_power_button is not None:
            await self.pi5_power_button.stop()
        if self.pwm_fan is not None:
            await self.pwm_fan.stop()
        if self.gpio_fan is not None:
            await self.gpio_fan.stop()
        await self.system.stop()
