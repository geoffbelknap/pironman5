import unittest
import time
from unittest import mock


class PironmanServiceTest(unittest.TestCase):
    def test_reload_config_applies_file_without_restarting_runtime(self):
        with mock.patch("logging.handlers.RotatingFileHandler"):
            from pironman5.pironman5 import Pironman5

        service = Pironman5.__new__(Pironman5)
        service.config_path = "/tmp/config.json"
        service.config = {"system": {"debug_level": "INFO", "rgb_brightness": 20}}
        service.upgrade_config = lambda config: config
        service.update_config = mock.Mock()
        service.log = mock.Mock()

        with mock.patch("pironman5.pironman5.load_config_file", return_value={"system": {"debug_level": "DEBUG", "rgb_brightness": 40}}):
            service.reload_config()

        service.update_config.assert_called_once_with({"system": {"debug_level": "DEBUG", "rgb_brightness": 40}})
        service.log.info.assert_any_call("Reloading config")


class RuntimeCoreTest(unittest.TestCase):
    def test_event_bus_bridges_connected_events(self):
        from pironman5.runtime_core import EventBus

        event = EventBus()
        received = []
        event.subscribe("target", lambda value=None: received.append(value))
        event.connect("source", "target")

        event.publish("source", "ok")

        self.assertEqual(["ok"], received)


class RuntimeStatusTest(unittest.TestCase):
    def test_system_status_module_imports_from_status_module(self):
        from pironman5.runtime_status import SystemStatusModule

        self.assertEqual("SystemStatusModule", SystemStatusModule.__name__)


class RuntimeFanTest(unittest.TestCase):
    def test_fan_modules_import_from_fan_module(self):
        from pironman5.runtime_fan import GPIOFanModule, PWMFanModule

        self.assertEqual("GPIOFanModule", GPIOFanModule.__name__)
        self.assertEqual("PWMFanModule", PWMFanModule.__name__)


class RuntimeOledTest(unittest.TestCase):
    def test_oled_module_imports_from_oled_module(self):
        from pironman5.runtime_oled import OLEDModule

        self.assertEqual("OLEDModule", OLEDModule.__name__)


class RuntimeRgbTest(unittest.TestCase):
    def test_ws2812_module_imports_from_rgb_module(self):
        from pironman5.runtime_rgb import WS2812Module

        self.assertEqual("WS2812Module", WS2812Module.__name__)


class RuntimeTest(unittest.TestCase):
    def test_legacy_hardware_runtime_does_not_enable_local_modules(self):
        from pironman5.runtime import LegacyHardwareRuntime

        with mock.patch("pironman5.runtime.Addons") as addons:
            LegacyHardwareRuntime(
                config={},
                peripherals=[
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
                    "system",
                    "gpio_fan_state",
                    "gpio_fan_mode",
                    "gpio_fan_led",
                    "pi5_power_button",
                    "ws2812",
                    "pwm_fan_speed",
                ],
                device_info={},
                event=None,
                log=None,
            )

        addons.assert_not_called()

    def test_legacy_hardware_runtime_allows_local_modules_without_pm_auto(self):
        from pironman5.runtime import LegacyHardwareRuntime

        with mock.patch("pironman5.runtime.Addons", None):
            runtime = LegacyHardwareRuntime(
                config={},
                peripherals=[
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
                    "system",
                    "gpio_fan_state",
                    "gpio_fan_mode",
                    "gpio_fan_led",
                    "pi5_power_button",
                    "ws2812",
                    "pwm_fan_speed",
                ],
                device_info={},
                event=None,
                log=None,
            )

        self.assertEqual([], runtime.peripherals)

    def test_legacy_hardware_runtime_treats_rtl8125_as_local_setup_only(self):
        from pironman5.runtime import LegacyHardwareRuntime

        with mock.patch("pironman5.runtime.Addons", None):
            runtime = LegacyHardwareRuntime(
                config={},
                peripherals=["rtl8125"],
                device_info={},
                event=None,
                log=None,
            )

        self.assertEqual([], runtime.peripherals)

    def test_legacy_hardware_runtime_treats_vibration_switch_as_local(self):
        from pironman5.runtime import LegacyHardwareRuntime

        with mock.patch("pironman5.runtime.Addons", None):
            runtime = LegacyHardwareRuntime(
                config={},
                peripherals=["vibration_switch"],
                device_info={},
                event=None,
                log=None,
            )

        self.assertEqual([], runtime.peripherals)

    def test_legacy_hardware_runtime_treats_oled_as_local(self):
        from pironman5.runtime import LegacyHardwareRuntime

        with mock.patch("pironman5.runtime.Addons", None):
            runtime = LegacyHardwareRuntime(
                config={},
                peripherals=["oled", "oled_sleep", "oled_page_mix", "oled_page_performance"],
                device_info={},
                event=None,
                log=None,
            )

        self.assertEqual([], runtime.peripherals)

    def test_legacy_hardware_runtime_treats_pironman_mcu_as_local(self):
        from pironman5.runtime import LegacyHardwareRuntime

        with mock.patch("pironman5.runtime.Addons", None):
            runtime = LegacyHardwareRuntime(
                config={},
                peripherals=["pironman_mcu"],
                device_info={},
                event=None,
                log=None,
            )

        self.assertEqual([], runtime.peripherals)

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
        from pironman5.runtime_core import EventBus
        from pironman5.runtime_status import SystemStatusModule

        event = EventBus()
        data = {}
        event.subscribe("data_changed", data.update)
        module = SystemStatusModule(event=event)

        with mock.patch("pironman5.runtime_status.host.get_cpu_count", return_value=4):
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

        with mock.patch("pironman5.runtime_fan.host.get_cpu_temperature", return_value=70):
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

        with mock.patch("pironman5.runtime_fan.host.get_cpu_temperature", return_value=70):
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

    def test_gpio_fan_stop_closes_lgpio_chip(self):
        from pironman5.runtime import EventBus, GPIOFanModule, GPIOOutputPin

        with mock.patch.object(GPIOOutputPin, "__init__", return_value=None), \
                mock.patch.object(GPIOOutputPin, "set"), \
                mock.patch.object(GPIOOutputPin, "close"), \
                mock.patch.object(GPIOOutputPin, "cleanup_all") as cleanup_all:
            module = GPIOFanModule(
                config={"gpio_fan_pin": 6, "gpio_fan_led_pin": 5},
                event=EventBus(),
            )

            import asyncio
            asyncio.run(module.stop())

        cleanup_all.assert_called_once()

    def test_gpio_cleanup_stops_lgpio_notify_thread(self):
        from pironman5.runtime import GPIOOutputPin

        notify_thread = mock.Mock()
        notify_thread._notify = 5
        notify_thread.is_alive.return_value = True
        with mock.patch.dict("sys.modules", {"lgpio": mock.Mock(_notify_thread=notify_thread)}):
            import lgpio

            GPIOOutputPin._stop_lgpio_notify_thread()

        notify_thread.stop.assert_called_once()
        lgpio._notify_close.assert_called_once_with(5)
        notify_thread.join.assert_called_once_with(timeout=1)

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

    def test_pironman_mcu_module_publishes_button_events(self):
        from pironman5.runtime import EventBus, PironmanMcuButtonStatus, PironmanMcuModule

        fake_mcu = mock.Mock()
        fake_mcu.get_button.side_effect = [
            PironmanMcuButtonStatus.CLICK,
            PironmanMcuButtonStatus.DOUBLE_CLICK,
            PironmanMcuButtonStatus.LONG_PRESS_2S,
            PironmanMcuButtonStatus.LONG_PRESS_2S_RELEASED,
            PironmanMcuButtonStatus.RELEASED,
        ]
        event = EventBus()
        published = []
        for name in (
            "pironman_mcu_button_click",
            "pironman_mcu_button_double_click",
            "pironman_mcu_button_long_press",
            "pironman_mcu_button_long_press_released",
        ):
            event.subscribe(name, lambda *args, _name=name: published.append((_name, args)))

        module = PironmanMcuModule(event=event, mcu_factory=lambda: fake_mcu)
        for _ in range(5):
            module.poll_once()

        self.assertEqual(
            [
                ("pironman_mcu_button_click", ()),
                ("pironman_mcu_button_double_click", ()),
                ("pironman_mcu_button_long_press", ("button_long_press",)),
                ("pironman_mcu_button_long_press_released", ("button_long_press_released",)),
            ],
            published,
        )

    def test_pironman_mcu_device_reads_and_clears_button_register(self):
        from pironman5.runtime import PironmanMcuButtonStatus, PironmanMcuDevice

        bus = mock.Mock()
        bus.read_i2c_block_data.return_value = [PironmanMcuButtonStatus.DOUBLE_CLICK]

        device = PironmanMcuDevice(bus_factory=lambda _bus: bus, scanner=lambda _bus: [0x6A])

        self.assertEqual(PironmanMcuButtonStatus.DOUBLE_CLICK, device.get_button())
        bus.read_i2c_block_data.assert_called_once_with(0x6A, 0x02, 1)
        bus.write_byte_data.assert_called_once_with(0x6A, 0x02, 0)

    def test_vibration_switch_module_publishes_activation_event(self):
        from pironman5.runtime import EventBus, VibrationSwitchModule

        fake_device = mock.Mock()
        event = EventBus()
        published = []
        event.subscribe("vibration_detected", lambda *args: published.append(args))

        module = VibrationSwitchModule(
            config={"vibration_switch_pin": 17, "vibration_switch_pull_up": False},
            event=event,
            device_factory=lambda pin, pull_up: fake_device,
        )
        callback = fake_device.set_activation_callback.call_args.args[0]

        callback()

        self.assertEqual([()], published)
        fake_device.configure.assert_called_once_with(17, False)

    def test_vibration_switch_config_update_reconfigures_device(self):
        from pironman5.runtime import EventBus, VibrationSwitchModule

        fake_device = mock.Mock()
        module = VibrationSwitchModule(
            config={},
            event=EventBus(),
            device_factory=lambda pin, pull_up: fake_device,
        )

        patch = module.update_config({"vibration_switch_pin": 22, "vibration_switch_pull_up": True})

        self.assertEqual({"vibration_switch_pin": 22, "vibration_switch_pull_up": True}, patch)
        fake_device.configure.assert_called_once_with(22, True)

    def test_oled_module_tracks_data_and_pages(self):
        from pironman5.runtime import EventBus, OLEDModule

        fake_display = mock.Mock()
        event = EventBus()
        module = OLEDModule(
            config={"oled_pages": ["mix", "performance"], "oled_sleep_timeout": 10},
            peripherals=["oled", "oled_page_mix", "oled_page_performance"],
            event=event,
            display_factory=lambda rotation: fake_display,
        )

        event.publish("data_changed", {"cpu_percent": 12.5, "memory_percent": 34.5})
        module.render_once()
        event.publish("oled_wake_page_next")
        module.render_once()

        self.assertEqual({"cpu_percent": 12.5, "memory_percent": 34.5}, module.data)
        self.assertEqual(1, module.page_index)
        self.assertGreaterEqual(fake_display.draw_text.call_count, 2)

    def test_oled_config_update_validates_pages_and_rotation(self):
        from pironman5.runtime import EventBus, OLEDModule

        fake_display = mock.Mock()
        module = OLEDModule(
            config={},
            peripherals=["oled", "oled_page_mix"],
            event=EventBus(),
            display_factory=lambda rotation: fake_display,
        )

        patch = module.update_config({
            "oled_rotation": 180,
            "oled_sleep_timeout": 99999,
            "oled_pages": ["mix", "missing", "mix"],
        })

        self.assertEqual({"oled_rotation": 180, "oled_sleep_timeout": 3600, "oled_pages": ["mix"]}, patch)
        fake_display.set_rotation.assert_called_once_with(180)

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

    def test_pi5_power_button_stop_joins_worker_threads(self):
        from pironman5.runtime import ButtonStatus, Pi5PowerButton

        class FakeDevice:
            def __init__(self):
                self.closed = False

            def read_loop(self):
                while not self.closed:
                    time.sleep(0.01)
                    if False:
                        yield None

            def read_one(self):
                return None

            def ungrab(self):
                pass

            def close(self):
                self.closed = True

        button = Pi5PowerButton.__new__(Pi5PowerButton)
        button.ecodes = mock.Mock(EV_KEY=1)
        button.event_code = 116
        button.dev = FakeDevice()
        button.status = ButtonStatus.RELEASED
        button.last_key_down_time = 0
        button.last_key_up_time = 0
        button.is_pressed = False
        button.double_click_ready = False
        button.running = False
        button._watch_thread = None
        button._process_thread = None
        button._button_callback = None
        button._device_ready = lambda _timeout: False

        button.start()
        deadline = time.time() + 1
        while button._watch_thread is None and time.time() < deadline:
            time.sleep(0.01)

        button.stop()

        self.assertFalse(button._process_thread.is_alive())
        self.assertFalse(button._watch_thread.is_alive())

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

    def test_ws2812_status_thermal_renders_whole_case_temperature_color(self):
        from pironman5.runtime import EventBus, WS2812Module

        event = EventBus()
        strip = mock.Mock()
        module = WS2812Module(
            config={
                "rgb_led_count": 4,
                "rgb_enable": True,
                "rgb_mode": "status",
                "rgb_profile": "thermal",
                "rgb_brightness": 40,
            },
            event=event,
            strip_factory=lambda _count: strip,
        )

        event.publish("data_changed", {"cpu_temperature": 72.0})
        delay = module.render_once()

        strip.fill.assert_called_with((102, 0, 0))
        strip.show.assert_called()
        self.assertEqual(1, delay)

    def test_ws2812_night_schedule_dims_current_mode(self):
        from datetime import time as datetime_time
        from pironman5.runtime import EventBus, WS2812Module

        strip = mock.Mock()
        module = WS2812Module(
            config={
                "rgb_led_count": 4,
                "rgb_enable": True,
                "rgb_color": "#ffffff",
                "rgb_brightness": 80,
                "rgb_style": "solid",
                "rgb_night_brightness": 10,
                "rgb_night_start": "22:00",
                "rgb_night_end": "07:00",
            },
            event=EventBus(),
            strip_factory=lambda _count: strip,
            now_fn=lambda: datetime_time(23, 30),
        )

        module.render_once()

        strip.fill.assert_called_with((25, 25, 25))

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

    def test_pwm_fan_device_reads_state_and_speed_from_sysfs(self):
        from pironman5.runtime import PWMFanDevice

        files = {
            "/thermal/cooling_device0/cur_state": "2\n",
            "/cooling_fan/hwmon/hwmon3/fan1_input": "2500\n",
        }

        device = PWMFanDevice(
            thermal_glob=lambda _pattern: ["/thermal/cooling_device0/cur_state"],
            speed_glob=lambda _pattern: ["/cooling_fan/hwmon/hwmon3/fan1_input"],
            reader=lambda path: files[path],
        )

        self.assertTrue(device.ready)
        self.assertEqual(2, device.get_state())
        self.assertEqual(2500, device.get_speed())

    def test_pwm_fan_module_publishes_speed_and_state(self):
        from pironman5.runtime import EventBus, PWMFanModule

        class FakePWMFan:
            ready = True
            kernel_controlled = True

            def get_speed(self):
                return 2100

            def get_state(self):
                return 1

            def close(self):
                pass

        event = EventBus()
        data = {}
        event.subscribe("data_changed", data.update)
        module = PWMFanModule(event=event, fan_factory=lambda: FakePWMFan())

        module.task_1s()

        self.assertEqual({"pwm_fan_speed": 2100, "pwm_fan_state": 1}, data)

    def test_runtime_starts_pwm_fan_when_present(self):
        from pironman5.runtime import PironmanRuntime

        with mock.patch("pironman5.runtime.PWMFanModule") as module:
            runtime = PironmanRuntime(
                config={},
                peripherals=["pwm_fan_speed"],
                device_info={},
                event_map={},
                log=None,
            )

        module.assert_called_once_with(event=runtime.event, log=runtime.log)


if __name__ == "__main__":
    unittest.main()
