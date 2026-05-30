import json
import os
import stat
import tempfile
import unittest

from pironman5.security import redact_secrets, write_json_private


class SecretRedactionTest(unittest.TestCase):
    def test_redacts_sensitive_keys_recursively(self):
        config = {
            "system": {
                "smtp_email": "person@example.com",
                "smtp_password": "secret",
                "nested": {
                    "api_token": "abc123",
                    "normal": "visible",
                },
            }
        }

        redacted = redact_secrets(config)

        self.assertEqual(redacted["system"]["smtp_password"], "<redacted>")
        self.assertEqual(redacted["system"]["nested"]["api_token"], "<redacted>")
        self.assertEqual(redacted["system"]["nested"]["normal"], "visible")

    def test_write_json_private_creates_restrictive_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.json")
            write_json_private(path, {"system": {"debug_level": "INFO"}})

            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600)

            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["system"]["debug_level"], "INFO")

    def test_write_json_private_preserves_existing_owner_group_and_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"system": {"debug_level": "INFO"}}, f)
            os.chmod(path, 0o640)
            original = os.stat(path)

            write_json_private(path, {"system": {"debug_level": "DEBUG"}})

            updated = os.stat(path)
            self.assertEqual(original.st_uid, updated.st_uid)
            self.assertEqual(original.st_gid, updated.st_gid)
            self.assertEqual(0o640, stat.S_IMODE(updated.st_mode))
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["system"]["debug_level"], "DEBUG")


class LoggingDefaultTest(unittest.TestCase):
    def test_default_debug_level_is_warning(self):
        from pironman5._constants import DEFAULT_DEBUG_LEVEL

        self.assertEqual(DEFAULT_DEBUG_LEVEL, "WARNING")


class LegacyInstallerIsolationTest(unittest.TestCase):
    def test_install_module_does_not_import_legacy_installer_at_module_load(self):
        with open("install.py", "r", encoding="utf-8") as f:
            source = f.read()

        module_load_source = source.split("def build_installer", 1)[0]
        self.assertNotIn("tools.sf_installer", module_load_source)
