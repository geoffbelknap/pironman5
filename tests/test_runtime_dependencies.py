import pathlib
import unittest


class RuntimeDependencyBoundaryTest(unittest.TestCase):
    def test_runtime_does_not_import_sf_rpi_status(self):
        source_files = [
            pathlib.Path("pironman5/pironman5.py"),
            pathlib.Path("pironman5/__init__.py"),
        ]

        for source_file in source_files:
            with self.subTest(source_file=source_file):
                self.assertNotIn("sf_rpi_status", source_file.read_text(encoding="utf-8"))

    def test_missing_dashboard_is_logged_as_optional(self):
        source = pathlib.Path("pironman5/pironman5.py").read_text(encoding="utf-8")

        self.assertIn("self.log.info('PM Dashboard not installed; skipping optional dashboard startup')", source)
        self.assertNotIn("self.log.warning('PM Dashboard not found skipping')", source)


if __name__ == "__main__":
    unittest.main()
