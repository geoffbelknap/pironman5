import unittest

from tools.sf_installer import SF_Installer


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

    def test_legacy_influxdb_requires_explicit_flag(self):
        import install

        args = install.parse_install_args(["--enable-dashboard", "--enable-influxdb-legacy"])
        names = install.resolve_enabled_setting_names(args, peripherals=["oled"])

        self.assertIn("dashboard", names)
        self.assertIn("influxdb_legacy", names)

    def test_ups_requires_explicit_flag_even_when_peripheral_exists(self):
        import install

        args = install.parse_install_args([])
        names = install.resolve_enabled_setting_names(args, peripherals=["pipower5"])

        self.assertNotIn("pipower5", names)

        args = install.parse_install_args(["--enable-ups"])
        names = install.resolve_enabled_setting_names(args, peripherals=["pipower5"])

        self.assertIn("pipower5", names)


class ServiceHardeningTest(unittest.TestCase):
    def test_service_runs_as_pironman5_user(self):
        with open("bin/pironman5.service", "r", encoding="utf-8") as f:
            service = f.read()

        self.assertIn("User=pironman5", service)
        self.assertIn("Group=pironman5", service)
        self.assertNotIn("User=root", service)
        self.assertNotIn("Group=root", service)

    def test_installer_does_not_add_installing_user_to_service_group(self):
        with open("tools/sf_installer.py", "r", encoding="utf-8") as f:
            installer = f.read()

        self.assertNotIn("self.add_user_to_group(current_user, self.user)", installer)


class InfluxDefaultPolicyTest(unittest.TestCase):
    def test_default_install_does_not_reference_influxdb_script(self):
        import install

        args = install.parse_install_args([])
        names = install.resolve_enabled_setting_names(args, peripherals=["oled"])
        installer = install.build_installer_for_settings(names)

        self.assertNotIn("install_influxdb.sh", installer.before_install_scripts)
        self.assertNotIn("influxdb", installer.groups)

    def test_legacy_influxdb_flag_adds_influxdb_script(self):
        import install

        args = install.parse_install_args(["--enable-dashboard", "--enable-influxdb-legacy"])
        names = install.resolve_enabled_setting_names(args, peripherals=["oled"])
        installer = install.build_installer_for_settings(names)

        self.assertIn("install_influxdb.sh", installer.before_install_scripts)
        self.assertIn("influxdb", installer.groups)


if __name__ == "__main__":
    unittest.main()
