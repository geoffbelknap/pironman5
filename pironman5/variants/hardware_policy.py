from os import listdir, path


OPTIONAL_HARDWARE_MODULES = {
    "pipower5": {
        "modules": {"pipower5", "oled_ups_pages"},
        "hardware": "pipower5",
    },
}

REALTEK_VENDOR_ID = "0x10ec"
RTL8125_DEVICE_IDS = {"0x8125"}


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


def _read_sysfs_id(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip().lower()
    except OSError:
        return None


def probe_device_node(device_path):
    return path.exists(device_path)


def probe_i2c_bus(dev_root="/dev", bus=1):
    return probe_device_node(path.join(dev_root, f"i2c-{bus}"))


def probe_spi0(dev_root="/dev"):
    return probe_device_node(path.join(dev_root, "spidev0.0"))


def probe_gpio_chip(dev_root="/dev", chip=0):
    return probe_device_node(path.join(dev_root, f"gpiochip{chip}"))


def probe_pwm(sysfs_root="/sys/class/pwm"):
    try:
        device_names = listdir(sysfs_root)
    except OSError:
        return False
    return any(device_name.startswith("pwmchip") for device_name in device_names)


def probe_rtl8125(sysfs_root="/sys/bus/pci/devices"):
    try:
        device_names = listdir(sysfs_root)
    except OSError:
        return False

    for device_name in device_names:
        device_path = path.join(sysfs_root, device_name)
        vendor = _read_sysfs_id(path.join(device_path, "vendor"))
        device = _read_sysfs_id(path.join(device_path, "device"))
        if vendor == REALTEK_VENDOR_ID and device in RTL8125_DEVICE_IDS:
            return True
    return False
