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


class LoggingDefaultTest(unittest.TestCase):
    def test_default_debug_level_is_warning(self):
        from pironman5._constants import DEFAULT_DEBUG_LEVEL

        self.assertEqual(DEFAULT_DEBUG_LEVEL, "WARNING")
