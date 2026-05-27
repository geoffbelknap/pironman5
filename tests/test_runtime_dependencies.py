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

    def test_local_sf_rpi_status_compatibility_shim_is_packaged(self):
        import sf_rpi_status

        required = [
            "get_cpu_temperature",
            "get_cpu_percent",
            "get_disks_info",
            "get_network_speed",
            "shutdown",
        ]

        for name in required:
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(sf_rpi_status, name)))

    def test_pyproject_packages_local_compatibility_shim(self):
        pyproject = pathlib.Path("pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('"sf_rpi_status"', pyproject)


if __name__ == "__main__":
    unittest.main()
