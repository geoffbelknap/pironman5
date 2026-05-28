import unittest
import unittest.mock
import io
from pathlib import Path
from types import SimpleNamespace

from tools.sf_installer import SF_Installer


class Args(SimpleNamespace):
    def __contains__(self, name):
        return hasattr(self, name)


class ShellCommandQuotingTest(unittest.TestCase):
    def test_quotes_pip_dependency_specs_with_shell_metacharacters(self):
        command = SF_Installer.shell_join([
            "/opt/pironman5/venv/bin/pip3",
            "install",
            "--upgrade",
            "pyftdi>=0.40.0",
            "Adafruit-PureIO>=1.1.7",
            "Adafruit-Blinka==8.59.0",
        ])

        self.assertIn("'pyftdi>=0.40.0'", command)
        self.assertIn("'Adafruit-PureIO>=1.1.7'", command)
        self.assertNotIn(" pyftdi>=", command)
        self.assertNotIn(" Adafruit-PureIO>=", command)


class InstallerMainArgumentTest(unittest.TestCase):
    def test_main_uses_preparsed_args_when_available(self):
        installer = SF_Installer("pironman5")
        installer.args = SimpleNamespace(uninstall=True, skip_reboot=True)
        installer.check_admin = lambda: None
        installer.uninstall = lambda: None
        installer.cleanup = lambda: None
        installer.print_title = lambda *_args, **_kwargs: None
        installer.parser.parse_args = lambda: self.fail("parse_args should not be called")

        installer.main()


class InstallerCommandConstructionTest(unittest.TestCase):
    def test_working_directory_commands_quote_paths(self):
        installer = SF_Installer(
            "pironman5",
            work_dir="/opt/piron man;bad",
            log_dir="/var/log/piron man;bad",
        )
        installer.args = SimpleNamespace(plain_text=True)
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        installer.create_working_dir()

        self.assertIn("mkdir -p '/opt/piron man;bad'", commands)
        self.assertIn("chmod 750 '/opt/piron man;bad'", commands)
        self.assertIn("mkdir -p '/var/log/piron man;bad'", commands)
        self.assertIn("touch '/var/log/piron man;bad/pironman5.log'", commands)
        for command in commands:
            self.assertNotIn(" /opt/piron man;bad", command)
            self.assertNotIn(" /var/log/piron man;bad", command)

    def test_setup_user_normalizes_service_home_permissions(self):
        installer = SF_Installer("pironman5")
        installer.args = SimpleNamespace(plain_text=True)
        commands = []
        installer.run_command = lambda _cmd, **_kwargs: (0, "", "")
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        installer.setup_user()

        self.assertIn("chmod 750 /opt/pironman5", commands)
        self.assertIn("find /opt/pironman5 -mindepth 1 -maxdepth 1 -type f -exec chmod 640 '{}' +", commands)
        self.assertIn("find /opt/pironman5 -mindepth 1 -maxdepth 1 -type d -exec chmod 750 '{}' +", commands)

    def test_setup_user_does_not_copy_skeleton_files(self):
        installer = SF_Installer("pironman5")
        installer.args = SimpleNamespace(plain_text=True)
        commands = []

        def fake_run_command(cmd, **_kwargs):
            if cmd.startswith("getent"):
                return (1, "", "")
            return (0, "", "")

        installer.run_command = fake_run_command
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        installer.setup_user()

        useradd_commands = [cmd for cmd in commands if cmd.startswith("useradd ")]
        self.assertEqual(len(useradd_commands), 1)
        self.assertNotIn(" -m ", useradd_commands[0])
        self.assertIn("--no-create-home", useradd_commands[0])

    def test_work_dir_fix_keeps_directory_private(self):
        installer = SF_Installer("pironman5", work_dir="/opt/pironman5")
        installer.args = SimpleNamespace(plain_text=True)
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        installer.change_work_dir_owner()

        self.assertIn("chmod 750 /opt/pironman5", commands)
        self.assertNotIn("chmod +x /opt/pironman5", commands)

    def test_work_files_are_written_privately(self):
        installer = SF_Installer("pironman5", work_dir="/opt/pironman5")
        installer.args = SimpleNamespace(plain_text=True)
        installer.work_files = {".variant": "mini\n"}
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        installer.write_work_files()

        self.assertIn("printf %s 'mini\n' | tee /opt/pironman5/.variant > /dev/null", commands)
        self.assertIn("chown pironman5:pironman5 /opt/pironman5/.variant", commands)
        self.assertIn("chmod 640 /opt/pironman5/.variant", commands)

    def test_modules_probe_writes_dedicated_idempotent_modules_file(self):
        installer = SF_Installer("pironman5")
        installer.args = Args(plain_text=True, skip_modules=False)
        installer.modules = {"i2c-dev"}
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        installer.modules_probe()

        self.assertEqual(commands, [
            "printf '%s\\n' i2c-dev | install -m 0644 -o root -g root /dev/stdin /etc/modules-load.d/pironman5.conf"
        ])

    def test_copy_dtoverlay_installs_root_owned_non_executable_file(self):
        installer = SF_Installer("pironman5")
        installer.args = Args(plain_text=True, skip_dtoverlay=False)
        installer.dtoverlays = {"sunfounder-pironman5.dtbo"}
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        installer.copy_dtoverlay()

        self.assertIn(
            "install -m 0644 -o root -g root pironman5/assets/overlays/sunfounder-pironman5.dtbo /boot/firmware/overlays/sunfounder-pironman5.dtbo",
            commands,
        )

    def test_setup_auto_start_uses_packaged_service_asset(self):
        installer = SF_Installer("pironman5")
        installer.args = Args(plain_text=True, skip_auto_start=False)
        installer.service_files = ["pironman5.service"]
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        installer.setup_auto_start()

        self.assertIn("cp pironman5/assets/bin/pironman5.service /etc/systemd/system/", commands)

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

    def test_wait_for_dpkg_does_not_shell_out_to_helper_script(self):
        installer = SF_Installer("pironman5")
        installer.get_dpkg_lock_holders = lambda: []

        with unittest.mock.patch("os.system") as system:
            installer.wait_for_dpkg(wait_interval=0, max_wait=0)

        system.assert_not_called()

    def test_wait_for_dpkg_times_out_when_lock_remains_held(self):
        installer = SF_Installer("pironman5")
        installer.get_dpkg_lock_holders = lambda: [
            {"lock_file": "/var/lib/dpkg/lock", "pid": "123", "process": "apt-get"}
        ]

        with self.assertRaisesRegex(RuntimeError, "Timeout waiting for dpkg"):
            installer.wait_for_dpkg(wait_interval=0, max_wait=0)

    def test_run_preflight_actions_dispatches_installer_methods(self):
        installer = SF_Installer("pironman5")
        installer.args = Args(plain_text=True)
        installer.preflight_actions = ["install_lgpio", "fix_kali_gpio_spi_groups"]
        calls = []
        installer.install_lgpio = lambda: calls.append("install_lgpio")
        installer.fix_kali_gpio_spi_groups = lambda: calls.append("fix_kali_gpio_spi_groups")

        installer.run_preflight_actions()

        self.assertEqual(["install_lgpio", "fix_kali_gpio_spi_groups"], calls)

    def test_run_preflight_actions_rejects_unknown_actions(self):
        installer = SF_Installer("pironman5")
        installer.args = Args(plain_text=True)
        installer.preflight_actions = ["unknown_action"]

        with self.assertRaisesRegex(ValueError, "Unknown preflight action"):
            installer.run_preflight_actions()

    def test_install_lgpio_uses_apt_packages_without_source_fallback(self):
        installer = SF_Installer("pironman5")
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        installer.install_lgpio()

        self.assertEqual(
            ["env DEBIAN_FRONTEND=noninteractive apt-get install -y liblgpio-dev python3-lgpio"],
            commands,
        )

    def test_fix_kali_gpio_spi_groups_is_noop_off_kali(self):
        installer = SF_Installer("pironman5")
        installer.args = Args(plain_text=True)
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        with unittest.mock.patch.object(installer, "is_kali_linux", return_value=False):
            installer.fix_kali_gpio_spi_groups()

        self.assertEqual([], commands)

    def test_fix_kali_gpio_spi_groups_normalizes_groups_on_kali(self):
        installer = SF_Installer("pironman5")
        installer.args = Args(plain_text=True)
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        with unittest.mock.patch.object(installer, "is_kali_linux", return_value=True):
            installer.fix_kali_gpio_spi_groups()

        self.assertEqual(
            [
                "getent group gpio > /dev/null || groupadd -r gpio",
                "getent group spi > /dev/null || groupadd -r spi",
            ],
            commands,
        )

    def test_apply_umbrel_patch_is_noop_off_umbrel(self):
        installer = SF_Installer("pironman5")
        installer.args = Args(plain_text=True)
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        with unittest.mock.patch.object(installer, "is_umbrel_os", return_value=False):
            installer.apply_umbrel_patch()

        self.assertEqual([], commands)

    def test_apply_umbrel_patch_applies_umbrel_system_changes(self):
        installer = SF_Installer("pironman5")
        installer.args = Args(plain_text=True)
        commands = []
        installer.do = lambda _msg, cmd, **_kwargs: commands.append(cmd)

        with unittest.mock.patch.object(installer, "is_umbrel_os", return_value=True), \
             unittest.mock.patch.object(installer, "is_boot_read_only", return_value=True):
            installer.apply_umbrel_patch()

        self.assertEqual(
            [
                "mount -o remount,rw /boot",
                "getent group gpio > /dev/null || groupadd -r gpio",
                "getent group spi > /dev/null || groupadd -r spi",
                "chown :gpio /dev/gpiochip*",
                "chown :spi /dev/spidev*",
                "install -m 0644 -o root -g root pironman5/assets/bin/99-com.rules /etc/udev/rules.d/99-com.rules",
                "udevadm control --reload-rules",
            ],
            commands,
        )


class InstallSettingsPolicyTest(unittest.TestCase):
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

    def test_pipower5_auto_enables_when_hat_is_detected(self):
        import install

        args = install.parse_install_args([])
        with unittest.mock.patch(
            "install.detect_optional_hardware",
            return_value={"pipower5": True},
        ):
            names = install.resolve_enabled_setting_names(args, peripherals=["pipower5"])

        self.assertIn("pipower5", names)

    def test_pipower5_flag_overrides_hardware_detection(self):
        import install

        args = install.parse_install_args(["--enable-ups"])
        with unittest.mock.patch(
            "install.detect_optional_hardware",
            return_value={"pipower5": False},
        ):
            names = install.resolve_enabled_setting_names(args, peripherals=[])

        self.assertIn("pipower5", names)

    def test_enable_ups_persists_runtime_optional_hardware(self):
        import install

        args = install.parse_install_args(["--enable-ups"])
        installer = install.build_installer_for_settings(["base"])

        install.apply_optional_hardware_install_settings(installer, args)

        self.assertEqual(installer.work_files[".enabled_optional_hardware"], "pipower5\n")

    def test_default_install_does_not_persist_optional_hardware(self):
        import install

        args = install.parse_install_args([])
        installer = install.build_installer_for_settings(["base"])

        install.apply_optional_hardware_install_settings(installer, args)

        self.assertNotIn(".enabled_optional_hardware", installer.work_files)

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

        installer = install.build_installer_for_settings(["base"])
        install.apply_variant_config_txt(installer, Pironman5ProMax)

        self.assertEqual(installer.config_txt["dtparam=spi"], "on")
        self.assertEqual(installer.config_txt["dtparam=i2c_arm"], "on")

    def test_oled_timeout_zero_is_documented_as_disable(self):
        with open("pironman5/_cli.py", "r", encoding="utf-8") as f:
            cli = f.read()

        self.assertIn("set to 0 to disable timeout", cli)
        self.assertIn("Set OLED sleep timeout: disabled", cli)

    def test_sunfounder_git_dependencies_are_pinned_to_commits(self):
        import install

        installer = install.build_installer_for_settings([
            "base",
            "dashboard",
            "pipower5",
        ])

        sunfounder_urls = [
            url for url in installer.python_source.values()
            if isinstance(url, str) and "github.com/sunfounder" in url
        ]

        self.assertGreater(len(sunfounder_urls), 0)
        for url in sunfounder_urls:
            ref = url.rsplit("@", 1)[-1]
            self.assertRegex(ref, r"^[0-9a-f]{40}$")

    def test_default_runtime_dependencies_use_reviewed_forks(self):
        import install

        installer = install.build_installer_for_settings(["base"])

        self.assertIn("github.com/geoffbelknap/pm_auto", installer.python_source["pm_auto"])
        self.assertNotIn("sf_rpi_status", installer.python_source)

    def test_dashboard_dependency_uses_reviewed_fork(self):
        import install

        installer = install.build_installer_for_settings(["dashboard"])

        self.assertIn("github.com/geoffbelknap/pm_dashboard", installer.python_source["pm_dashboard"])

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

        installer = install.build_installer_for_variant("mini")

        self.assertEqual({" .variant".strip(): "mini\n"}, installer.work_files)

    def test_print_variant_flag_is_parsed(self):
        import install

        args = install.parse_install_args(["--print-variant"])

        self.assertTrue(args.print_variant)

    def test_variant_help_lists_canonical_values(self):
        import install

        self.assertIn("auto, base, max, mini, nas, pro_max, ups", install.VARIANT_HELP)

    def test_gpio_settings_use_installer_preflight_actions(self):
        import install

        installer = install.build_installer_for_settings(["gpio"])

        self.assertIn("install_lgpio", installer.preflight_actions)
        self.assertIn("fix_kali_gpio_spi_groups", installer.preflight_actions)
        self.assertIn("RPi.GPIO", installer.custom_uninstall_pip_dependencies)
        self.assertIn("rpi.lgpio", installer.custom_pip_dependencies)
        self.assertNotIn("install_lgpio.sh", installer.before_install_scripts)
        self.assertNotIn("fix_kali_gpio_spi.sh", installer.before_install_scripts)
        self.assertNotIn("change_rpi.gpio_to_rpi.lgpio.sh", installer.after_install_scripts)

    def test_base_settings_use_installer_umbrel_preflight_action(self):
        import install

        installer = install.build_installer_for_settings(["base"])

        self.assertIn("apply_umbrel_patch", installer.preflight_actions)
        self.assertNotIn("umbrel_patch.sh", installer.before_install_scripts)

    def test_shared_preflight_actions_are_not_duplicated(self):
        import install

        installer = install.build_installer_for_settings(["gpio", "ws2812"])

        self.assertEqual(1, installer.preflight_actions.count("install_lgpio"))
        self.assertEqual(1, installer.preflight_actions.count("fix_kali_gpio_spi_groups"))


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

    def test_installer_does_not_add_installing_user_to_service_group(self):
        with open("tools/sf_installer.py", "r", encoding="utf-8") as f:
            installer = f.read()

        self.assertNotIn("self.add_user_to_group(current_user, self.user)", installer)

    def test_installer_does_not_create_group_writable_runtime_dirs(self):
        with open("tools/sf_installer.py", "r", encoding="utf-8") as f:
            installer = f.read()

        self.assertNotIn("chmod 775", installer)

    def test_installer_does_not_download_remote_dtoverlays(self):
        with open("tools/sf_installer.py", "r", encoding="utf-8") as f:
            installer = f.read()

        self.assertNotIn("wget {overlay}", installer)
        self.assertIn("Remote dtoverlay downloads are disabled", installer)

    def test_pipower5_install_verifies_release_archives(self):
        with open("scripts/setup_pipower5.sh", "r", encoding="utf-8") as f:
            script = f.read()

        self.assertIn("sha256sum -c", script)
        self.assertIn("0e346fb9fdeca94c5d2ca8f2388c494690576ef99b0aa1882f886a408db66d82", script)
        self.assertIn("7cc1bf3612c7bf4fcdf18846da9eeefc1043e16dd98a1262a1ac0afbfea1b868", script)


class InfluxDefaultPolicyTest(unittest.TestCase):
    def test_default_install_does_not_reference_influxdb_script(self):
        import install

        args = install.parse_install_args([])
        names = install.resolve_enabled_setting_names(args, peripherals=["oled"])
        installer = install.build_installer_for_settings(names)

        self.assertNotIn("install_influxdb.sh", installer.before_install_scripts)
        self.assertNotIn("influxdb", installer.groups)

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
