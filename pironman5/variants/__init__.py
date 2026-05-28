from os import path, listdir, getenv

from .hardware_policy import (
    filter_enabled_modules,
    normalize_enabled_optional_hardware,
    probe_gpio_chip,
    probe_i2c_bus,
    probe_pwm,
    probe_rtl8125,
    probe_spi0,
)
from .modules import assemble
from .products import PRODUCT_DEFINITIONS

DEFAULT_PART_NUMBER = "0306V10"

VARIANT_ALIASES = {
    "base": "base",
    "pironman5": "base",
    "pironman-5": "base",
    "max": "max",
    "pironman5-max": "max",
    "pironman-5-max": "max",
    "mini": "mini",
    "pironman5-mini": "mini",
    "pironman-5-mini": "mini",
    "nas": "nas",
    "pironman5-nas": "nas",
    "pironman-5-nas": "nas",
    "ups": "ups",
    "pironman5-ups": "ups",
    "pironman-5-ups": "ups",
    "pro_max": "pro_max",
    "pro-max": "pro_max",
    "promax": "pro_max",
    "pironman5-pro-max": "pro_max",
    "pironman-5-pro-max": "pro_max",
}


def normalize_variant_key(variant):
    if variant is None:
        return None
    if not isinstance(variant, str):
        return None
    key = variant.strip().lower()
    return VARIANT_ALIASES.get(key, key)


def get_product_definition(variant):
    key = normalize_variant_key(variant)
    if key not in PRODUCT_DEFINITIONS:
        return None
    return PRODUCT_DEFINITIONS[key]


def get_variant_choices():
    return sorted(VARIANT_ALIASES)


# --- HAT EEPROM detection (unchanged) ---

def get_device_tree_path():
    device_tree_path = '/proc/device-tree'
    if not path.exists(device_tree_path):
        device_tree_path = '/device-tree'
        if not path.exists(device_tree_path):
            return None
    return device_tree_path


def read_device_tree_file(file_path):
    if not path.exists(file_path):
        return None
    with open(file_path, "r") as f:
        result = f.read()[:-1]
        result = int(result, 16)
        return result


def get_part_number():
    device_tree_path = get_device_tree_path()
    part_number = ""
    if device_tree_path is None:
        return
    hat_path = None
    for file in listdir(device_tree_path):
        if file.startswith('hat'):
            hat_path = f"{device_tree_path}/{file}"
            break
    if hat_path is None:
        return
    product_id_file = f"{hat_path}/product_id"
    product_ver_file = f"{hat_path}/product_ver"

    try:
        product_id = read_device_tree_file(product_id_file)
        product_ver = read_device_tree_file(product_ver_file)
        if product_id is None or product_ver is None:
            return
        part_number = f"{product_id:04d}V{product_ver:02d}"
    except Exception:
        pass
    return part_number


def get_varient_id_and_version():
    part_number = getenv('PIRONMAN5_PART_NUMBER', None)
    if part_number is None:
        part_number = get_part_number()
    if part_number is None:
        part_number = DEFAULT_PART_NUMBER
    varient_id = part_number.split('V')[0]
    version_id = part_number.split('V')[1]
    return varient_id, version_id


def split_part_number(part_number):
    if not part_number or "V" not in part_number:
        return None, None
    variant_id, version = part_number.split("V", 1)
    return variant_id, version


def get_variant(variant_id, version=None):
    if variant_id == "0306":
        if version == "10":
            return "base"
        else:
            return "max"
    elif variant_id == "0308":
        return "mini"
    elif variant_id == "0312":
        return "nas"
    elif variant_id == "2602":
        return "ups"
    elif variant_id == "0316":
        return "pro_max"
    else:
        return None


def detect_hardware_variant():
    part_number = getenv("PIRONMAN5_PART_NUMBER")
    source = "environment"
    if part_number is None:
        part_number = get_part_number()
        source = "hat-eeprom"
    if part_number is None:
        part_number = DEFAULT_PART_NUMBER
        source = "fallback"
    variant_id, version = split_part_number(part_number)
    variant = get_variant(variant_id, version) or "base"
    return {
        "variant": variant,
        "source": source,
        "part_number": part_number,
        "variant_id": variant_id,
        "version": version,
    }


def detect_optional_hardware():
    detected = detect_hardware_variant()
    is_hat_eeprom = detected["source"] == "hat-eeprom"
    return {
        "pipower5": is_hat_eeprom and detected["variant_id"] == "2602",
        "pironman_mcu": is_hat_eeprom and detected["variant_id"] == "0312",
        "rtl8125": probe_rtl8125(),
        "i2c_bus": probe_i2c_bus(),
        "spi0": probe_spi0(),
        "gpio_chip": probe_gpio_chip(),
        "pwm": probe_pwm(),
    }


def _detect_variant_key():
    env_variant = getenv("PIRONMAN5_VARIANT")
    if env_variant:
        return normalize_variant_key(env_variant)

    variant_path = "/opt/pironman5/.variant"
    if path.exists(variant_path):
        with open(variant_path, "r") as f:
            variant = normalize_variant_key(f.read())
            if variant:
                return variant

    return detect_hardware_variant()["variant"]


def _custom_modules():
    custom_path = "/opt/pironman5/.custom_module"
    if not path.exists(custom_path):
        return []
    with open(custom_path) as f:
        modules = [
            line.strip() for line in f
            if line.strip() and not line.strip().startswith("#")
        ]
    return modules


def _enabled_optional_hardware():
    enabled = normalize_enabled_optional_hardware(getenv("PIRONMAN5_ENABLE_OPTIONAL_HARDWARE"))
    enabled_path = "/opt/pironman5/.enabled_optional_hardware"
    if path.exists(enabled_path):
        with open(enabled_path) as f:
            enabled.update(
                line.strip() for line in f
                if line.strip() and not line.strip().startswith("#")
            )
    return enabled


# --- Assembly ---

_variant_key = _detect_variant_key()
_product = PRODUCT_DEFINITIONS.get(_variant_key, PRODUCT_DEFINITIONS["base"])

_module_names = list(_product["modules"])
_custom = _custom_modules()
for m in _custom:
    if m not in _module_names:
        _module_names.append(m)
_module_names = filter_enabled_modules(
    _module_names,
    detected_hardware=detect_optional_hardware(),
    enabled_optional_hardware=_enabled_optional_hardware(),
)
_assembled = assemble(_module_names)

_config = dict(_assembled["default_config"])
_config.update(_product.get("config_overrides", {}))

if "event_map_replace" in _product:
    _event_map = dict(_product["event_map_replace"])
else:
    _event_map = dict(_assembled["event_map"])
    _event_map.update(_product.get("event_map_overrides", {}))

# --- Exports (same names as before) ---

NAME = _product["name"]
ID = _product["id"]
PRODUCT_VERSION = _product["product_version"]
PERIPHERALS = list(_assembled["peripherals"])
SYSTEM_DEFAULT_CONFIG = _config
EVENT_MAP = _event_map
DT_OVERLAYS = _product["dt_overlays"]
VARIENT = _variant_key
