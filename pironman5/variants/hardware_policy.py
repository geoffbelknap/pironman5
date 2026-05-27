OPTIONAL_HARDWARE_MODULES = {
    "pipower5": {
        "modules": {"pipower5", "oled_ups_pages"},
        "hardware": "pipower5",
    },
}


def normalize_enabled_optional_hardware(enabled_optional_hardware=None):
    if enabled_optional_hardware is None:
        return set()
    if isinstance(enabled_optional_hardware, str):
        return {item.strip() for item in enabled_optional_hardware.split(",") if item.strip()}
    return {item for item in enabled_optional_hardware if item}


def filter_enabled_modules(module_names, detected_hardware=None, enabled_optional_hardware=None):
    detected_hardware = detected_hardware or {}
    enabled_optional_hardware = normalize_enabled_optional_hardware(enabled_optional_hardware)
    disabled_modules = set()

    for hardware_name, policy in OPTIONAL_HARDWARE_MODULES.items():
        if detected_hardware.get(policy["hardware"]) or hardware_name in enabled_optional_hardware:
            continue
        disabled_modules.update(policy["modules"])

    return [module_name for module_name in module_names if module_name not in disabled_modules]
