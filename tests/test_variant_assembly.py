import importlib
import os
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
