import asyncio
import logging
import re
import select
import threading
import time
from enum import IntEnum

from .runtime_core import EventBus, TaskScheduler
from .runtime_fan import GPIO_FAN_MODES, FAN_LEVELS, GPIOFanModule, GPIOOutputPin, PWMFanDevice, PWMFanModule
from .runtime_oled import OLEDModule, SSD1306TextDisplay
from .runtime_rgb import (
    RGB_AMBIENT_PROFILES,
    RGB_MODES,
    RGB_STATUS_PROFILES,
    RGB_STYLES,
    WS2812Module,
    WS2812Strip,
    map_value,
)
from .runtime_status import SystemStatusModule

try:
    from pm_auto.addons import Addons
except ImportError:
    Addons = None


OLED_PAGE_PERIPHERALS = {
    "oled_page_battery",
    "oled_page_disk",
    "oled_page_input",
    "oled_page_ips",
    "oled_page_mix",
    "oled_page_performance",
    "oled_page_rpi_power",
}
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
    "vibration_switch",
    "pironman_mcu",
    "oled",
    "oled_sleep",
    *OLED_PAGE_PERIPHERALS,
}
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


class PironmanMcuRegister(IntEnum):
    FIRMWARE_VERSION = 0x00
    DEFAULT_ON = 0x01
    PWR_BTN = 0x02
    SHUTDOWN_REQ = 0x03


class PironmanMcuButtonStatus(IntEnum):
    RELEASED = 0
    CLICK = 1
    DOUBLE_CLICK = 2
    LONG_PRESS_2S = 3
    LONG_PRESS_2S_RELEASED = 4
    LONG_PRESS_5S = 5
    LONG_PRESS_5S_RELEASED = 6


class PironmanMcuDevice:
    I2C_ADDRESSES = (0x6A,)

    def __init__(self, bus=1, bus_factory=None, scanner=None):
        from smbus2 import SMBus

        self.bus_number = bus
        self.bus_factory = bus_factory or SMBus
        self.scanner = scanner or self.scan
        self.address = self._detect_address()
        self.bus = self.bus_factory(self.bus_number)

    def _detect_address(self):
        addresses = self.scanner(self.bus_number)
        for address in addresses:
            if address in self.I2C_ADDRESSES:
                return address
        expected = ", ".join(f"0x{address:02X}" for address in self.I2C_ADDRESSES)
        raise OSError(f"Pironman MCU I2C address not found in [{expected}]")

    def scan(self, bus):
        devices = []
        for address in range(0x03, 0x78):
            try:
                with self.bus_factory(bus) as smbus:
                    smbus.write_quick(address)
                    devices.append(address)
            except OSError:
                continue
        return devices

    def get_firmware_version(self):
        data = self.bus.read_i2c_block_data(self.address, PironmanMcuRegister.FIRMWARE_VERSION, 1)[0]
        major = data >> 6 & 0x03
        minor = data >> 3 & 0x07
        patch = data & 0x07
        return major, minor, patch

    def get_button(self):
        data = self.bus.read_i2c_block_data(self.address, PironmanMcuRegister.PWR_BTN, 1)[0]
        self.bus.write_byte_data(self.address, PironmanMcuRegister.PWR_BTN, 0)
        return PironmanMcuButtonStatus(data)

    def close(self):
        close = getattr(self.bus, "close", None)
        if close is not None:
            close()


class PironmanMcuModule:
    INTERVAL = 0.1

    def __init__(self, event, log=None, mcu_factory=None):
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.mcu = (mcu_factory or PironmanMcuDevice)()
        self.tasks = TaskScheduler()

    def poll_once(self):
        try:
            mcu_button = self.mcu.get_button()
        except ValueError as exc:
            self.log.warning("Unknown Pironman MCU button status: %s", exc)
            return
        if mcu_button == PironmanMcuButtonStatus.CLICK:
            self.event.publish("pironman_mcu_button_click")
        elif mcu_button == PironmanMcuButtonStatus.DOUBLE_CLICK:
            self.event.publish("pironman_mcu_button_double_click")
        elif mcu_button == PironmanMcuButtonStatus.LONG_PRESS_2S:
            self.event.publish("pironman_mcu_button_long_press", "button_long_press")
        elif mcu_button == PironmanMcuButtonStatus.LONG_PRESS_2S_RELEASED:
            self.event.publish("pironman_mcu_button_long_press_released", "button_long_press_released")

    async def start(self):
        await self.tasks.run_periodically(self.poll_once, self.INTERVAL)

    async def stop(self):
        await self.tasks.stop()
        self.mcu.close()


class GPIODigitalInputDevice:
    def __init__(self, pin=None, pull_up=True):
        from RPi import GPIO

        self.gpio = GPIO
        self.pin = None
        self.callback = None
        self.gpio.setmode(self.gpio.BCM)
        if pin is not None:
            self.configure(pin, pull_up)

    def configure(self, pin, pull_up=True):
        if self.pin is not None:
            self.close()
        self.pin = int(pin)
        pull = self.gpio.PUD_UP if pull_up else self.gpio.PUD_DOWN
        self.gpio.setup(self.pin, self.gpio.IN, pull_up_down=pull)
        self.gpio.add_event_detect(self.pin, self.gpio.RISING, callback=self._handle_activation, bouncetime=200)

    def set_activation_callback(self, callback):
        self.callback = callback

    def _handle_activation(self, _pin):
        if self.callback is not None:
            self.callback()

    def close(self):
        if self.pin is None:
            return
        try:
            self.gpio.remove_event_detect(self.pin)
        except Exception:
            pass
        self.gpio.cleanup(self.pin)
        self.pin = None


class VibrationSwitchModule:
    def __init__(self, config, event, log=None, device_factory=None):
        self.config = dict(config or {})
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.device = (device_factory or GPIODigitalInputDevice)(None, self.config.get("vibration_switch_pull_up", True))
        self.device.set_activation_callback(self.when_activated)
        if self.config.get("vibration_switch_pin") is not None:
            self.device.configure(
                int(self.config["vibration_switch_pin"]),
                bool(self.config.get("vibration_switch_pull_up", True)),
            )

    def when_activated(self):
        self.event.publish("vibration_detected")

    def update_config(self, config):
        patch = {}
        if "vibration_switch_pin" in config:
            patch["vibration_switch_pin"] = int(config["vibration_switch_pin"])
        if "vibration_switch_pull_up" in config:
            patch["vibration_switch_pull_up"] = bool(config["vibration_switch_pull_up"])
        if not patch:
            return {}
        self.config.update(patch)
        if self.config.get("vibration_switch_pin") is not None:
            self.device.configure(
                int(self.config["vibration_switch_pin"]),
                bool(self.config.get("vibration_switch_pull_up", True)),
            )
        return patch

    async def start(self):
        return

    async def stop(self):
        self.device.close()


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
        self.vibration_switch = (
            VibrationSwitchModule(config=config, event=self.event, log=self.log)
            if "vibration_switch" in peripherals
            else None
        )
        self.pironman_mcu = (
            PironmanMcuModule(event=self.event, log=self.log)
            if "pironman_mcu" in peripherals
            else None
        )
        self.oled = (
            OLEDModule(config=config, peripherals=peripherals, event=self.event, log=self.log)
            if "oled" in peripherals
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
        if self.vibration_switch is not None:
            patch.update(self.vibration_switch.update_config(config))
        if self.oled is not None:
            patch.update(self.oled.update_config(config))
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
        if self.vibration_switch is not None:
            await self.vibration_switch.start()
        if self.pironman_mcu is not None:
            await self.pironman_mcu.start()
        if self.oled is not None:
            await self.oled.start()
        await self.hardware.start()

    async def _stop(self):
        await self.hardware.stop()
        if self.oled is not None:
            await self.oled.stop()
        if self.pironman_mcu is not None:
            await self.pironman_mcu.stop()
        if self.vibration_switch is not None:
            await self.vibration_switch.stop()
        if self.ws2812 is not None:
            await self.ws2812.stop()
        if self.pi5_power_button is not None:
            await self.pi5_power_button.stop()
        if self.pwm_fan is not None:
            await self.pwm_fan.stop()
        if self.gpio_fan is not None:
            await self.gpio_fan.stop()
        await self.system.stop()
