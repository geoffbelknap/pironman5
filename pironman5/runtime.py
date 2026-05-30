import asyncio
import logging
import threading

from .runtime_core import EventBus, TaskScheduler
from .runtime_fan import GPIO_FAN_MODES, FAN_LEVELS, GPIOFanModule, GPIOOutputPin, PWMFanDevice, PWMFanModule
from .runtime_input import (
    ButtonStatus,
    GPIODigitalInputDevice,
    Pi5PowerButton,
    Pi5PowerButtonModule,
    PironmanMcuButtonStatus,
    PironmanMcuDevice,
    PironmanMcuModule,
    PironmanMcuRegister,
    VibrationSwitchModule,
    find_input_device_path,
    parse_input_devices,
)
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
