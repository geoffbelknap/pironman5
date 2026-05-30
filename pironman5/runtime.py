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
from .runtime_legacy import LegacyHardwareRuntime, LOCAL_PERIPHERALS, OLED_PAGE_PERIPHERALS
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
