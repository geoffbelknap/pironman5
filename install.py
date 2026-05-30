#!/usr/bin/env python3

import argparse

from pironman5.version import __version__
from pironman5.variants import (
    NAME,
    PERIPHERALS,
    VARIENT,
    PRODUCT_DEFINITIONS,
    detect_hardware_variant,
    detect_optional_hardware,
    get_product_definition,
    normalize_variant_key,
)
from pironman5.variants.hardware_policy import OPTIONAL_HARDWARE_CHOICES, normalize_optional_hardware_name
from pironman5.variants.modules import assemble

PM_AUTO_REF = 'b00dd490ce498e963c352876801b5cb4e59c4bd2'  # geoffbelknap/pironman5-1.4.7-hardened
DASHBOARD_REF = '7a347dd84115949e916811cfe536172cb44cadf0'  # geoffbelknap/pironman5-1.4.0-hardened
PIPOWER5_REF = '46250a12e2e6b4b9e1f3d7e3787d02a2aaf1b373'  # 1.2.3
SPC_REF = '3581063092fe669e7a5538f4a4dc67e9b766863c'
VARIANT_HELP = f"Install for a specific Pironman variant; default: auto. Valid: auto, {', '.join(sorted(PRODUCT_DEFINITIONS))}"

settings = {
    # - Setup venv options if needed, default to []
    'venv_options': [
        '--system-site-packages',
    ],

    'groups': [],

    'preflight_actions': [
        "apply_umbrel_patch",
    ],

    # - Install from apt
    'apt_dependencies': [
        'python3-dev',
    ],

    # - Install from pip
    'pip_dependencies': [
        'psutil',
    ],

    # - Install python source code from git
    'python_source': {
        'pironman5': './',
        'pm_auto': f'git+https://github.com/geoffbelknap/pm_auto.git@{PM_AUTO_REF}',
    },

    # create symbolic links from venv/bin/ to /usr/local/bin/
    'symlinks':
    [
        'pironman5',
    ],

    # - Setup config txt
    # 'config_txt':  {
    #     'dtparam=spi': 'on',
    #     'dtparam=i2c_arm': 'on',
    #     'dtoverlay=gpio-ir,gpio_pin': '13',
    # },

    # add modules
    # sudo nano /etc/modules
    # 'modules': [
    #     "i2c-dev",
    # ],

    # - Autostart settings
    # - Set service filenames
    'service_files': ['pironman5.service'],
    # - Set bin files
    'bin_files': [],

    # - Copy device tree overlay to /boot/overlays
    'dtoverlays': [],
}

ws2812_settings = {
    'preflight_actions': [
        "install_lgpio",
        "fix_kali_gpio_spi_groups",
    ],
    'groups': ['spi', 'gpio'],
    'pip_dependencies': [
        'adafruit-circuitpython-neopixel-spi',
        'adafruit_platformdetect',
        'Adafruit-Blinka==8.59.0',
        'rpi.lgpio',
        'adafruit-circuitpython-typing',
        'Adafruit-PureIO>=1.1.7',
        'pyftdi>=0.40.0',
    ],
}

oled_settings = {
    'groups': ['i2c'],
    'apt_dependencies': [
        'libjpeg-dev', # for Pillow on 32 bit OS
        'libfreetype6-dev', # for Pillow on 32 bit OS
        'libopenjp2-7', # for Pillow on 32 bit OS
        'kmod',
        'i2c-tools',
    ],
    'pip_dependencies': [
        'Pillow',
        'smbus2',
    ],
    'modules': [
        "i2c-dev",
    ],
}

gpio_settings = {
    'preflight_actions': [
        "install_lgpio",
        "fix_kali_gpio_spi_groups",
    ],
    'groups': ['gpio'],
    # - Install from apt
    'uninstall_pip_dependencies': [
        'RPi.GPIO',
    ],
    # - Install from pip
    'pip_dependencies': [
        'rpi.lgpio',
    ],
}

pi5_power_button_settings = {
    'apt_dependencies': [
        'build-essential',
        'gcc',
        'g++',
        'python3-dev',
    ],
    'groups': ['input'],
    'pip_dependencies': [
        'evdev',
    ],
}

rgb_matrix_settings = {
    'groups': ['i2c'],
    'pip_dependencies': [
        'smbus2',
        'numpy',
    ],
}

dashboard_settings = {
    'python_source': {
        'pm_dashboard': f'git+https://github.com/geoffbelknap/pm_dashboard.git@{DASHBOARD_REF}',
    },
}

pipower5_settings = {
    # Install python packages from source
    'groups': ['i2c', 'pipower5'],
    'python_source': {
        'pipower5': f'git+https://github.com/sunfounder/pipower5.git@{PIPOWER5_REF}',
        'spc': f'git+https://github.com/sunfounder/spc.git@{SPC_REF}',
    },
    # Add symbolic links
    'symlinks': [
        'pipower5',
    ],
    # - Copy device tree overlay to /boot/overlays
    'dtoverlays': [
        'sunfounder-pipower5.dtbo',
    ],
}

rtl8125_settings = {
    # RTL8125 eFuse programming is intentionally manual-only.
    # See scripts/setup_rtl8125.sh for the explicit write workflow.
}

def build_installer(variant_key=None):
    from tools.sf_installer import SF_Installer

    product = get_product_definition(variant_key) if variant_key else None
    return SF_Installer(
        name='pironman5',
        friendly_name=product["name"] if product else NAME,
        # - Setup install command description if needed, default to "Installer for {friendly_name}""
        # description='Installer for Pironman 5',
        # - Setup Work Dir if needed, default to /opt/{name}
        # work_dir='/opt/pironman5',
        # - Setup log dir if needed, default to /var/log/{name}
        # log_dir='/var/log/pironman5',
    )


def parse_install_args(argv=None, parser=None):
    if parser is None:
        parser = build_installer().parser
    parser.add_argument(
        "--variant",
        type=normalize_variant_key,
        choices=["auto", *sorted(PRODUCT_DEFINITIONS)],
        default="auto",
        metavar="VARIANT",
        help=VARIANT_HELP,
    )
    parser.add_argument("--print-variant", action="store_true", help="Print detected/selected variant and exit")
    parser.add_argument("--enable-dashboard", action="store_true", help="Enable dashboard components")
    parser.add_argument("--enable-ups", action="store_true", help="Enable PiPower5 UPS components")
    parser.add_argument(
        "--enable-legacy-hardware",
        action="append",
        default=[],
        type=normalize_optional_hardware_name,
        choices=OPTIONAL_HARDWARE_CHOICES,
        help="Enable a legacy hardware module explicitly",
    )
    parser.add_argument("--enable-experimental-dependency", action="append", default=[], help="Enable a named experimental dependency")
    parser.add_argument("--legacy-installer", action="store_true", help="Run the deprecated install.py workflow")
    parser.add_argument("--disable-dashboard", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def get_selected_variant_key(args):
    if getattr(args, "variant", "auto") != "auto":
        return normalize_variant_key(args.variant)
    return detect_hardware_variant()["variant"]


def describe_variant_selection(args):
    if getattr(args, "variant", "auto") != "auto":
        variant_key = normalize_variant_key(args.variant)
        product = get_product_definition(variant_key)
        return variant_key, f"Selected variant: {product['name']} ({variant_key})"
    detected = detect_hardware_variant()
    variant_key = detected["variant"]
    product = get_product_definition(variant_key)
    if detected["source"] == "hat-eeprom":
        detail = f"HAT EEPROM {detected['part_number']}"
    else:
        detail = f"fallback {detected['part_number']}"
    return variant_key, f"Auto-detected variant: {product['name']} ({variant_key}) from {detail}"


def get_variant_peripherals(variant_key):
    product = get_product_definition(variant_key)
    if product is None:
        return PERIPHERALS
    return assemble(product["modules"])["peripherals"]


def resolve_enabled_setting_names(args, peripherals=None):
    if peripherals is None:
        peripherals = get_variant_peripherals(get_selected_variant_key(args))
    optional_hardware = detect_optional_hardware()

    names = ["base"]

    if "oled" in peripherals:
        names.append("oled")
    if "gpio_fan_state" in peripherals or "vibration_switch" in peripherals:
        names.append("gpio")
    if "ws2812" in peripherals:
        names.append("ws2812")
    if "pi5_power_button" in peripherals:
        names.append("pi5_power_button")
    if "rgb_matrix" in peripherals:
        names.append("rgb_matrix")
    if (
        "rtl8125" in peripherals
        and (optional_hardware.get("rtl8125") or "rtl8125" in args.enable_experimental_dependency)
    ):
        names.append("rtl8125")

    if args.enable_dashboard:
        names.append("dashboard")
    if args.enable_ups:
        names.append("pipower5")

    return names


def apply_settings_by_name(installer_obj, names):
    mapping = {
        "base": settings,
        "oled": oled_settings,
        "gpio": gpio_settings,
        "ws2812": ws2812_settings,
        "pi5_power_button": pi5_power_button_settings,
        "rgb_matrix": rgb_matrix_settings,
        "dashboard": dashboard_settings,
        "pipower5": pipower5_settings,
        "rtl8125": rtl8125_settings,
    }
    for name in names:
        installer_obj.update_settings(mapping[name])


def apply_variant_config_txt(installer_obj, variant=VARIENT):
    product = get_product_definition(variant)
    config_txt = None
    if product is not None:
        config_txt = product.get("config_txt")
    if config_txt is None:
        config_txt = getattr(variant, "CONFIG_TXT", None)
    if config_txt:
        installer_obj.update_settings({"config_txt": config_txt})


def apply_variant_install_settings(installer_obj, variant_key):
    product = get_product_definition(variant_key)
    if product is None:
        return
    installer_obj.update_settings({
        "dtoverlays": product.get("dt_overlays", []),
        "work_files": {
            ".variant": f"{variant_key}\n",
        },
    })
    apply_variant_config_txt(installer_obj, variant_key)


def apply_optional_hardware_install_settings(installer_obj, args):
    enabled = []
    if getattr(args, "enable_ups", False):
        enabled.append("pipower5")
    enabled.extend(getattr(args, "enable_legacy_hardware", []) or [])
    if not enabled:
        return
    installer_obj.update_settings({
        "work_files": {
            ".enabled_optional_hardware": "\n".join(sorted(set(enabled))) + "\n",
        },
    })


def build_installer_for_variant(variant_key):
    variant_key = normalize_variant_key(variant_key)
    installer_obj = build_installer(variant_key)
    names = resolve_enabled_setting_names(
        argparse.Namespace(
            variant=variant_key,
            enable_dashboard=False,
            enable_ups=False,
            enable_legacy_hardware=[],
            enable_experimental_dependency=[],
        )
    )
    apply_settings_by_name(installer_obj, names)
    apply_variant_install_settings(installer_obj, variant_key)
    return installer_obj


def build_installer_for_settings(names):
    installer_obj = build_installer()
    apply_settings_by_name(installer_obj, names)
    apply_variant_config_txt(installer_obj)
    return installer_obj


def main(argv=None):
    installer_obj = build_installer()
    args = parse_install_args(argv, parser=installer_obj.parser)
    variant_key, variant_description = describe_variant_selection(args)
    print(variant_description)
    if args.print_variant:
        return
    if not args.legacy_installer:
        print("")
        print("install.py is deprecated and no longer runs the legacy root installer by default.")
        print("Use the package CLI setup flow instead:")
        print("")
        print(f"  pironman5 setup --variant {variant_key} --dry-run")
        print(f"  sudo \"$(command -v pironman5)\" setup --variant {variant_key}")
        print("")
        print("To run the old compatibility path explicitly, pass --legacy-installer.")
        return 2
    installer_obj.friendly_name = get_product_definition(variant_key)["name"]
    names = resolve_enabled_setting_names(args)
    apply_settings_by_name(installer_obj, names)
    apply_variant_install_settings(installer_obj, variant_key)
    apply_optional_hardware_install_settings(installer_obj, args)
    installer_obj.args = args
    installer_obj.main()


if __name__ == "__main__":
    raise SystemExit(main())
