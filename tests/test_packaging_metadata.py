import pathlib
import sys
import unittest


if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class PackagingMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pyproject = pathlib.Path("pyproject.toml")
        cls.data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    def test_core_runtime_dependencies_are_declared(self):
        dependencies = set(self.data["project"]["dependencies"])

        expected = {
            "psutil",
            "Pillow",
            "smbus2",
            "evdev",
            "rpi.lgpio",
            "adafruit-circuitpython-neopixel-spi",
            "adafruit_platformdetect",
            "Adafruit-Blinka==8.59.0",
            "adafruit-circuitpython-typing",
            "Adafruit-PureIO>=1.1.7",
            "pyftdi>=0.40.0",
        }

        self.assertTrue(expected.issubset(dependencies))
        self.assertFalse(any("sf_rpi_status" in dependency for dependency in dependencies))
        self.assertFalse(any("pm_auto" in dependency for dependency in dependencies))

    def test_optional_dependency_extras_are_declared(self):
        optional = self.data["project"]["optional-dependencies"]

        self.assertIn("dashboard", optional)
        self.assertIn(
            "pm_dashboard @ git+https://github.com/geoffbelknap/pm_dashboard.git@7a347dd84115949e916811cfe536172cb44cadf0",
            optional["dashboard"],
        )
        self.assertIn("ups", optional)
        self.assertIn(
            "pipower5 @ git+https://github.com/sunfounder/pipower5.git@46250a12e2e6b4b9e1f3d7e3787d02a2aaf1b373",
            optional["ups"],
        )
        self.assertIn("rgb-matrix", optional)
        self.assertIn("numpy", optional["rgb-matrix"])
        self.assertIn("legacy-ups", optional)
        self.assertNotIn("legacy-hardware", optional)
        self.assertIn(
            "pm_auto @ git+https://github.com/geoffbelknap/pm_auto.git@b00dd490ce498e963c352876801b5cb4e59c4bd2",
            optional["legacy-ups"],
        )

    def test_legacy_influxdb_is_not_installed_by_package_metadata(self):
        serialized = str(self.data["project"])

        self.assertNotIn("influxdb", serialized.lower())

    def test_dashboard_is_optional_and_not_installed_by_default(self):
        dependencies = self.data["project"]["dependencies"]

        self.assertFalse(any("pm_dashboard" in dependency for dependency in dependencies))

    def test_project_metadata_identifies_this_fork(self):
        project = self.data["project"]

        self.assertEqual(project["description"], "Pironman 5 Raspberry Pi case service and CLI")
        self.assertIn({"name": "Geoff Belknap"}, project["maintainers"])
        self.assertEqual(project["urls"]["Homepage"], "https://github.com/geoffbelknap/pironman5")
        self.assertEqual(project["urls"]["Source"], "https://github.com/geoffbelknap/pironman5")

    def test_package_init_does_not_contain_legacy_cli(self):
        source = pathlib.Path("pironman5/__init__.py").read_text(encoding="utf-8")

        self.assertNotIn("def main(", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("current_config['system']", source)

    def test_version_identifies_geoffbelknap_fork(self):
        from pironman5.version import __version__

        self.assertIn("+geoffbelknap.", __version__)


if __name__ == "__main__":
    unittest.main()
