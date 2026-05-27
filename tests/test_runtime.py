import unittest
from unittest import mock


class RuntimeTest(unittest.TestCase):
    def test_legacy_hardware_runtime_does_not_enable_local_modules(self):
        from pironman5.runtime import LegacyHardwareRuntime

        with mock.patch("pironman5.runtime.Addons") as addons:
            LegacyHardwareRuntime(
                config={},
                peripherals=["cpu", "system", "gpio_fan_state", "gpio_fan_led", "pwm_fan_speed"],
                device_info={},
                event=None,
                log=None,
            )

        kwargs = addons.call_args.kwargs
        self.assertEqual(["cpu", "pwm_fan_speed"], kwargs["peripherals"])

    def test_runtime_connects_event_map_once_on_shared_event_bus(self):
        from pironman5.runtime import PironmanRuntime

        runtime = PironmanRuntime(
            config={},
            peripherals=[],
            device_info={},
            event_map={"button": "shutdown"},
            log=None,
        )

        self.assertIn("button", runtime.event.subscribers)

    def test_runtime_aggregates_data_changed_events(self):
        from pironman5.runtime import PironmanRuntime

        runtime = PironmanRuntime(config={}, peripherals=[], device_info={}, event_map={}, log=None)
        runtime.event.publish("data_changed", {"cpu_count": 4})

        self.assertEqual(4, runtime.read()["cpu_count"])

    def test_system_module_publishes_host_status(self):
        from pironman5.runtime import EventBus, SystemStatusModule

        event = EventBus()
        data = {}
        event.subscribe("data_changed", data.update)
        module = SystemStatusModule(event=event)

        with mock.patch("pironman5.runtime.host.get_cpu_count", return_value=4):
            module.task_once()

        self.assertEqual(4, data["cpu_count"])

    def test_gpio_fan_module_sets_pin_from_temperature(self):
        from pironman5.runtime import EventBus, GPIOFanModule

        fan_pin = mock.Mock()
        event = EventBus()
        data = {}
        event.subscribe("data_changed", data.update)
        module = GPIOFanModule(
            config={"gpio_fan_pin": 6, "gpio_fan_mode": 1},
            event=event,
            pin_factory=lambda _pin: fan_pin,
        )

        with mock.patch("pironman5.runtime.host.get_cpu_temperature", return_value=70):
            module.task_1s()

        fan_pin.set.assert_called_with(True)
        self.assertTrue(data["gpio_fan_state"])

    def test_gpio_fan_led_can_follow_fan_state(self):
        from pironman5.runtime import EventBus, GPIOFanModule

        pins = {}
        module = GPIOFanModule(
            config={
                "gpio_fan_pin": 6,
                "gpio_fan_led_pin": 5,
                "gpio_fan_led": "follow",
                "gpio_fan_mode": 1,
            },
            event=EventBus(),
            pin_factory=lambda pin: pins.setdefault(pin, mock.Mock()),
        )

        with mock.patch("pironman5.runtime.host.get_cpu_temperature", return_value=70):
            module.task_1s()

        pins[6].set.assert_called_with(True)
        pins[5].set.assert_called_with(True)

    def test_gpio_fan_config_update_changes_pin_and_led_mode(self):
        from pironman5.runtime import EventBus, GPIOFanModule

        module = GPIOFanModule(
            config={"gpio_fan_pin": 6, "gpio_fan_led_pin": 5, "gpio_fan_led": "off"},
            event=EventBus(),
            pin_factory=lambda _pin: mock.Mock(),
        )

        patch = module.update_config({"gpio_fan_pin": 13, "gpio_fan_led": "on"})

        self.assertEqual({"gpio_fan_pin": 13, "gpio_fan_led": "on"}, patch)


if __name__ == "__main__":
    unittest.main()
