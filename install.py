#!/usr/bin/env python3

import argparse

from tools.sf_installer import SF_Installer
from pironman5.version import __version__
from pironman5.variants import NAME, DT_OVERLAYS, PERIPHERALS

PM_AUTO_VERSION = '1.4.7'
DASHBOARD_VERSION = '1.4.0'
SF_RPI_STATUS_VERSION = '1.1.8'
PIPOWER5_VERSION = 'main'

settings = {
    # - Setup venv options if needed, default to []
    'venv_options': [
        '--system-site-packages',
    ],

    'groups': [],

    # - Build required apt dependencies, default to []
    # 'build_dependencies': [
    #     'curl', # for influxdb key download
    # ],

    # - Before install scripts, default to []
    'run_scripts_before_install': [
        "umbrel_patch.sh",
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
        'pm_auto': f'git+https://github.com/sunfounder/pm_auto.git@{PM_AUTO_VERSION}',
        'sf_rpi_status': f'git+https://github.com/sunfounder/sf_rpi_status.git@{SF_RPI_STATUS_VERSION}',
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
    'dtoverlays': DT_OVERLAYS,
}

ws2812_settings = {
    'run_scripts_before_install': [
        "install_lgpio.sh",
        "fix_kali_gpio_spi.sh",
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
    # - Before install scripts, default to []
    'run_scripts_before_install': [
        "install_lgpio.sh",
        "fix_kali_gpio_spi.sh",
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
    'run_scripts_after_install': [
        "change_rpi.gpio_to_rpi.lgpio.sh",
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
        'pm_dashboard': f'git+https://github.com/sunfounder/pm_dashboard.git@{DASHBOARD_VERSION}',
    },
}

influxdb_legacy_settings = {
    'groups': ['influxdb'],
    # - Build required apt dependencies, default to []
    'build_dependencies': [
        'curl', # for influxdb key download
    ],
    # - Before install scripts, default to []
    'run_scripts_before_install': [
        "install_influxdb.sh",
    ],
}

pipower5_settings = {
    # Install python packages from source
    'groups': ['i2c', 'pipower5'],
    'python_source': {
        'pipower5': f'git+https://github.com/sunfounder/pipower5.git@{PIPOWER5_VERSION}',
        'spc': f'git+https://github.com/sunfounder/spc.git',
    },
    # Add symbolic links
    'symlinks': [
        'pipower5',
    ],
    # Before install scripts, default to []
    'run_scripts_before_install': [
        "setup_pipower5.sh",
    ],
    # - Copy device tree overlay to /boot/overlays
    'dtoverlays': [
        f'https://github.com/sunfounder/pipower5/raw/refs/heads/main/sunfounder-pipower5.dtbo'
    ],
}

rtl8125_settings = {
    # - Install from apt
    'run_scripts_before_install': [
        "setup_rtl8125.sh",
    ],
}

def build_installer():
    return SF_Installer(
        name='pironman5',
        friendly_name=NAME,
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
    parser.add_argument("--enable-dashboard", action="store_true", help="Enable dashboard components")
    parser.add_argument("--enable-influxdb-legacy", action="store_true", help="Enable legacy InfluxDB dashboard history backend")
    parser.add_argument("--enable-ups", action="store_true", help="Enable PiPower5 UPS components")
    parser.add_argument("--enable-experimental-dependency", action="append", default=[], help="Enable a named experimental dependency")
    parser.add_argument("--disable-dashboard", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def resolve_enabled_setting_names(args, peripherals=None):
    if peripherals is None:
        peripherals = PERIPHERALS

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
    if "rtl8125" in peripherals:
        names.append("rtl8125")

    if args.enable_dashboard:
        names.append("dashboard")
    if args.enable_dashboard and args.enable_influxdb_legacy:
        names.append("influxdb_legacy")
    if args.enable_ups and "pipower5" in peripherals:
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
        "influxdb_legacy": influxdb_legacy_settings,
        "pipower5": pipower5_settings,
        "rtl8125": rtl8125_settings,
    }
    for name in names:
        installer_obj.update_settings(mapping[name])


def build_installer_for_settings(names):
    installer_obj = build_installer()
    apply_settings_by_name(installer_obj, names)
    return installer_obj


def main(argv=None):
    installer_obj = build_installer()
    args = parse_install_args(argv, parser=installer_obj.parser)
    names = resolve_enabled_setting_names(args)
    apply_settings_by_name(installer_obj, names)
    installer_obj.args = args
    installer_obj.main()


if __name__ == "__main__":
    main()
