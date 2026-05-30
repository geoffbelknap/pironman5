import argparse
import io
import unittest
import unittest.mock
from pathlib import Path


class InstallSettingsPolicyTest(unittest.TestCase):
    def test_install_py_refuses_legacy_install_by_default(self):
        import install

        with unittest.mock.patch("sys.stdout", new=io.StringIO()) as stdout:
            result = install.main([])

        self.assertEqual(2, result)
        self.assertIn("pironman5 setup", stdout.getvalue())
        self.assertIn("sudo ~/.local/bin/pironman5 setup", stdout.getvalue())
        self.assertNotIn('sudo "$(command -v pironman5)" setup', stdout.getvalue())
        self.assertNotIn("pironman5 system setup", stdout.getvalue())

    def test_install_py_legacy_flag_is_no_longer_executable(self):
        import install

        fake_plan = unittest.mock.Mock()
        fake_plan.parser = argparse.ArgumentParser()
        with unittest.mock.patch.object(install, "build_installer", return_value=fake_plan), \
             unittest.mock.patch.object(install, "describe_variant_selection", return_value=("mini", "Selected variant")), \
             unittest.mock.patch("sys.stdout", new=io.StringIO()) as stdout:
            result = install.main(["--legacy-installer"])

        self.assertEqual(2, result)
        self.assertIn("legacy installer path has been removed", stdout.getvalue())

    def test_dashboard_settings_are_disabled_by_default(self):
        import install

        args = install.parse_install_args([])
        names = install.resolve_enabled_setting_names(args, peripherals=["oled", "ws2812"])

        self.assertIn("base", names)
        self.assertIn("oled", names)
        self.assertIn("ws2812", names)
        self.assertNotIn("dashboard", names)
        self.assertNotIn("influxdb_legacy", names)

    def test_dashboard_requires_explicit_flag(self):
        import install

        args = install.parse_install_args(["--enable-dashboard"])
        names = install.resolve_enabled_setting_names(args, peripherals=["oled"])

        self.assertIn("dashboard", names)
        self.assertNotIn("influxdb_legacy", names)

    def test_legacy_influxdb_setting_is_not_available(self):
        import install

        with unittest.mock.patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit):
            install.parse_install_args(["--enable-dashboard", "--enable-influxdb-legacy"])

    def test_pipower5_requires_detected_hat_or_explicit_flag(self):
        import install

        args = install.parse_install_args([])
        with unittest.mock.patch(
            "install.detect_optional_hardware",
            return_value={"pipower5": False},
        ):
            names = install.resolve_enabled_setting_names(args, peripherals=["pipower5"])

        self.assertNotIn("pipower5", names)

    def test_pipower5_detection_does_not_install_unaudited_legacy_dependency(self):
        import install

        args = install.parse_install_args([])
        with unittest.mock.patch(
            "install.detect_optional_hardware",
            return_value={"pipower5": True},
        ):
            names = install.resolve_enabled_setting_names(args, peripherals=["pipower5"])

        self.assertNotIn("pipower5", names)

    def test_pipower5_flag_overrides_hardware_detection(self):
        import install

        args = install.parse_install_args(["--enable-ups"])
        with unittest.mock.patch(
            "install.detect_optional_hardware",
            return_value={"pipower5": False},
        ):
            names = install.resolve_enabled_setting_names(args, peripherals=[])

        self.assertIn("pipower5", names)

    def test_pironman_mcu_is_not_enabled_without_explicit_legacy_flag(self):
        import install

        args = install.parse_install_args([])
        with unittest.mock.patch(
            "install.detect_optional_hardware",
            return_value={"pironman_mcu": True},
        ):
            names = install.resolve_enabled_setting_names(args, peripherals=["pironman_mcu"])

        self.assertNotIn("legacy_hardware", names)

    def test_pironman_mcu_flag_persists_runtime_optional_hardware(self):
        import install

        args = install.parse_install_args(["--enable-legacy-hardware", "pironman_mcu"])
        plan = install.build_installer_for_settings(["base"])

        install.apply_optional_hardware_install_settings(plan, args)

        self.assertEqual(plan.work_files[".enabled_optional_hardware"], "pironman_mcu\n")

    def test_enable_ups_persists_runtime_optional_hardware(self):
        import install

        args = install.parse_install_args(["--enable-ups"])
        plan = install.build_installer_for_settings(["base"])

        install.apply_optional_hardware_install_settings(plan, args)

        self.assertEqual(plan.work_files[".enabled_optional_hardware"], "pipower5\n")

    def test_default_install_does_not_persist_optional_hardware(self):
        import install

        args = install.parse_install_args([])
        plan = install.build_installer_for_settings(["base"])

        install.apply_optional_hardware_install_settings(plan, args)

        self.assertNotIn(".enabled_optional_hardware", plan.work_files)

    def test_rtl8125_requires_explicit_experimental_flag(self):
        import install

        args = install.parse_install_args([])
        with unittest.mock.patch(
            "install.detect_optional_hardware",
            return_value={"rtl8125": False, "pipower5": False},
        ):
            names = install.resolve_enabled_setting_names(args, peripherals=["rtl8125"])

        self.assertNotIn("rtl8125", names)

        args = install.parse_install_args(["--enable-experimental-dependency", "rtl8125"])
        with unittest.mock.patch(
            "install.detect_optional_hardware",
            return_value={"rtl8125": False, "pipower5": False},
        ):
            names = install.resolve_enabled_setting_names(args, peripherals=["rtl8125"])

        self.assertIn("rtl8125", names)

    def test_rtl8125_auto_enables_when_hardware_is_detected(self):
        import install

        args = install.parse_install_args([])
        with unittest.mock.patch(
            "install.detect_optional_hardware",
            return_value={"rtl8125": True, "pipower5": False},
        ):
            names = install.resolve_enabled_setting_names(args, peripherals=["rtl8125"])

        self.assertIn("rtl8125", names)

    def test_pro_max_variant_config_txt_is_applied(self):
        import install
        from pironman5.variants.pironman5_pro_max import Pironman5ProMax

        plan = install.build_installer_for_settings(["base"])
        install.apply_variant_config_txt(plan, Pironman5ProMax)

        self.assertEqual(plan.config_txt["dtparam=spi"], "on")
        self.assertEqual(plan.config_txt["dtparam=i2c_arm"], "on")

    def test_oled_timeout_zero_is_documented_as_disable(self):
        with open("pironman5/_cli.py", "r", encoding="utf-8") as f:
            cli = f.read()

        self.assertIn("set to 0 to disable timeout", cli)
        self.assertIn("Set OLED sleep timeout: disabled", cli)

    def test_sunfounder_git_dependencies_are_pinned_to_commits(self):
        import install

        plan = install.build_installer_for_settings([
            "base",
            "dashboard",
            "pipower5",
        ])

        sunfounder_urls = [
            url for url in plan.python_source.values()
            if isinstance(url, str) and "github.com/sunfounder" in url
        ]

        self.assertGreater(len(sunfounder_urls), 0)
        for url in sunfounder_urls:
            ref = url.rsplit("@", 1)[-1]
            self.assertRegex(ref, r"^[0-9a-f]{40}$")

    def test_default_runtime_dependencies_use_reviewed_forks(self):
        import install

        plan = install.build_installer_for_settings(["base"])

        self.assertIn("github.com/geoffbelknap/pm_auto", plan.python_source["pm_auto"])
        self.assertNotIn("sf_rpi_status", plan.python_source)

    def test_dashboard_dependency_uses_reviewed_fork(self):
        import install

        plan = install.build_installer_for_settings(["dashboard"])

        self.assertIn("github.com/geoffbelknap/pm_dashboard", plan.python_source["pm_dashboard"])

    def test_variant_flag_is_parsed(self):
        import install

        args = install.parse_install_args(["--variant", "mini"])

        self.assertEqual("mini", args.variant)

    def test_auto_variant_is_default(self):
        import install

        args = install.parse_install_args([])

        self.assertEqual("auto", args.variant)

    def test_variant_flag_accepts_hyphenated_alias(self):
        import install

        args = install.parse_install_args(["--variant", "pro-max"])

        self.assertEqual("pro_max", args.variant)

    def test_auto_variant_uses_hardware_detection(self):
        import install

        args = install.parse_install_args([])
        with unittest.mock.patch.object(install, "detect_hardware_variant", return_value={"variant": "mini"}):
            variant = install.get_selected_variant_key(args)

        self.assertEqual("mini", variant)

    def test_variant_flag_controls_dependency_settings(self):
        import install

        args = install.parse_install_args(["--variant", "mini"])
        names = install.resolve_enabled_setting_names(args)

        self.assertIn("ws2812", names)
        self.assertIn("gpio", names)
        self.assertNotIn("oled", names)
        self.assertNotIn("pi5_power_button", names)

    def test_build_installer_persists_selected_variant(self):
        import install

        plan = install.build_installer_for_variant("mini")

        self.assertEqual({".variant": "mini\n"}, plan.work_files)

    def test_print_variant_flag_is_parsed(self):
        import install

        args = install.parse_install_args(["--print-variant"])

        self.assertTrue(args.print_variant)

    def test_variant_help_lists_canonical_values(self):
        import install

        self.assertIn("auto, base, max, mini, nas, pro_max, ups", install.VARIANT_HELP)

    def test_gpio_settings_use_installer_preflight_actions(self):
        import install

        plan = install.build_installer_for_settings(["gpio"])

        self.assertIn("install_lgpio", plan.preflight_actions)
        self.assertIn("fix_kali_gpio_spi_groups", plan.preflight_actions)
        self.assertIn("RPi.GPIO", plan.custom_uninstall_pip_dependencies)
        self.assertIn("rpi.lgpio", plan.custom_pip_dependencies)
        self.assertNotIn("install_lgpio.sh", plan.before_install_scripts)
        self.assertNotIn("fix_kali_gpio_spi.sh", plan.before_install_scripts)
        self.assertNotIn("change_rpi.gpio_to_rpi.lgpio.sh", plan.after_install_scripts)

    def test_base_settings_use_installer_umbrel_preflight_action(self):
        import install

        plan = install.build_installer_for_settings(["base"])

        self.assertIn("apply_umbrel_patch", plan.preflight_actions)
        self.assertNotIn("umbrel_patch.sh", plan.before_install_scripts)

    def test_shared_preflight_actions_are_not_duplicated(self):
        import install

        plan = install.build_installer_for_settings(["gpio", "ws2812"])

        self.assertEqual(1, plan.preflight_actions.count("install_lgpio"))
        self.assertEqual(1, plan.preflight_actions.count("fix_kali_gpio_spi_groups"))


class DeadCodePolicyTest(unittest.TestCase):
    def test_legacy_sf_installer_framework_is_removed(self):
        self.assertFalse(Path("tools/sf_installer.py").exists())

    def test_stale_manual_helper_files_are_not_tracked(self):
        stale_paths = [
            Path("scripts/setup_influxdb.sh"),
            Path("scripts/install_influxdb.sh"),
            Path("scripts/test_dpkg_lock.sh"),
            Path("scripts/upload-1.2.ps1"),
            Path("scripts/wait_for_dpkg.sh"),
            Path("scripts/install_lgpio.sh"),
            Path("scripts/fix_kali_gpio_spi.sh"),
            Path("scripts/change_rpi.gpio_to_rpi.lgpio.sh"),
            Path("scripts/umbrel_patch.sh"),
            Path("tests/read_variants.py"),
            Path("tests/usgae.md"),
        ]

        for stale_path in stale_paths:
            with self.subTest(path=stale_path):
                self.assertFalse(stale_path.exists())

    def test_duplicate_root_asset_directories_are_not_tracked(self):
        duplicate_paths = [
            Path("bin/99-com.rules"),
            Path("bin/pironman5"),
            Path("bin/pironman5.service"),
            Path("overlays/sunfounder-pipower5.dtbo"),
            Path("overlays/sunfounder-pironman5.dtbo"),
            Path("overlays/sunfounder-pironman5mini.dtbo"),
            Path("overlays/sunfounder-pironman5nas.dtbo"),
            Path("overlays/sunfounder-pironman5promax.dtbo"),
            Path("sunfounder-pironman5.dtbo"),
            Path("sunfounder-pironman5mini.dtbo"),
        ]

        for duplicate_path in duplicate_paths:
            with self.subTest(path=duplicate_path):
                self.assertFalse(duplicate_path.exists())


class ServiceHardeningTest(unittest.TestCase):
    def test_service_runs_as_pironman5_user(self):
        with open("pironman5/assets/bin/pironman5.service", "r", encoding="utf-8") as f:
            service = f.read()

        self.assertIn("User=pironman5", service)
        self.assertIn("Group=pironman5", service)
        self.assertNotIn("User=root", service)
        self.assertNotIn("Group=root", service)

    def test_service_loads_default_environment_file(self):
        with open("pironman5/assets/bin/pironman5.service", "r", encoding="utf-8") as f:
            service = f.read()

        self.assertIn("EnvironmentFile=-/etc/default/pironman5", service)

    def test_pipower5_install_script_requires_local_driver_archive(self):
        with open("scripts/setup_pipower5.sh", "r", encoding="utf-8") as f:
            script = f.read()

        self.assertIn("--driver-zip", script)
        self.assertIn("--sha256", script)
        self.assertIn("sha256sum -c", script)
        self.assertNotIn("curl ", script)
        self.assertNotIn("https://github.com/sunfounder/pipower5/releases", script)
        self.assertNotIn("apt-get", script)

    def test_pipower5_driver_script_is_not_run_by_installer(self):
        import install

        plan = install.build_installer_for_settings(["pipower5"])

        self.assertNotIn("setup_pipower5.sh", plan.before_install_scripts)

    def test_pipower5_install_does_not_download_email_templates(self):
        with open("scripts/setup_pipower5.sh", "r", encoding="utf-8") as f:
            script = f.read()

        self.assertNotIn("email_templates", script)
        self.assertNotIn("/opt/pipower5", script)

    def test_rtl8125_setup_is_not_run_by_installer(self):
        import install

        plan = install.build_installer_for_settings(["rtl8125"])

        self.assertNotIn("setup_rtl8125.sh", plan.before_install_scripts)

    def test_rtl8125_setup_requires_explicit_write_efuse_flag(self):
        with open("scripts/setup_rtl8125.sh", "r", encoding="utf-8") as f:
            script = f.read()

        self.assertIn("--write-efuse", script)
        self.assertIn("--confirm-mac-unset", script)
        self.assertIn("--tool-dir", script)
        self.assertIn("This script writes RTL8125 eFuse data", script)
        self.assertNotIn("git clone", script)
        self.assertNotIn("rm -rf", script)


class InfluxDefaultPolicyTest(unittest.TestCase):
    def test_default_install_does_not_reference_influxdb_script(self):
        import install

        args = install.parse_install_args([])
        names = install.resolve_enabled_setting_names(args, peripherals=["oled"])
        plan = install.build_installer_for_settings(names)

        self.assertNotIn("install_influxdb.sh", plan.before_install_scripts)
        self.assertNotIn("influxdb", plan.groups)

    def test_legacy_influxdb_flag_is_not_supported(self):
        import install

        with unittest.mock.patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit):
            install.parse_install_args(["--enable-dashboard", "--enable-influxdb-legacy"])

    def test_remove_dashboard_does_not_manage_influxdb(self):
        with open("pironman5/_cli.py", "r", encoding="utf-8") as f:
            cli = f.read()

        self.assertNotIn("influxdb", cli.lower())


if __name__ == "__main__":
    unittest.main()
