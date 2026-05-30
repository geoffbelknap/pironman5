import contextlib
import io
import sys
import unittest
import unittest.mock
from pathlib import Path


class PackageSetupPolicyTest(unittest.TestCase):
    def test_oled_timeout_zero_is_documented_as_disable(self):
        with open("pironman5/_cli.py", "r", encoding="utf-8") as f:
            cli = f.read()

        self.assertIn("set to 0 to disable timeout", cli)
        self.assertIn("Set OLED sleep timeout: disabled", cli)

    def test_setup_dry_run_uses_package_cli_flow(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        argv = ["pironman5", "setup", "--variant", "max", "--dry-run"]
        with unittest.mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(stdout):
                _cli.main()

        output = stdout.getvalue()
        self.assertIn("Pironman 5 setup dry run", output)
        self.assertIn("/opt/pironman5-venv", output)
        self.assertIn("pironman5.service", output)
        self.assertNotIn("install.py", output)
        self.assertNotIn('$(command -v pironman5)', output)

    def test_setup_rejects_legacy_influxdb_flag(self):
        from pironman5 import _cli

        argv = ["pironman5", "setup", "--enable-influxdb-legacy"]
        with unittest.mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    _cli.main()


class DeadCodePolicyTest(unittest.TestCase):
    def test_legacy_install_script_is_removed(self):
        self.assertFalse(Path("install.py").exists())

    def test_readme_does_not_document_legacy_install_script(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertNotIn("install.py", readme)

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
        from pironman5 import system

        _variant_key, commands = system.setup_commands("ups", enabled_optional_hardware=["pipower5"])
        command_text = "\n".join(command.shell() for command in commands)

        self.assertNotIn("setup_pipower5.sh", command_text)

    def test_pipower5_install_does_not_download_email_templates(self):
        with open("scripts/setup_pipower5.sh", "r", encoding="utf-8") as f:
            script = f.read()

        self.assertNotIn("email_templates", script)
        self.assertNotIn("/opt/pipower5", script)

    def test_rtl8125_setup_is_not_run_by_installer(self):
        from pironman5 import system

        _variant_key, commands = system.setup_commands("nas")
        command_text = "\n".join(command.shell() for command in commands)

        self.assertNotIn("setup_rtl8125.sh", command_text)

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
        from pironman5 import system

        _variant_key, commands = system.setup_commands("max")
        command_text = "\n".join(command.shell() for command in commands)

        self.assertNotIn("install_influxdb.sh", command_text)
        self.assertNotIn("influxdb", command_text.lower())

    def test_legacy_influxdb_flag_is_not_supported(self):
        from pironman5 import _cli

        argv = ["pironman5", "setup", "--enable-influxdb-legacy"]
        with unittest.mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    _cli.main()

    def test_remove_dashboard_does_not_manage_influxdb(self):
        with open("pironman5/_cli.py", "r", encoding="utf-8") as f:
            cli = f.read()

        self.assertNotIn("influxdb", cli.lower())


if __name__ == "__main__":
    unittest.main()
