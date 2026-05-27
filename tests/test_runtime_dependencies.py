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

    def test_local_sf_rpi_status_compatibility_shim_is_not_packaged(self):
        pyproject = pathlib.Path("pyproject.toml").read_text(encoding="utf-8")

        self.assertNotIn('"sf_rpi_status"', pyproject)

    def test_pironman_runtime_does_not_instantiate_pm_auto_directly(self):
        source = pathlib.Path("pironman5/pironman5.py").read_text(encoding="utf-8")

        self.assertNotIn("from pm_auto.pm_auto import PMAuto", source)
        self.assertIn("from .runtime import PironmanRuntime", source)

    def test_ws2812_cli_uses_local_runtime_constants(self):
        source = pathlib.Path("pironman5/_cli.py").read_text(encoding="utf-8")

        self.assertIn("from .runtime import RGB_STYLES", source)
        self.assertNotIn("from pm_auto.addons.ws2812 import RGB_STYLES", source)

    def test_gpio_fan_cli_uses_local_runtime_constants(self):
        source = pathlib.Path("pironman5/_cli.py").read_text(encoding="utf-8")

        self.assertIn("from .runtime import GPIO_FAN_MODES", source)
        self.assertNotIn("from pm_auto.addons.fan import GPIO_FAN_MODES", source)


if __name__ == "__main__":
    unittest.main()
