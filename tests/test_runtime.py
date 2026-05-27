import unittest
from unittest import mock


class RuntimeTest(unittest.TestCase):
    def test_legacy_hardware_runtime_does_not_enable_local_modules(self):
        from pironman5.runtime import LegacyHardwareRuntime

        with mock.patch("pironman5.runtime.Addons") as addons:
            LegacyHardwareRuntime(
                config={},
                peripherals=[
                    "cpu",
                    "system",
                    "gpio_fan_state",
                    "gpio_fan_led",
                    "pi5_power_button",
                    "ws2812",
                    "pwm_fan_speed",
                ],
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

    def test_pi5_power_button_module_publishes_button_events(self):
        from pironman5.runtime import ButtonStatus, EventBus, Pi5PowerButtonModule

        fake_button = mock.Mock()
        event = EventBus()
        published = []
        for name in (
            "pi5_power_button_click",
            "pi5_power_button_double_click",
            "pi5_power_button_long_press",
            "pi5_power_button_long_press_released",
        ):
            event.subscribe(name, lambda *args, _name=name: published.append((_name, args)))

        module = Pi5PowerButtonModule(event=event, button_factory=lambda: fake_button)
        callback = fake_button.set_button_callback.call_args.args[0]

        callback(ButtonStatus.CLICK)
        callback(ButtonStatus.DOUBLE_CLICK)
        callback(ButtonStatus.LONG_PRESS_2S)
        callback(ButtonStatus.LONG_PRESS_2S_RELEASED)

        self.assertEqual(
            [
                ("pi5_power_button_click", (ButtonStatus.CLICK,)),
                ("pi5_power_button_double_click", (ButtonStatus.DOUBLE_CLICK,)),
                ("pi5_power_button_long_press", ("button_long_press",)),
                ("pi5_power_button_long_press_released", ("button_long_press_released",)),
            ],
            published,
        )

    def test_runtime_starts_pi5_power_button_when_present(self):
        from pironman5.runtime import PironmanRuntime

        with mock.patch("pironman5.runtime.Pi5PowerButtonModule") as module:
            runtime = PironmanRuntime(
                config={},
                peripherals=["pi5_power_button"],
                device_info={},
                event_map={},
                log=None,
            )

        module.assert_called_once_with(event=runtime.event, log=runtime.log)

    def test_ws2812_config_update_keeps_compatible_patch_semantics(self):
        from pironman5.runtime import EventBus, WS2812Module

        module = WS2812Module(
            config={"rgb_led_count": 4, "rgb_led_count_min": 4},
            event=EventBus(),
            log=mock.Mock(),
            strip_factory=lambda _count: None,
        )

        patch = module.update_config(
            {
                "rgb_led_count": 2,
                "rgb_enable": False,
                "rgb_color": "#112233",
                "rgb_brightness": 25,
                "rgb_style": "rainbow",
                "rgb_speed": 75,
                "rgb_position": [3, 2],
            }
        )

        self.assertEqual(
            {
                "rgb_led_count": 4,
                "rgb_enable": False,
                "rgb_color": "#112233",
                "rgb_brightness": 25,
                "rgb_style": "rainbow",
                "rgb_speed": 75,
                "rgb_position": [3, 2, 0, 1],
            },
            patch,
        )

    def test_ws2812_solid_renders_brightness_adjusted_color(self):
        from pironman5.runtime import EventBus, WS2812Module

        strip = mock.Mock()
        module = WS2812Module(
            config={
                "rgb_led_count": 4,
                "rgb_enable": True,
                "rgb_color": "#204060",
                "rgb_brightness": 50,
                "rgb_style": "solid",
            },
            event=EventBus(),
            strip_factory=lambda _count: strip,
        )

        delay = module.render_once()

        strip.fill.assert_called_with((16, 32, 48))
        strip.show.assert_called_once()
        self.assertEqual(1, delay)

    def test_runtime_starts_ws2812_when_present(self):
        from pironman5.runtime import PironmanRuntime

        with mock.patch("pironman5.runtime.WS2812Module") as module:
            runtime = PironmanRuntime(
                config={},
                peripherals=["ws2812"],
                device_info={},
                event_map={},
                log=None,
            )

        module.assert_called_once_with(config={}, event=runtime.event, log=runtime.log)


if __name__ == "__main__":
    unittest.main()
