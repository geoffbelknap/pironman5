import logging

from .runtime_core import EventBus

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
LOCAL_RUNTIME_PERIPHERALS = {
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


class OptionalBridgeRuntime:
    def __init__(self, config, peripherals, device_info, event, log=None):
        self.log = log or logging.getLogger(__name__)
        self.event = event or EventBus(log=self.log)
        self.peripherals = [peripheral for peripheral in peripherals if peripheral not in LOCAL_RUNTIME_PERIPHERALS]
        self.addons = None
        if self.peripherals:
            if Addons is None:
                raise RuntimeError("pm_auto is required for optional bridge modules")
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
