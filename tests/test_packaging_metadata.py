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
            "pm_auto @ git+https://github.com/geoffbelknap/pm_auto.git@b00dd490ce498e963c352876801b5cb4e59c4bd2",
            "sf_rpi_status @ git+https://github.com/geoffbelknap/sf_rpi_status.git@cc9841628913a01315c009e72df5cec2bc4f45af",
        }

        self.assertTrue(expected.issubset(dependencies))

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

    def test_legacy_influxdb_is_not_installed_by_package_metadata(self):
        serialized = str(self.data["project"])

        self.assertNotIn("influxdb", serialized.lower())


if __name__ == "__main__":
    unittest.main()
