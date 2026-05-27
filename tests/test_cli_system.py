import contextlib
import io
import sys
import unittest
from unittest import mock


class SystemCliTest(unittest.TestCase):
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

    def test_system_setup_refresh_venv_reinstalls_service_environment(self):
        from pironman5 import _cli

        stdout = io.StringIO()
        argv = ["pironman5", "system", "setup", "--variant", "max", "--refresh-venv", "--dry-run"]
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(stdout):
                _cli.main()

        output = stdout.getvalue()
        self.assertIn("rm -rf /opt/pironman5-venv", output)
        self.assertIn("python3 -m venv /opt/pironman5-venv", output)
        self.assertIn("/opt/pironman5-venv/bin/pip install --upgrade", output)

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
        argv = ["pironman5", "system", "upgrade-service", "--dry-run"]
        with mock.patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(stdout):
                _cli.main()

        output = stdout.getvalue()
        self.assertIn("rm -rf /opt/pironman5-venv", output)
        self.assertIn("python3 -m venv /opt/pironman5-venv", output)
        self.assertIn("/opt/pironman5-venv/bin/pip install --upgrade", output)
        self.assertIn("systemctl restart pironman5.service", output)

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
        self.assertIn("system upgrade-service", readme)
        self.assertIn("pipx reinstall pironman5", readme)
        self.assertNotIn("moving toward a split install model", readme)


if __name__ == "__main__":
    unittest.main()
