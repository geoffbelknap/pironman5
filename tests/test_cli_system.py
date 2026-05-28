import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


class SystemCliTest(unittest.TestCase):
    def test_load_config_file_returns_empty_config_when_missing(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing-config.json"

            self.assertEqual({"system": {}}, _cli.load_config_file(str(config_path)))
            self.assertFalse(config_path.exists())

    def test_load_config_file_rejects_invalid_json(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text("{bad json", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, f"Invalid config file: {config_path}"):
                _cli.load_config_file(str(config_path))

    def test_update_config_file_creates_missing_file(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            _cli.update_config_file({"system": {"debug_level": "DEBUG"}}, str(config_path))

            self.assertEqual({"system": {"debug_level": "DEBUG"}}, json.loads(config_path.read_text(encoding="utf-8")))

    def test_update_config_file_preserves_existing_values(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"system": {"temperature_unit": "C"}}), encoding="utf-8")

            _cli.update_config_file({"system": {"debug_level": "DEBUG"}}, str(config_path))

            self.assertEqual(
                {"system": {"temperature_unit": "C", "debug_level": "DEBUG"}},
                json.loads(config_path.read_text(encoding="utf-8")),
            )

    def test_get_system_config_value_returns_default_for_missing_values(self):
        from pironman5 import _cli

        self.assertEqual("INFO", _cli.get_system_config_value({"system": {}}, "debug_level", "INFO"))
        self.assertEqual("DEBUG", _cli.get_system_config_value({"system": {"debug_level": "DEBUG"}}, "debug_level", "INFO"))

    def test_handle_debug_level_sets_normalized_value(self):
        from pironman5 import _cli

        args = types.SimpleNamespace(debug_level="debug")
        patch = {}
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            _cli.handle_debug_level(args, {"system": {}}, patch)

        self.assertEqual({"debug_level": "DEBUG"}, patch)
        self.assertIn("Set debug level: DEBUG", stdout.getvalue())

    def test_handle_debug_level_queries_default_without_patch(self):
        from pironman5 import _cli

        args = types.SimpleNamespace(debug_level=None)
        patch = {}
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            _cli.handle_debug_level(args, {"system": {}}, patch)

        self.assertEqual({}, patch)
        self.assertIn("Debug level: INFO", stdout.getvalue())

    def test_handle_database_retention_days_sets_integer_value(self):
        from pironman5 import _cli

        args = types.SimpleNamespace(database_retention_days="14")
        patch = {}
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            _cli.handle_database_retention_days(args, {"system": {}}, patch)

        self.assertEqual({"database_retention_days": 14}, patch)
        self.assertIn("Set database retention days: 14", stdout.getvalue())

    def test_handle_enable_history_sets_boolean_value(self):
        from pironman5 import _cli

        args = types.SimpleNamespace(enable_history="off")
        patch = {}
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            _cli.handle_enable_history(args, {"system": {}}, patch)

        self.assertEqual({"enable_history": False}, patch)
        self.assertIn("Set enable history: False", stdout.getvalue())

    def test_handle_temperature_unit_sets_value(self):
        from pironman5 import _cli

        args = types.SimpleNamespace(temperature_unit="F")
        patch = {}
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            _cli.handle_temperature_unit(args, {"system": {}}, patch)

        self.assertEqual({"temperature_unit": "F"}, patch)
        self.assertIn("Set Temperature unit: F", stdout.getvalue())

    def test_detect_prints_variant_and_optional_hardware(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        detected_variant = {
            "variant": "max",
            "source": "hat-eeprom",
            "part_number": "0306V11",
            "variant_id": "0306",
            "version": "11",
        }
        with mock.patch.object(sys, "argv", ["pironman5", "detect"]):
            with mock.patch.object(_cli, "detect_hardware_variant", return_value=detected_variant):
                with mock.patch.object(_cli, "detect_optional_hardware", return_value={"pipower5": False, "rtl8125": True}):
                    with contextlib.redirect_stdout(stdout):
                        _cli.main()

        output = stdout.getvalue()
        self.assertIn("Variant: Pironman 5 Max (max)", output)
        self.assertIn("Source: HAT EEPROM 0306V11", output)
        self.assertIn("PiPower5 UPS: not detected", output)
        self.assertIn("RTL8125 NIC: detected", output)

    def test_detect_json_prints_machine_readable_hardware(self):
        import json
        from pironman5 import _cli

        stdout = io.StringIO()
        detected_variant = {
            "variant": "max",
            "source": "hat-eeprom",
            "part_number": "0306V11",
            "variant_id": "0306",
            "version": "11",
        }
        with mock.patch.object(sys, "argv", ["pironman5", "detect", "--json"]):
            with mock.patch.object(_cli, "detect_hardware_variant", return_value=detected_variant):
                with mock.patch.object(_cli, "detect_optional_hardware", return_value={"pipower5": False, "rtl8125": True}):
                    with contextlib.redirect_stdout(stdout):
                        _cli.main()

        output = json.loads(stdout.getvalue())
        self.assertEqual("max", output["variant"])
        self.assertEqual("Pironman 5 Max", output["variant_name"])
        self.assertEqual("hat-eeprom", output["source"])
        self.assertEqual("0306V11", output["part_number"])
        self.assertEqual({"pipower5": False, "rtl8125": True}, output["optional_hardware"])

    def test_top_level_command_namespace_is_intentional(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["pironman5", "--help"]):
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stdout(stdout):
                    _cli.main()

        output = stdout.getvalue()
        self.assertIn("detect", output)
        self.assertIn("dashboard", output)
        self.assertIn("start", output)
        self.assertIn("stop", output)
        self.assertIn("launch-browser", output)
        self.assertNotIn("--remove-dashboard", output)
        self.assertNotIn("--enable-history", output)
        self.assertNotIn("--database-retention-days", output)
        self.assertNotIn("--debug-level", output)
        self.assertNotIn("--rgb-brightness", output)
        self.assertNotIn("--oled-enable", output)
        self.assertNotIn("{hardware", output)

    def test_stop_does_not_rewrite_config_file(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"system": {"debug_level": "INFO"}}), encoding="utf-8")
            argv = ["pironman5", "--config-path", str(config_path), "stop"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with mock.patch.object(_cli, "update_config_file") as update_config_file:
                        with mock.patch.object(_cli.subprocess, "run") as run:
                            _cli.main()

            update_config_file.assert_not_called()
            run.assert_called_once_with(["systemctl", "stop", "pironman5.service"], check=False)

    def test_stop_does_not_create_missing_config_file(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing-config.json"
            argv = ["pironman5", "--config-path", str(config_path), "stop"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with mock.patch.object(_cli, "write_json_private") as write_json_private:
                        with mock.patch.object(_cli.subprocess, "run"):
                            _cli.main()

            write_json_private.assert_not_called()
            self.assertFalse(config_path.exists())

    def test_stop_command_does_not_use_process_name_kill(self):
        source = Path("pironman5/_cli.py").read_text(encoding="utf-8")

        self.assertNotIn("pkill", source)

    def test_dashboard_remove_uses_service_venv_pip(self):
        from pironman5 import _cli

        argv = ["pironman5", "dashboard", "remove"]
        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(_cli, "PERIPHERALS", []):
                with mock.patch.object(_cli.subprocess, "run") as run:
                    _cli.main()

        run.assert_called_once_with(["/opt/pironman5-venv/bin/pip", "uninstall", "pm_dashboard", "-y"], check=False)

    def test_legacy_remove_dashboard_flag_still_works(self):
        from pironman5 import _cli

        argv = ["pironman5", "--remove-dashboard"]
        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(_cli, "PERIPHERALS", []):
                with mock.patch.object(_cli.subprocess, "run") as run:
                    with self.assertRaises(SystemExit):
                        _cli.main()

        run.assert_called_once_with(["/opt/pironman5-venv/bin/pip", "uninstall", "pm_dashboard", "-y"], check=False)

    def test_cli_does_not_reference_legacy_installer_venv(self):
        source = Path("pironman5/_cli.py").read_text(encoding="utf-8")

        self.assertNotIn("/opt/pironman5/venv", source)

    def test_available_oled_pages_are_derived_from_peripherals(self):
        from pironman5 import _cli

        pages = _cli.available_oled_pages([
            "oled",
            "oled_page_mix",
            "oled_page_performance",
            "oled_page_battery",
        ])

        self.assertEqual(["mix", "performance", "battery"], pages)

    def test_start_does_not_create_missing_config_file(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing-config.json"
            argv = ["pironman5", "--config-path", str(config_path), "start"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with mock.patch.object(_cli, "write_json_private") as write_json_private:
                        pironman5 = mock.Mock()
                        fake_module = types.ModuleType("pironman5.pironman5")
                        fake_module.Pironman5 = pironman5
                        with mock.patch.dict(sys.modules, {"pironman5.pironman5": fake_module}):
                            _cli.main()

            write_json_private.assert_not_called()
            pironman5.assert_called_once_with(config_path=str(config_path))
            pironman5.return_value.start.assert_called_once_with()
            self.assertFalse(config_path.exists())

    def test_launch_browser_does_not_create_missing_config_file(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing-config.json"
            argv = ["pironman5", "--config-path", str(config_path), "launch-browser"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with mock.patch.object(_cli, "write_json_private") as write_json_private:
                        with mock.patch.object(_cli, "launch_browser") as launch_browser:
                            _cli.main()

            write_json_private.assert_not_called()
            launch_browser.assert_called_once_with()
            self.assertFalse(config_path.exists())

    def test_show_config_does_not_create_missing_config_file(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing-config.json"
            argv = ["pironman5", "--config-path", str(config_path), "--config"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with mock.patch.object(_cli, "write_json_private") as write_json_private:
                        with contextlib.redirect_stdout(stdout):
                            _cli.main()

            write_json_private.assert_not_called()
            self.assertFalse(config_path.exists())

        self.assertIn('"system": {}', stdout.getvalue())

    def test_config_get_uses_default_without_creating_missing_config_file(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing-config.json"
            argv = ["pironman5", "--config-path", str(config_path), "config", "get", "database_retention_days"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with mock.patch.object(_cli, "write_json_private") as write_json_private:
                        with contextlib.redirect_stdout(stdout):
                            _cli.main()

            write_json_private.assert_not_called()
            self.assertFalse(config_path.exists())

        self.assertIn("database_retention_days: 30", stdout.getvalue())

    def test_config_get_rejects_unknown_key(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing-config.json"
            argv = ["pironman5", "--config-path", str(config_path), "config", "get", "not_a_key"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with contextlib.redirect_stdout(stdout):
                        with self.assertRaises(SystemExit):
                            _cli.main()

            self.assertFalse(config_path.exists())

        self.assertIn("Unknown config key: not_a_key", stdout.getvalue())

    def test_config_set_writes_typed_value(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"system": {"database_retention_days": 30}}), encoding="utf-8")
            argv = ["pironman5", "--config-path", str(config_path), "config", "set", "database_retention_days", "14"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with contextlib.redirect_stdout(stdout):
                        _cli.main()

            self.assertEqual(
                {"system": {"database_retention_days": 14}},
                json.loads(config_path.read_text(encoding="utf-8")),
            )

        self.assertIn("Set database_retention_days: 14", stdout.getvalue())

    def test_config_set_normalizes_debug_level(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            argv = ["pironman5", "--config-path", str(config_path), "config", "set", "debug_level", "debug"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    _cli.main()

            self.assertEqual(
                {"system": {"debug_level": "DEBUG"}},
                json.loads(config_path.read_text(encoding="utf-8")),
            )

    def test_debug_level_query_does_not_create_missing_config_file(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing-config.json"
            argv = ["pironman5", "--config-path", str(config_path), "--debug-level"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with mock.patch.object(_cli, "write_json_private") as write_json_private:
                        with contextlib.redirect_stdout(stdout):
                            _cli.main()

            write_json_private.assert_not_called()
            self.assertFalse(config_path.exists())

        self.assertIn("Debug level: INFO", stdout.getvalue())

    def test_database_retention_query_uses_default_when_config_key_missing(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"system": {}}), encoding="utf-8")
            argv = ["pironman5", "--config-path", str(config_path), "--database-retention-days"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with contextlib.redirect_stdout(stdout):
                        _cli.main()

        self.assertIn("Database retention days: 30", stdout.getvalue())

    def test_temperature_unit_query_uses_default_when_config_key_missing(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"system": {}}), encoding="utf-8")
            argv = ["pironman5", "--config-path", str(config_path), "--temperature-unit"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", ["temperature_unit"]):
                    with contextlib.redirect_stdout(stdout):
                        _cli.main()

        self.assertIn("Temperature unit: C", stdout.getvalue())

    def test_rgb_query_uses_default_when_config_key_missing(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"system": {}}), encoding="utf-8")
            argv = ["pironman5", "--config-path", str(config_path), "--rgb-brightness"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", ["ws2812"]):
                    with contextlib.redirect_stdout(stdout):
                        _cli.main()

        self.assertIn("RGB brightness: 100", stdout.getvalue())

    def test_cli_does_not_directly_index_system_config_for_queries(self):
        source = Path("pironman5/_cli.py").read_text(encoding="utf-8")

        self.assertNotIn("current_config['system'][", source)

    def test_cli_does_not_use_shell_string_system_calls(self):
        source = Path("pironman5/_cli.py").read_text(encoding="utf-8")

        self.assertNotIn("os.system", source)

    def test_setting_change_rewrites_config_file(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"system": {"debug_level": "INFO"}}), encoding="utf-8")
            argv = ["pironman5", "--config-path", str(config_path), "--debug-level", "debug"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    with mock.patch.object(_cli, "update_config_file") as update_config_file:
                        _cli.main()

            update_config_file.assert_called_once_with({"system": {"debug_level": "DEBUG"}}, str(config_path))

    def test_setting_change_creates_missing_config_file(self):
        from pironman5 import _cli

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing-config.json"
            argv = ["pironman5", "--config-path", str(config_path), "--debug-level", "debug"]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(_cli, "PERIPHERALS", []):
                    _cli.main()

            self.assertEqual({"system": {"debug_level": "DEBUG"}}, json.loads(config_path.read_text(encoding="utf-8")))

    def test_system_plan_does_not_require_runtime_hardware_dependencies(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["pironman5", "system", "plan"]):
            with contextlib.redirect_stdout(stdout):
                _cli.main()

        output = stdout.getvalue()
        self.assertIn("System setup plan", output)
        self.assertIn("/boot/firmware/overlays", output)
        self.assertIn("/etc/modules-load.d/pironman5.conf", output)
        self.assertIn("No changes made", output)

    def test_system_setup_dry_run_prints_privileged_commands(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        argv = ["pironman5", "system", "setup", "--variant", "max", "--dry-run"]
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(stdout):
                _cli.main()

        output = stdout.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("install -m 0644 -o root -g root", output)
        self.assertIn("/boot/firmware/overlays/sunfounder-pironman5.dtbo", output)
        self.assertIn("/etc/modules-load.d/pironman5.conf", output)
        self.assertIn("/usr/local/bin/pironman5", output)
        self.assertIn("/opt/pironman5-venv", output)
        self.assertIn("systemctl enable pironman5.service", output)
        self.assertIn("systemctl restart pironman5.service", output)
        self.assertNotIn("/home/geoff/.local/pipx", output)
        self.assertNotIn("rm -rf /opt/pironman5-venv", output)

    def test_system_setup_default_venv_bootstrap_does_not_use_shell(self):
        from pironman5 import system

        _variant_key, commands = system.setup_commands("max")

        self.assertFalse(any(command.args[:2] == ("sh", "-c") for command in commands))
        self.assertTrue(any(command.args[0] == "ensure-service-venv" for command in commands))

    def test_system_setup_installs_legacy_extra_for_legacy_variant(self):
        from pironman5 import system

        _variant_key, commands = system.setup_commands("max")
        ensure_venv = next(command for command in commands if command.args[0] == "ensure-service-venv")

        self.assertIn("[legacy-hardware]", ensure_venv.args[1])

    def test_system_setup_skips_legacy_extra_for_local_only_variant(self):
        from pironman5 import system

        _variant_key, commands = system.setup_commands("mini")
        ensure_venv = next(command for command in commands if command.args[0] == "ensure-service-venv")

        self.assertNotIn("legacy-hardware", ensure_venv.args[1])

    def test_system_setup_skips_legacy_extra_for_rtl8125_only_profile(self):
        from pironman5 import system

        product = {"modules": ["rtl8125"], "dt_overlays": [], "config_txt": {}}

        self.assertEqual((), system._service_package_extras(product))

    def test_system_setup_skips_legacy_extra_for_vibration_switch_only_profile(self):
        from pironman5 import system

        product = {"modules": ["vibration_switch"], "dt_overlays": [], "config_txt": {}}

        self.assertEqual((), system._service_package_extras(product))

    def test_system_setup_skips_legacy_extra_for_oled_ups_pages_only_profile(self):
        from pironman5 import system

        product = {"modules": ["oled_ups_pages"], "dt_overlays": [], "config_txt": {}}

        self.assertEqual((), system._service_package_extras(product))

    def test_system_setup_skips_ups_extra_without_pipower5_hardware(self):
        from pironman5 import system

        with mock.patch.object(system, "detect_optional_hardware", return_value={"pipower5": False}):
            _variant_key, commands = system.setup_commands("ups")

        ensure_venv = next(command for command in commands if command.args[0] == "ensure-service-venv")
        self.assertNotIn("ups", ensure_venv.args[1])

    def test_system_setup_does_not_install_unaudited_ups_extra_for_detected_pipower5_hardware(self):
        from pironman5 import system

        with mock.patch.object(system, "detect_optional_hardware", return_value={"pipower5": True}):
            _variant_key, commands = system.setup_commands("ups")

        ensure_venv = next(command for command in commands if command.args[0] == "ensure-service-venv")
        self.assertIn("[legacy-hardware]", ensure_venv.args[1])
        self.assertNotIn("ups", ensure_venv.args[1])

    def test_system_setup_installs_ups_extra_for_explicit_pipower5_hardware(self):
        from pironman5 import system

        with mock.patch.object(system, "detect_optional_hardware", return_value={"pipower5": False}):
            _variant_key, commands = system.setup_commands("ups", enabled_optional_hardware=["pipower5"])

        ensure_venv = next(command for command in commands if command.args[0] == "ensure-service-venv")
        self.assertIn("[legacy-hardware,ups]", ensure_venv.args[1])

    def test_system_setup_persists_explicit_optional_hardware(self):
        from pironman5 import system

        stdout = io.StringIO()
        argv = [
            "pironman5",
            "system",
            "setup",
            "--variant",
            "ups",
            "--with",
            "pipower5",
            "--dry-run",
        ]

        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(stdout):
                system.main(sys.argv[2:])

        output = stdout.getvalue()
        self.assertIn("/opt/pironman5/.enabled_optional_hardware", output)

    def test_system_setup_refresh_venv_reinstalls_service_environment(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        argv = ["pironman5", "system", "setup", "--variant", "max", "--fresh", "--dry-run"]
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(stdout):
                _cli.main()

        output = stdout.getvalue()
        self.assertIn("rm -rf /opt/pironman5-venv", output)
        self.assertIn("python3 -m venv /opt/pironman5-venv", output)
        self.assertIn("/opt/pironman5-venv/bin/pip install --upgrade", output)

    def test_system_removal_commands_use_guarded_internal_actions(self):
        from pironman5 import system

        _variant_key, setup_refresh_commands = system.setup_commands("max", refresh_venv=True)
        uninstall_commands = system.uninstall_commands("max", purge=True)
        commands = [*setup_refresh_commands, *uninstall_commands]

        self.assertFalse(any(command.args[:2] == ("rm", "-rf") for command in commands))
        self.assertTrue(any(command.args == ("remove-tree", str(system.SERVICE_VENV)) for command in commands))
        self.assertTrue(any(command.args == ("remove-tree", str(system.WORK_DIR)) for command in commands))

    def test_guarded_tree_removal_rejects_unapproved_paths(self):
        from pironman5 import system

        command = system.Command("Remove unsafe tree", ("remove-tree", "/tmp"))

        with self.assertRaisesRegex(ValueError, "Refusing to remove unapproved tree"):
            system._run_internal_command(command)

    def test_system_doctor_reports_missing_setup_files(self):
        from pironman5 import system

        stdout = io.StringIO()
        with mock.patch.object(system.Path, "exists", return_value=False):
            with contextlib.redirect_stdout(stdout):
                system.main(["doctor", "--variant", "max"])

        output = stdout.getvalue()
        self.assertIn("System setup doctor", output)
        self.assertIn("missing", output)
        self.assertIn("/etc/modules-load.d/pironman5.conf", output)
        self.assertIn("service active:", output)
        self.assertIn("service enabled:", output)
        self.assertIn("wrapper target:", output)
        self.assertIn("pipx/user version:", output)
        self.assertIn("service version:", output)
        self.assertIn("pipx/user source:", output)
        self.assertIn("service source:", output)
        self.assertIn("install drift:", output)
        self.assertIn("legacy modules.conf i2c-dev entries:", output)

    def test_system_upgrade_service_refreshes_service_environment(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        argv = ["pironman5", "system", "update", "--dry-run"]
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(stdout):
                _cli.main()

        output = stdout.getvalue()
        self.assertIn("rm -rf /opt/pironman5-venv", output)
        self.assertIn("python3 -m venv /opt/pironman5-venv", output)
        self.assertIn("/opt/pironman5-venv/bin/pip install --upgrade", output)
        self.assertIn("systemctl restart pironman5.service", output)

    def test_system_upgrade_service_uses_installed_variant_extra(self):
        from pironman5 import system

        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            (work_dir / ".variant").write_text("max\n", encoding="utf-8")

            with mock.patch.object(system, "WORK_DIR", work_dir):
                commands = system.upgrade_service_commands()

        install = next(command for command in commands if command.description == "Install service application package")
        self.assertIn("[legacy-hardware]", install.args[-1])

    def test_system_upgrade_service_skips_ups_extra_without_pipower5_hardware(self):
        from pironman5 import system

        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            (work_dir / ".variant").write_text("ups\n", encoding="utf-8")

            with mock.patch.object(system, "WORK_DIR", work_dir), \
                    mock.patch.object(system, "OPTIONAL_HARDWARE_FILE", work_dir / ".enabled_optional_hardware"), \
                    mock.patch.object(system, "detect_optional_hardware", return_value={"pipower5": False}):
                commands = system.upgrade_service_commands()

        install = next(command for command in commands if command.description == "Install service application package")
        self.assertIn("[legacy-hardware]", install.args[-1])
        self.assertNotIn("ups", install.args[-1])

    def test_system_upgrade_service_uses_persisted_optional_hardware_extra(self):
        from pironman5 import system

        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            (work_dir / ".variant").write_text("ups\n", encoding="utf-8")
            (work_dir / ".enabled_optional_hardware").write_text("pipower5\n", encoding="utf-8")

            with mock.patch.object(system, "WORK_DIR", work_dir), \
                    mock.patch.object(system, "OPTIONAL_HARDWARE_FILE", work_dir / ".enabled_optional_hardware"), \
                    mock.patch.object(system, "detect_optional_hardware", return_value={"pipower5": False}):
                commands = system.upgrade_service_commands()

        install = next(command for command in commands if command.description == "Install service application package")
        self.assertIn("[legacy-hardware,ups]", install.args[-1])

    def test_service_install_info_does_not_import_from_current_checkout(self):
        from pironman5 import system

        with mock.patch.object(system.Path, "exists", return_value=True):
            with mock.patch.object(system.subprocess, "run") as run:
                run.return_value.stdout = '{"version": "1", "source": "installed", "commit": null}'

                self.assertEqual(system._service_install_info()["source"], "installed")

        self.assertEqual(run.call_args.kwargs["cwd"], "/")

    def test_system_uninstall_dry_run_prints_removed_files(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        argv = ["pironman5", "system", "uninstall", "--variant", "max", "--dry-run"]
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(stdout):
                _cli.main()

        output = stdout.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("systemctl disable pironman5.service", output)
        self.assertIn("/etc/modules-load.d/pironman5.conf", output)
        self.assertIn("/boot/firmware/overlays/sunfounder-pironman5.dtbo", output)
        self.assertIn("/opt/pironman5-venv", output)
        self.assertNotIn("\nrm -rf /opt/pironman5\n", output)

    def test_system_uninstall_purge_removes_runtime_state(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        argv = ["pironman5", "system", "uninstall", "--variant", "max", "--purge", "--dry-run"]
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(stdout):
                _cli.main()

        output = stdout.getvalue()
        self.assertIn("rm -rf /opt/pironman5", output)
        self.assertIn("rm -rf /var/log/pironman5", output)

    def test_readme_documents_pipx_as_primary_install_path(self):
        with open("README.md", "r", encoding="utf-8") as f:
            readme = f.read()

        self.assertIn("primary install path", readme)
        self.assertIn("/opt/pironman5-venv", readme)
        self.assertIn("system update", readme)
        self.assertNotIn("system upgrade-service", readme)
        self.assertIn("pipx reinstall pironman5", readme)
        self.assertNotIn("moving toward a split install model", readme)

    def test_system_help_uses_update_command(self):
        from pironman5 import system

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as exit_context:
                system.main(["--help"])

        self.assertEqual(0, exit_context.exception.code)
        output = stdout.getvalue()
        self.assertIn("update", output)
        self.assertNotIn("upgrade-service", output)

    def test_system_setup_help_uses_fresh_flag(self):
        from pironman5 import system

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as exit_context:
                system.main(["setup", "--help"])

        self.assertEqual(0, exit_context.exception.code)
        output = stdout.getvalue()
        self.assertIn("--fresh", output)
        self.assertNotIn("--refresh-venv", output)


if __name__ == "__main__":
    unittest.main()
