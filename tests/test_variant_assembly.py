import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def reload_variants():
    for name in list(sys.modules):
        if name == "pironman5.variants" or name.startswith("pironman5.variants."):
            del sys.modules[name]
    return importlib.import_module("pironman5.variants")


class VariantAssemblyTest(unittest.TestCase):
    def test_all_products_assemble(self):
        from pironman5.variants.modules import assemble
        from pironman5.variants.products import PRODUCT_DEFINITIONS

        self.assertGreaterEqual(len(PRODUCT_DEFINITIONS), 4)
        for key, product in PRODUCT_DEFINITIONS.items():
            with self.subTest(key=key):
                result = assemble(product["modules"])
                self.assertIsInstance(result["peripherals"], list)
                self.assertIsInstance(result["default_config"], dict)
                self.assertIsInstance(result["event_map"], dict)
                self.assertGreater(len(result["peripherals"]), 0)

    def test_dependency_resolution_orders_dependencies_first(self):
        from pironman5.variants.modules import resolve_dependencies

        resolved = resolve_dependencies(["gpio_fan_led"])

        self.assertIn("gpio_fan", resolved)
        self.assertIn("gpio_fan_led", resolved)
        self.assertLess(resolved.index("gpio_fan"), resolved.index("gpio_fan_led"))

    def test_duplicate_module_names_do_not_duplicate_peripherals(self):
        from pironman5.variants.modules import assemble

        result = assemble(["core", "core", "core"])

        self.assertEqual(1, result["peripherals"].count("storage"))

    def test_unknown_module_raises_key_error(self):
        from pironman5.variants.modules import get

        with self.assertRaises(KeyError):
            get("unknown-module")

    def test_part_number_mapping_matches_known_variants(self):
        from pironman5.variants import get_variant

        self.assertEqual("base", get_variant("0306", "10"))
        self.assertEqual("max", get_variant("0306", "11"))
        self.assertEqual("mini", get_variant("0308", "10"))
        self.assertEqual("nas", get_variant("0312", "10"))
        self.assertEqual("ups", get_variant("2602", "10"))
        self.assertEqual("pro_max", get_variant("0316", "10"))

    def test_environment_variant_override_wins(self):
        with mock.patch.dict(os.environ, {"PIRONMAN5_VARIANT": "mini"}, clear=False):
            variants = reload_variants()

        self.assertEqual("mini", variants.VARIENT)
        self.assertEqual("Pironman 5 Mini", variants.NAME)

    def test_hardware_detection_ignores_runtime_environment_override(self):
        with mock.patch.dict(os.environ, {"PIRONMAN5_VARIANT": "mini"}, clear=False):
            variants = reload_variants()
            with mock.patch.object(variants, "get_part_number", return_value="0306V11"):
                detected = variants.detect_hardware_variant()

        self.assertEqual("max", detected["variant"])
        self.assertEqual("hat-eeprom", detected["source"])
        self.assertEqual("0306V11", detected["part_number"])

    def test_hardware_detection_falls_back_to_base(self):
        from pironman5 import variants

        with mock.patch.object(variants, "get_part_number", return_value=None):
            detected = variants.detect_hardware_variant()

        self.assertEqual("base", detected["variant"])
        self.assertEqual("fallback", detected["source"])
        self.assertEqual("0306V10", detected["part_number"])

    def test_hardware_detection_can_be_overridden_for_tests(self):
        with mock.patch.dict(os.environ, {"PIRONMAN5_PART_NUMBER": "0312V10"}, clear=False):
            variants = reload_variants()
            detected = variants.detect_hardware_variant()

        self.assertEqual("nas", detected["variant"])
        self.assertEqual("environment", detected["source"])
        self.assertEqual("0312V10", detected["part_number"])

    def test_optional_hardware_detects_pipower5_hat(self):
        from pironman5 import variants

        with mock.patch.object(
            variants,
            "detect_hardware_variant",
            return_value={"variant": "ups", "variant_id": "2602", "source": "hat-eeprom"},
        ):
            detected = variants.detect_optional_hardware()

        self.assertTrue(detected["pipower5"])

    def test_optional_hardware_ignores_fallback_variant(self):
        from pironman5 import variants

        with mock.patch.object(
            variants,
            "detect_hardware_variant",
            return_value={"variant": "ups", "variant_id": "2602", "source": "fallback"},
        ):
            detected = variants.detect_optional_hardware()

        self.assertFalse(detected["pipower5"])

    def test_rtl8125_probe_detects_realtek_pci_device(self):
        from pironman5.variants.hardware_policy import probe_rtl8125

        with tempfile.TemporaryDirectory() as tmpdir:
            device = Path(tmpdir) / "0000:01:00.0"
            device.mkdir()
            (device / "vendor").write_text("0x10ec\n", encoding="utf-8")
            (device / "device").write_text("0x8125\n", encoding="utf-8")

            self.assertTrue(probe_rtl8125(tmpdir))

    def test_rtl8125_probe_ignores_other_realtek_pci_devices(self):
        from pironman5.variants.hardware_policy import probe_rtl8125

        with tempfile.TemporaryDirectory() as tmpdir:
            device = Path(tmpdir) / "0000:01:00.0"
            device.mkdir()
            (device / "vendor").write_text("0x10ec\n", encoding="utf-8")
            (device / "device").write_text("0x8168\n", encoding="utf-8")

            self.assertFalse(probe_rtl8125(tmpdir))

    def test_optional_hardware_reports_rtl8125_probe(self):
        from pironman5 import variants

        with mock.patch.object(variants, "probe_rtl8125", return_value=True):
            detected = variants.detect_optional_hardware()

        self.assertTrue(detected["rtl8125"])

    def test_capability_policy_filters_pipower5_from_profile_without_detection(self):
        from pironman5.variants.hardware_policy import filter_enabled_modules
        from pironman5.variants.products import PRODUCT_DEFINITIONS

        modules = filter_enabled_modules(
            PRODUCT_DEFINITIONS["ups"]["modules"],
            detected_hardware={"pipower5": False},
            enabled_optional_hardware=[],
        )

        self.assertNotIn("pipower5", modules)
        self.assertNotIn("oled_ups_pages", modules)
        self.assertIn("oled", modules)

    def test_capability_policy_keeps_pipower5_when_hat_is_detected(self):
        from pironman5.variants.hardware_policy import filter_enabled_modules
        from pironman5.variants.products import PRODUCT_DEFINITIONS

        modules = filter_enabled_modules(
            PRODUCT_DEFINITIONS["ups"]["modules"],
            detected_hardware={"pipower5": True},
            enabled_optional_hardware=[],
        )

        self.assertIn("pipower5", modules)
        self.assertIn("oled_ups_pages", modules)

    def test_capability_policy_keeps_pipower5_when_explicitly_enabled(self):
        from pironman5.variants.hardware_policy import filter_enabled_modules
        from pironman5.variants.products import PRODUCT_DEFINITIONS

        modules = filter_enabled_modules(
            PRODUCT_DEFINITIONS["ups"]["modules"],
            detected_hardware={"pipower5": False},
            enabled_optional_hardware=["pipower5"],
        )

        self.assertIn("pipower5", modules)
        self.assertIn("oled_ups_pages", modules)

    def test_runtime_profile_filters_pipower5_without_detection(self):
        with mock.patch.dict(
            os.environ,
            {"PIRONMAN5_VARIANT": "ups", "PIRONMAN5_PART_NUMBER": "0306V10"},
            clear=False,
        ):
            variants = reload_variants()

        self.assertNotIn("pipower5", variants.PERIPHERALS)
        self.assertNotIn("send_email", variants.PERIPHERALS)

    def test_runtime_profile_allows_explicit_pipower5_override(self):
        with mock.patch.dict(
            os.environ,
            {
                "PIRONMAN5_VARIANT": "ups",
                "PIRONMAN5_PART_NUMBER": "0306V10",
                "PIRONMAN5_ENABLE_OPTIONAL_HARDWARE": "pipower5",
            },
            clear=False,
        ):
            variants = reload_variants()

        self.assertIn("pipower5", variants.PERIPHERALS)
        self.assertIn("send_email", variants.PERIPHERALS)


if __name__ == "__main__":
    unittest.main()
