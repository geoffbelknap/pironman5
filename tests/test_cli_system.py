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


if __name__ == "__main__":
    unittest.main()
