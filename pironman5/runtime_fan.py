import glob
import logging
import threading

from . import host
from .runtime_core import TaskScheduler


FAN_LEVELS = [
    {"name": "OFF", "low": -200, "high": 55, "percent": 0},
    {"name": "LOW", "low": 45, "high": 65, "percent": 40},
    {"name": "MEDIUM", "low": 55, "high": 75, "percent": 80},
    {"name": "HIGH", "low": 65, "high": 100, "percent": 100},
]
GPIO_FAN_MODES = ["Always On", "Performance", "Cool", "Balanced", "Quiet"]


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
