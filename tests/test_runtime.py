import unittest
from unittest import mock


class RuntimeTest(unittest.TestCase):
    def test_legacy_hardware_runtime_does_not_enable_pm_auto_system_addon(self):
        from pironman5.runtime import LegacyHardwareRuntime

        with mock.patch("pironman5.runtime.Addons") as addons:
            LegacyHardwareRuntime(
                config={},
                peripherals=["cpu", "system", "gpio_fan_state"],
                device_info={},
                event=None,
                log=None,
            )

        kwargs = addons.call_args.kwargs
        self.assertEqual(["cpu", "gpio_fan_state"], kwargs["peripherals"])

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


if __name__ == "__main__":
    unittest.main()
