import tempfile
import unittest
from pathlib import Path
from unittest import mock


class LaunchBrowserTest(unittest.TestCase):
    def test_chromium_args_use_private_profile_without_password_store(self):
        from pironman5 import _launch_browser

        with mock.patch.object(_launch_browser, "get_url", return_value="http://localhost:34001/small"):
            with mock.patch.object(_launch_browser, "get_browser_profile_dir", return_value="/tmp/pironman5-browser"):
                args = _launch_browser.get_browser_fullscreen_args("chromium")

        self.assertIn("--user-data-dir=/tmp/pironman5-browser", args)
        self.assertNotIn("--password-store=basic", args)
        self.assertNotIn("--password-manager=disabled", args)

    def test_firefox_args_use_private_profile(self):
        from pironman5 import _launch_browser

        with mock.patch.object(_launch_browser, "get_url", return_value="http://localhost:34001/small"):
            with mock.patch.object(_launch_browser, "get_browser_profile_dir", return_value="/tmp/pironman5-browser"):
                args = _launch_browser.get_browser_fullscreen_args("firefox")

        self.assertIn("--profile", args)
        self.assertIn("/tmp/pironman5-browser", args)
        self.assertNotIn("--password-manager=disabled", args)

    def test_browser_profile_dir_is_private(self):
        from pironman5 import _launch_browser

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(_launch_browser.os.environ, {"XDG_RUNTIME_DIR": tmpdir}, clear=False):
                profile_dir = Path(_launch_browser.get_browser_profile_dir())

            self.assertEqual(profile_dir, Path(tmpdir) / "pironman5-browser")
            self.assertEqual(profile_dir.stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
