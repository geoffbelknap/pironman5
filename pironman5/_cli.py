
import argparse
import json
import sys
import os
from importlib.resources import files as resource_files

from ._launch_browser import run as launch_browser
from .variants import NAME, PERIPHERALS, SYSTEM_DEFAULT_CONFIG, detect_hardware_variant, detect_optional_hardware, get_product_definition
from .version import __version__
from .utils import is_included, constrain
from .security import write_json_private

AVAILABLE_PAGES = []
AVAILABLE_EMAIL_MODES = []
TRUE_LIST = ['true', 'True', 'TRUE', '1', 'on', 'On', 'ON']
FALSE_LIST = ['false', 'False', 'FALSE', '0', 'off', 'Off', 'OFF']
DEBUG_LEVELS = [
    'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',
    'debug', 'info', 'warning', 'error', 'critical',
]
EXTRA_CONFIG_DEFAULTS = {
    'debug_level': 'INFO',
}
OPTIONAL_HARDWARE_LABELS = {
    "pipower5": "PiPower5 UPS",
    "rtl8125": "RTL8125 NIC",
}


def _variant_source_label(detected):
    if detected["source"] == "hat-eeprom":
        return f"HAT EEPROM {detected['part_number']}"
    if detected["source"] == "environment":
        return f"environment {detected['part_number']}"
    return f"fallback {detected['part_number']}"


def detect_payload():
    detected = detect_hardware_variant()
    product = get_product_definition(detected["variant"])
    return {
        "variant": detected["variant"],
        "variant_name": product["name"] if product else detected["variant"],
        "source": detected["source"],
        "part_number": detected["part_number"],
        "variant_id": detected["variant_id"],
        "version": detected["version"],
        "optional_hardware": detect_optional_hardware(),
    }


def print_detect(json_output=False):
    payload = detect_payload()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print(f"Variant: {payload['variant_name']} ({payload['variant']})")
    print(f"Source: {_variant_source_label(payload)}")
    print("Optional hardware:")
    for key, label in OPTIONAL_HARDWARE_LABELS.items():
        state = "detected" if payload["optional_hardware"].get(key) else "not detected"
        print(f"  {label}: {state}")


def handle_launch_browser(auto_start, true_list=None, false_list=None):
    true_list = true_list or ['true', 'True', 'TRUE', '1', 'on', 'On', 'ON']
    false_list = false_list or ['false', 'False', 'FALSE', '0', 'off', 'Off', 'OFF']
    if auto_start != '':
        if auto_start in true_list:
            print(f"Set dashboard auto start")
            if not os.path.exists(os.path.expanduser("~/.config/autostart")):
                os.makedirs(os.path.expanduser("~/.config/autostart"))
            with open(os.path.expanduser("~/.config/autostart/pironman5-dashboard.desktop"), "w") as f:
                f.write("""[Desktop Entry]
Type=Application
Name=Pironman5 Launch Dashboard on Browser
Comment=Auto launch Dashboard on browser for pironman5 on startup
Exec=pironman5 launch-browser
Terminal=false
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
X-KDE-autostart-enabled=true
X-MATE-Autostart-enabled=true
Categories=Utility;Network;Browser;
Keywords=pironman5;browser;autostart;""")
        elif auto_start in false_list:
            print(f"Remove dashboard auto start")
            os.system(f'rm -f ~/.config/autostart/pironman5-dashboard.desktop')
        else:
            print(f"Invalid value for auto start, it should be true/on/1 or false/off/0")
            quit()
    else:
        launch_browser()


def update_config_file(config, config_path):
    import json
    current = {'system': {}}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            try:
                current = json.load(f)
            except json.JSONDecodeError:
                current = {'system': {}}
    for key in config:
        if key in current:
            current[key].update(config[key])
        else:
            current[key] = config[key]
    write_json_private(config_path, current)


def load_config_file(config_path):
    if not os.path.exists(config_path):
        return {'system': {}}
    with open(config_path, 'r') as f:
        try:
            content = f.read()
            if content == '':
                return {'system': {}}
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid config file: {config_path}") from exc


def get_system_config_value(config, key, default=None):
    if default is None:
        default = SYSTEM_DEFAULT_CONFIG.get(key)
    return config.get('system', {}).get(key, default)


def get_config_defaults():
    defaults = dict(SYSTEM_DEFAULT_CONFIG)
    for key, value in EXTRA_CONFIG_DEFAULTS.items():
        defaults.setdefault(key, value)
    return defaults


def ensure_known_config_key(key):
    defaults = get_config_defaults()
    if key not in defaults:
        print(f"Unknown config key: {key}")
        quit()
    return defaults[key]


def format_config_value(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def parse_config_value(key, raw_value):
    default = ensure_known_config_key(key)
    if key == 'debug_level':
        if raw_value.lower() not in ['debug', 'info', 'warning', 'error', 'critical']:
            print(f"Invalid debug level, it should be one of: debug, info, warning, error, critical")
            quit()
        return raw_value.upper()
    if key == 'temperature_unit':
        if raw_value not in ['C', 'F']:
            print(f"Invalid value for Temperature unit, it should be C or F")
            quit()
        return raw_value
    if isinstance(default, bool):
        if raw_value in TRUE_LIST:
            return True
        if raw_value in FALSE_LIST:
            return False
        print(f"Invalid value for {key}, it should be True/true/on/On/1 or False/false/off/Off/0")
        quit()
    if isinstance(default, int):
        try:
            return int(raw_value)
        except ValueError:
            print(f"Invalid value for {key}, it should be an integer")
            quit()
    if isinstance(default, (list, dict)):
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            print(f"Invalid value for {key}, it should be valid JSON")
            quit()
        if not isinstance(value, type(default)):
            print(f"Invalid value for {key}, it should be a {type(default).__name__}")
            quit()
        return value
    return raw_value


def handle_config_command(args, current_config, config_path):
    if args.config_action == 'get':
        default = ensure_known_config_key(args.config_key)
        value = get_system_config_value(current_config, args.config_key, default)
        print(f"{args.config_key}: {format_config_value(value)}")
        return
    if args.config_action == 'set':
        value = parse_config_value(args.config_key, args.config_value)
        update_config_file({'system': {args.config_key: value}}, config_path)
        print(f"Set {args.config_key}: {format_config_value(value)}")
        return
    print("Invalid config command")
    quit()


def handle_debug_level(args, current_config, new_sys_config):
    if args.debug_level == None:
        print(f"Debug level: {get_system_config_value(current_config, 'debug_level', 'INFO')}")
        return
    if args.debug_level.lower() not in ['debug', 'info', 'warning', 'error', 'critical']:
        print(f"Invalid debug level, it should be one of: debug, info, warning, error, critical")
        quit()
    debug_level = args.debug_level.upper()
    new_sys_config['debug_level'] = debug_level
    print(f"Set debug level: {debug_level}")


def handle_database_retention_days(args, current_config, new_sys_config):
    if args.database_retention_days == None:
        print(f"Database retention days: {get_system_config_value(current_config, 'database_retention_days')}")
        return
    try:
        database_retention_days = int(args.database_retention_days)
    except ValueError:
        print(f"Invalid value for database retention days, it should be a number")
        quit()
    new_sys_config['database_retention_days'] = database_retention_days
    print(f"Set database retention days: {database_retention_days}")


def handle_enable_history(args, current_config, new_sys_config):
    if args.enable_history == None:
        print(f"Enable history: {get_system_config_value(current_config, 'enable_history')}")
        return
    if args.enable_history in TRUE_LIST:
        new_sys_config['enable_history'] = True
        print(f"Set enable history: True")
    elif args.enable_history in FALSE_LIST:
        new_sys_config['enable_history'] = False
        print(f"Set enable history: False")
    else:
        print(f"Invalid value for enable history, it should be True/true/on/On/1 or False/false/off/Off/0")
        quit()


def handle_temperature_unit(args, current_config, new_sys_config):
    if args.temperature_unit == None:
        print(f"Temperature unit: {get_system_config_value(current_config, 'temperature_unit')}")
        return
    if args.temperature_unit not in ['C', 'F']:
        print(f"Invalid value for Temperature unit, it should be C or F")
        quit()
    new_sys_config['temperature_unit'] = args.temperature_unit
    print(f"Set Temperature unit: {args.temperature_unit}")


def main():
    global AVAILABLE_PAGES, AVAILABLE_EMAIL_MODES

    if len(sys.argv) > 1 and sys.argv[1] == "system":
        from .system import main as system_main
        system_main(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "detect":
        detect_parser = argparse.ArgumentParser(prog="pironman5 detect")
        detect_parser.add_argument("--json", action="store_true", help="Print detection results as JSON")
        detect_args = detect_parser.parse_args(sys.argv[2:])
        print_detect(json_output=detect_args.json)
        return

    __package_name__ = __name__.split('.')[0]
    CONFIG_PATH = "/opt/pironman5/config.json"
    PIP_PATH = "/opt/pironman5/venv/bin/pip"

    current_config = None
    new_sys_config = {}
    help_requested = any(arg in ("-h", "--help") for arg in sys.argv[1:])

    parser = argparse.ArgumentParser(prog='pironman5',
                                    description=f'{NAME} command line interface')
    
    subparsers = parser.add_subparsers(dest="subcommand", title="Subcommands")

    parser.add_argument("-v", "--version", action="store_true", help="Show version")
    parser.add_argument("-c", "--config", action="store_true", help="Show config")
    parser.add_argument("-drd", "--database-retention-days", nargs='?', default='', help="Database retention days")
    parser.add_argument("-dl", "--debug-level", nargs='?', default='', choices=DEBUG_LEVELS, help="Debug level")
    parser.add_argument("-rd", "--remove-dashboard", action="store_true", help="Remove dashboard")
    parser.add_argument("-cp", "--config-path", nargs='?', default='', help="Config path")
    parser.add_argument("-eh", "--enable-history", nargs='?', default='', help="Enable history, True/true/on/On/1 or False/false/off/Off/0")
    # ws2812
    if is_included(PERIPHERALS, "ws2812"):
        from .runtime import RGB_STYLES
        parser.add_argument("-re", "--rgb-enable", nargs='?', default='', help="RGB enable True/False")
        parser.add_argument("-rs", "--rgb-style", nargs='?', default='', help=f"RGB style: {RGB_STYLES}")
        parser.add_argument("-rc", "--rgb-color", nargs='?', default='', help='RGB color in hex format without # (e.g. 00aabb)')
        parser.add_argument("-rb", "--rgb-brightness", nargs='?', default='', help="RGB brightness 0-100")
        parser.add_argument("-rp", "--rgb-speed", nargs='?', default='', help="RGB speed 0-100")
        parser.add_argument("-rl", "--rgb-led-count", nargs='?', default='', help="RGB LED count int")
    # temperature_unit
    if is_included(PERIPHERALS, "temperature_unit"):
        parser.add_argument("-u", "--temperature-unit", choices=["C", "F"], nargs='?', default='', help="Temperature unit")
    # gpio_fan_mode
    if is_included(PERIPHERALS, "gpio_fan_mode"):
        from .runtime import GPIO_FAN_MODES
        parser.add_argument("-gm", "--gpio-fan-mode", nargs='?', default='', help=f"GPIO fan mode, {', '.join([f'{i}: {mode}' for i, mode in enumerate(GPIO_FAN_MODES)])}")
        parser.add_argument("-gp", "--gpio-fan-pin", nargs='?', default='', help="GPIO fan pin")
    if is_included(PERIPHERALS, "gpio_fan_led"):
        parser.add_argument("-fl", "--gpio-fan-led", nargs='?', default='', help="GPIO fan LED state on/off/follow")
        parser.add_argument("-fp", "--gpio-fan-led-pin", nargs='?', default='', help="GPIO fan LED pin")
    # oled
    if is_included(PERIPHERALS, "oled"):
        global AVAILABLE_PAGES
        if help_requested:
            AVAILABLE_PAGES = []
        else:
            from pm_auto.addons.oled import get_available_pages
            AVAILABLE_PAGES = get_available_pages(PERIPHERALS)
        parser.add_argument("-oe", "--oled-enable", nargs='?', default='', help="OLED enable True/true/on/On/1 or False/false/off/Off/0")
        parser.add_argument("-or", "--oled-rotation", nargs='?', default=-1, type=int, choices=[0, 180], help="Set to rotate OLED display, 0, 180")
        parser.add_argument("-op", "--oled-pages", nargs='?', default='', help=f"OLED pages, split by ',': {','.join(AVAILABLE_PAGES)}")
        if is_included(PERIPHERALS, "oled_sleep"):
            parser.add_argument("-os", "--oled-sleep-timeout", nargs='?', default='', help="OLED sleep timeout in seconds (set to 0 to disable timeout)")
    # vibration_switch
    if is_included(PERIPHERALS, "vibration_switch"):
        parser.add_argument("-vp", "--vibration-switch-pin", nargs='?', default='', help="Vibration switch pin")
        parser.add_argument("-vu", "--vibration-switch-pull-up", nargs='?', default='', help="Vibration switch pull up True/False")
    # rgb_matrix
    if is_included(PERIPHERALS, "rgb_matrix"):
        if help_requested:
            EFFECT_LIST = []
        else:
            from pm_auto.addons.rgb_matrix import EFFECT_LIST
        parser.add_argument("-rme", "--rgb-matrix-enable", nargs='?', default='', help="RGB enable True/False")
        parser.add_argument("-rms", "--rgb-matrix-style",  nargs='?', default='', help=f"RGB style: {EFFECT_LIST}")
        parser.add_argument("-rmc", "--rgb-matrix-color", nargs='?', default='', help='RGB color in hex format without # (e.g. 00aabb)')
        parser.add_argument("-rmc2", "--rgb-matrix-color2", nargs='?', default='', help='RGB color in hex format without # (e.g. 00aabb)')
        parser.add_argument("-rmp", "--rgb-matrix-speed", nargs='?', default='', help="RGB speed 0-100")
        parser.add_argument("-rmb", "--rgb-matrix-brightness", nargs='?', default='', help="RGB brightness 0-100")
    # pipower5
    if is_included(PERIPHERALS, "pipower5"):
        # 定义pipower5子命令（用于调用独立的pipower5）
        pipower_parser = subparsers.add_parser(
            "pipower5",
            add_help=False  # 禁用子命令的-h处理，确保透传
        )
    config_parser = subparsers.add_parser("config", help="Read or update config values")
    config_subparsers = config_parser.add_subparsers(dest="config_action")
    config_get_parser = config_subparsers.add_parser("get", help="Read a config value")
    config_get_parser.add_argument("config_key", help="System config key")
    config_set_parser = config_subparsers.add_parser("set", help="Update a config value")
    config_set_parser.add_argument("config_key", help="System config key")
    config_set_parser.add_argument("config_value", help="New value")
    detect_parser = subparsers.add_parser("detect", help="Detect variant and optional hardware")
    detect_parser.add_argument("--json", action="store_true", help="Print detection results as JSON")
    start_parser = subparsers.add_parser("start", help="Start Pironman5")
    stop_parser = subparsers.add_parser("stop", help="Stop Pironman5")
    launch_browser_parser = subparsers.add_parser("launch-browser", help="Launch browser")
    launch_browser_parser.add_argument("-a", "--auto-start", nargs='?', default='', help="Auto start browser on boot")

    # parse args
    # -----------------------------------------------------------
    # args = parser.parse_args()
    args, remaining_args = parser.parse_known_args()

    # no args, show help
    if not (len(sys.argv) > 1):
        parser.print_help()
        quit()
    
    # show version
    # ----------------------------------------
    if args.version:
        print(__version__)
        quit()

    # get or set config path
    # ----------------------------------------
    config_path = CONFIG_PATH
    if args.config_path != '':
        if args.config_path == None:
            print(f"Config path: {config_path}")
        else:
            config_path = args.config_path
            print(f"Set config path: {config_path}")

    if args.subcommand == 'start':
        from .pironman5 import Pironman5
        pironman5 = Pironman5(config_path=config_path)
        pironman5.start()
        return
    if args.subcommand == 'stop':
        os.system('pkill -f pironman5')
        return
    if args.subcommand == 'launch-browser':
        handle_launch_browser(args.auto_start, TRUE_LIST, FALSE_LIST)
        return

    # load config file
    # ----------------------------------------
    try:
        current_config = load_config_file(config_path)
    except ValueError as exc:
        print(str(exc))
        quit()

    # show config
    # ----------------------------------------
    if args.config:
        print(json.dumps(current_config, indent=4))
        return
    if args.subcommand == 'config':
        handle_config_command(args, current_config, config_path)
        return

    # get or set debug level
    # ----------------------------------------
    if args.debug_level != '':
        handle_debug_level(args, current_config, new_sys_config)

    # Set database retention days
    # ----------------------------------------
    if args.database_retention_days != '':
        handle_database_retention_days(args, current_config, new_sys_config)

    # remove dashboard
    # ----------------------------------------    
    if args.remove_dashboard:
        print("Remove Dashboard")
        os.system(f'{PIP_PATH} uninstall pm_dashboard -y')
        print("Dashboard removed, restart pironman5 to apply changes: sudo systemctl restart pironman5.service")
        quit()

    # swtich history
    if args.enable_history != '':
        handle_enable_history(args, current_config, new_sys_config)

    # ws2812 settings
    # ----------------------------------------
    if is_included(PERIPHERALS, "ws2812"):
        # ws2812 rgb_color
        if args.rgb_color != '':
            if args.rgb_color == None:
                hex = get_system_config_value(current_config, 'rgb_color')
                if hex[0] == '#':
                    hex = hex[1:]
                r = int(hex[0:2], 16)
                g = int(hex[2:4], 16)
                b = int(hex[4:6], 16)
                print(f"RGB color: #{hex} ({r}, {g}, {b})")
            else:
                if len(args.rgb_color) != 6:
                    print(f'Invalid value for RGB color, it should be in hex format without # (e.g. 00aabb)')
                    quit()
                if len(args.rgb_color) == 6:
                    try:
                        r = int(args.rgb_color[0:2], 16)
                        g = int(args.rgb_color[2:4], 16)
                        b = int(args.rgb_color[4:6], 16)
                    except ValueError:
                        print(f'Invalid value for RGB color, it should be in hex format without # (e.g. 00aabb)')
                        quit()
                new_sys_config['rgb_color'] = args.rgb_color
                print(f"Set RGB color: #{args.rgb_color} ({r}, {g}, {b})")
        # ws2812 rgb_brightness
        if args.rgb_brightness != '':
            if args.rgb_brightness == None:
                print(f"RGB brightness: {get_system_config_value(current_config, 'rgb_brightness')}")
            else:
                try:
                    args.rgb_brightness = int(args.rgb_brightness)
                except ValueError:
                    print(f"Invalid value for RGB brightness, it should be an integer between 0 and 100")
                    quit()
                if args.rgb_brightness < 0 or args.rgb_brightness > 100:
                    print(f"Invalid value for RGB brightness, it should be between 0 and 100")
                    quit()
                new_sys_config['rgb_brightness'] = args.rgb_brightness
                print(f"Set RGB brightness: {args.rgb_brightness}")
        # ws2812 rgb_style
        if args.rgb_style != '':
            if args.rgb_style == None:
                print(f"RGB style: {get_system_config_value(current_config, 'rgb_style')}")
            else:
                if args.rgb_style not in RGB_STYLES:
                    print(f"Invalid value for RGB style, it should be one of {RGB_STYLES}")
                    quit()
                new_sys_config['rgb_style'] = args.rgb_style
                print(f"Set RGB style: {args.rgb_style}")
        # ws2812 rgb_speed
        if args.rgb_speed != '':
            if args.rgb_speed == None:
                print(f"RGB speed: {get_system_config_value(current_config, 'rgb_speed')}")
            else:
                try:
                    args.rgb_speed = int(args.rgb_speed)
                except ValueError:
                    print(f"Invalid value for RGB speed, it should be an integer between 0 and 100")
                    quit()
                if args.rgb_speed < 0 or args.rgb_speed > 100:
                    print(f"Invalid value for RGB speed, it should be between 0 and 100")
                    quit()
                new_sys_config['rgb_speed'] = args.rgb_speed
                print(f"Set RGB speed: {args.rgb_speed}")
        # ws2812 rgb_enable
        if args.rgb_enable != '':
            if args.rgb_enable == None:
                print(f"RGB enable: {get_system_config_value(current_config, 'rgb_enable')}")
            else:
                if args.rgb_enable in TRUE_LIST:
                    new_sys_config['rgb_enable'] = True
                    print(f"Set RGB enable: True")
                elif args.rgb_enable in FALSE_LIST:
                    new_sys_config['rgb_enable'] = False
                    print(f"Set RGB enable: False")
                else:
                    print(f"Invalid value for RGB enable, it should be True or False")
                    quit()
        # ws2812 rgb_led_count
        if args.rgb_led_count != '':
            if args.rgb_led_count == None:
                print(f"RGB LED count: {get_system_config_value(current_config, 'rgb_led_count')}")
            else:
                try:
                    args.rgb_led_count = int(args.rgb_led_count)
                except ValueError:
                    print(f"Invalid value for RGB LED count, it should be an integer greater than 0")
                    quit()
                if args.rgb_led_count < 1:
                    print(f"Invalid value for RGB LED count, it should be greater than 0")
                    quit()
                new_sys_config['rgb_led_count'] = args.rgb_led_count
                print(f"Set RGB LED count: {args.rgb_led_count}")

    # temperature unit settings
    # ----------------------------------------
    if is_included(PERIPHERALS, "temperature_unit"):
        if args.temperature_unit != '':
            handle_temperature_unit(args, current_config, new_sys_config)

    # GPIO fan settings
    # ----------------------------------------
    if is_included(PERIPHERALS, "gpio_fan_mode"):
        # gpio_fan_mode
        if args.gpio_fan_mode != '':
            if args.gpio_fan_mode == None:
                print(f"GPIO fan mode: {get_system_config_value(current_config, 'gpio_fan_mode')}")
            else:
                try:
                    args.gpio_fan_mode = int(args.gpio_fan_mode)
                except ValueError:
                    print(f"Invalid value for GPIO fan mode, it should be an integer between 0 and {len(GPIO_FAN_MODES) - 1}, {', '.join([f'{i}: {mode}' for i, mode in enumerate(GPIO_FAN_MODES)])}")
                    quit()
                if args.gpio_fan_mode < 0 or args.gpio_fan_mode >= len(GPIO_FAN_MODES):
                    print(f"Invalid value for GPIO fan mode, it should be between 0 and {len(GPIO_FAN_MODES) - 1}, {', '.join([f'{i}: {mode}' for i, mode in enumerate(GPIO_FAN_MODES)])}")
                    quit()
                new_sys_config['gpio_fan_mode'] = args.gpio_fan_mode
                print(f"Set GPIO fan mode: {args.gpio_fan_mode}")
        # gpio_fan_pin
        if args.gpio_fan_pin != '':
            if args.gpio_fan_pin == None:
                print(f"GPIO fan pin: {get_system_config_value(current_config, 'gpio_fan_pin')}")
            else:
                try:
                    args.gpio_fan_pin = int(args.gpio_fan_pin)
                except ValueError:
                    print(f"Invalid value for GPIO fan pin, it should be an integer")
                    quit()
                new_sys_config['gpio_fan_pin'] = args.gpio_fan_pin
                print(f"Set GPIO fan pin: {args.gpio_fan_pin}")

    # GPIO fan LED settings
    # ----------------------------------------
    if is_included(PERIPHERALS, "gpio_fan_led"):
        if args.gpio_fan_led != '':
            if args.gpio_fan_led == None:
                print(f"GPIO fan LED state: {get_system_config_value(current_config, 'gpio_fan_led')}")
            else:
                state = args.gpio_fan_led.lower()
                if state not in ['on', 'off', 'follow']:
                    print(f"Invalid value for GPIO fan LED state, it should be on, off or follow")
                    quit()
                new_sys_config['gpio_fan_led'] = state
                print(f"Set GPIO fan LED state: {args.gpio_fan_led}")
        if args.gpio_fan_led_pin != '':
            if args.gpio_fan_led_pin == None:
                print(f"GPIO fan LED pin: {get_system_config_value(current_config, 'gpio_fan_led_pin')}")
            else:
                try:
                    args.gpio_fan_led_pin = int(args.gpio_fan_led_pin)
                except ValueError:
                    print(f"Invalid value for GPIO fan LED pin, it should be an integer")
                    quit()
                new_sys_config['gpio_fan_led_pin'] = args.gpio_fan_led_pin
                print(f"Set GPIO fan LED pin: {args.gpio_fan_led_pin}")

    # OLED settings
    # ----------------------------------------
    if is_included(PERIPHERALS, "oled"):
        # oled enable
        if args.oled_enable != '':
            if args.oled_enable == None:
                print(f"OLED enable: {'enabled' if get_system_config_value(current_config, 'oled_enable') else 'disabled'}")
            else:
                if args.oled_enable in TRUE_LIST:                
                    new_sys_config['oled_enable'] = True
                    print(f"Set OLED enable: Enabled")
                elif args.oled_enable in FALSE_LIST:
                    new_sys_config['oled_enable'] = False
                    print(f"Set OLED enable: Disabled")
                else:
                    print(f"Invalid value for OLED enable, it should be {', '.join(TRUE_LIST)} or {', '.join(FALSE_LIST)}")
                    quit()

        # oled rotation
        if args.oled_rotation != -1:
            if args.oled_rotation == None:
                print(f"OLED rotation: {get_system_config_value(current_config, 'oled_rotation')}")
            else:
                try:
                    args.oled_rotation = int(args.oled_rotation)
                except ValueError:
                    print(f"Invalid value for OLED rotation, it should be an integer of 0 or 180")
                    quit()
                if args.oled_rotation not in [0, 180]:
                    print(f"Invalid value for OLED rotation, it should be 0 or 180")
                    quit()
                new_sys_config['oled_rotation'] = args.oled_rotation
                print(f"SetOLED rotation: {args.oled_rotation}")
        # oled_sleep_timeout
        if args.oled_sleep_timeout != '':
            if args.oled_sleep_timeout == None:
                print(f"OLED sleep timeout: {get_system_config_value(current_config, 'oled_sleep_timeout')}")
            else:
                from pm_auto.addons.oled import OLEDAddon
                min = OLEDAddon.MIN_SLEEP_TIMEOUT
                max = OLEDAddon.MAX_SLEEP_TIMEOUT
                try:
                    args.oled_sleep_timeout = int(args.oled_sleep_timeout)
                except ValueError:
                    print(f"Invalid value for OLED sleep timeout, it should be an integer")
                    quit()
                if args.oled_sleep_timeout < 0:
                    print(f"Invalid value for OLED sleep timeout, it should be greater than or equal to 0")
                    quit()
                oled_sleep_timeout = args.oled_sleep_timeout
                if args.oled_sleep_timeout != 0 and (args.oled_sleep_timeout < min or args.oled_sleep_timeout > max):
                    print(f"[WARNING] OLED sleep timeout value should be between {min} and {max}")
                    oled_sleep_timeout = constrain(oled_sleep_timeout, min, max)
                new_sys_config['oled_sleep_timeout'] = oled_sleep_timeout
                if oled_sleep_timeout == 0:
                    print("Set OLED sleep timeout: disabled")
                else:
                    print(f"Set OLED sleep timeout: {oled_sleep_timeout}")
        # oled_pages
        if args.oled_pages != '':
            if args.oled_pages == None:
                pages = [f' - {page}' for page in get_system_config_value(current_config, 'oled_pages', [])]
                pages = '\n'.join(pages)
                print("OLED pages:")
                print(pages)
            else:
                if ',' in args.oled_pages:
                    pages = args.oled_pages.split(',')
                else:
                    pages = [args.oled_pages]
                pages = [p.lower() for p in pages]
                for page in pages:
                    if page not in AVAILABLE_PAGES:
                        print(f"Invalid value for OLED pages: '{page}', it should be split by ',' and be one of {','.join(AVAILABLE_PAGES)}")
                        quit()
                new_sys_config['oled_pages'] = pages
                print(f"Set OLED pages: {pages}")

    # Vibration switch settings
    # ----------------------------------------
    if is_included(PERIPHERALS, "vibration_switch"):
        # vibration_switch_pin
        if args.vibration_switch_pin != '':
            if args.vibration_switch_pin == None:
                print(f"Vibration switch pin: {get_system_config_value(current_config, 'vibration_switch_pin')}")
            else:
                try:
                    pin = int(args.vibration_switch_pin)
                except ValueError:
                    print(f"Invalid value for Vibration switch pin, it should be an integer")
                    quit()
                if pin < 0 or pin > 40:
                    print(f"Invalid value for Vibration switch pin, it should be between 0 and 40")
                    quit()
                new_sys_config['vibration_switch_pin'] = pin
                print(f"Set Vibration switch pin: {pin}")
        # vibration_switch_pull_up
        if args.vibration_switch_pull_up != '':
            if args.vibration_switch_pull_up == None:
                print(f"Vibration switch pull up: {get_system_config_value(current_config, 'vibration_switch_pull_up')}")
            else:
                if args.vibration_switch_pull_up in TRUE_LIST:
                    new_sys_config['vibration_switch_pull_up'] = True
                    print(f"Set Vibration switch pull up: True")
                elif args.vibration_switch_pull_up in FALSE_LIST:
                    new_sys_config['vibration_switch_pull_up'] = False
                    print(f"Set Vibration switch pull up: False")
                else:
                    print(f"Invalid value for Vibration switch pull up, it should be {', '.join(TRUE_LIST)} or {', '.join(FALSE_LIST)}")
                    quit()

    # RGB matrix settings
    # ----------------------------------------
    if is_included(PERIPHERALS, "rgb_matrix"):
        # rgb_matrix_enable
        if args.rgb_matrix_enable != '':
            if args.rgb_matrix_enable == None:
                print(f"RGB Matrix enable: {get_system_config_value(current_config, 'rgb_matrix_enable')}")
            else:
                if args.rgb_matrix_enable in TRUE_LIST:
                    new_sys_config['rgb_matrix_enable'] = True
                    print(f"Set RGB Matrix enable: True")
                elif args.rgb_matrix_enable in FALSE_LIST:
                    new_sys_config['rgb_matrix_enable'] = False
                    print(f"Set RGB Matrix enable: False")
                else:
                    print(f"Invalid value for RGB Matrix enable, it should be True or False")
                    quit()
        # rgb_matrix_style
        if args.rgb_matrix_style != '':
            if args.rgb_matrix_style == None:
                print(f"RGB Matrix style: {get_system_config_value(current_config, 'rgb_matrix_style')}")
            else:
                if args.rgb_matrix_style not in EFFECT_LIST:
                    print(f"Invalid value for RGB Matrix style: {args.rgb_matrix_style}, it should be one of {EFFECT_LIST}")
                    quit()
                new_sys_config['rgb_matrix_style'] = args.rgb_matrix_style
                print(f"Set RGB Matrix style: {args.rgb_matrix_style}")
        # rgb_matrix_speed
        if args.rgb_matrix_speed != '':
            if args.rgb_matrix_speed == None:
                print(f"RGB Matrix speed: {get_system_config_value(current_config, 'rgb_matrix_speed')}")
            else:
                try:
                    args.rgb_matrix_speed = int(args.rgb_matrix_speed)
                except ValueError:
                    print(f"Invalid value for RGB Matrix speed, it should be an integer between 0 and 100")
                    quit()
                if args.rgb_matrix_speed < 0 or args.rgb_matrix_speed > 100:
                    print(f"Invalid value for RGB Matrix speed, it should be between 0 and 100")
                    quit()
                new_sys_config['rgb_matrix_speed'] = args.rgb_matrix_speed
                print(f"Set RGB Matrix speed: {args.rgb_matrix_speed}")
        # rgb_matrix_brightness
        if args.rgb_matrix_brightness != '':
            if args.rgb_matrix_brightness == None:
                print(f"RGB Matrix brightness: {get_system_config_value(current_config, 'rgb_matrix_brightness')}")
            else:
                try:
                    args.rgb_matrix_brightness = int(args.rgb_matrix_brightness)
                except ValueError:
                    print(f"Invalid value for RGB Matrix brightness, it should be an integer between 0 and 100")
                    quit()
                if args.rgb_matrix_brightness < 0 or args.rgb_matrix_brightness > 100:
                    print(f"Invalid value for RGB Matrix brightness, it should be between 0 and 100")
                    quit()
                new_sys_config['rgb_matrix_brightness'] = args.rgb_matrix_brightness
                print(f"Set RGB Matrix brightness: {args.rgb_matrix_brightness}")
        # rgb_matrix color
        if args.rgb_matrix_color != '':
            from pironman5.utils import hex_to_rgb
            if args.rgb_matrix_color == None:
                hex = get_system_config_value(current_config, 'rgb_matrix_color')
                r, g, b = hex_to_rgb(hex)
                print(f"RGB Matrix color: #{hex} ({r}, {g}, {b})")
            else:
                try:
                    r, g, b = hex_to_rgb(args.rgb_matrix_color)
                except ValueError:
                    print(f'Invalid value for RGB Matrix color, it should be in hex format without # (e.g. 00aabb)')
                    quit()
                new_sys_config['rgb_matrix_color'] = args.rgb_matrix_color
                print(f"Set RGB Matrix color: #{args.rgb_matrix_color} ({r}, {g}, {b})")
        # rgb_matrix color2
        if args.rgb_matrix_color2 != '':
            from pironman5.utils import hex_to_rgb
            if args.rgb_matrix_color2 == None:
                print(f"RGB Matrix color2: {get_system_config_value(current_config, 'rgb_matrix_color2')}")
            else:
                try:
                    r, g, b = hex_to_rgb(args.rgb_matrix_color2)
                except ValueError:
                    print(f'Invalid value for RGB Matrix color2, it should be in hex format without # (e.g. 00aabb)')
                    quit()
                new_sys_config['rgb_matrix_color2'] = args.rgb_matrix_color2
                print(f"Set RGB Matrix color2: #{args.rgb_matrix_color2} ({r}, {g}, {b})")

    # # PiPower 5 settings
    if is_included(PERIPHERALS, "pipower5"):
        if args.subcommand == "pipower5":
            cmd = [
                "pipower5",
                "-cp", CONFIG_PATH,
                *remaining_args
            ]
            try:
                import subprocess
                result = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                print(result.stdout)
            except subprocess.CalledProcessError as e:
                print(f"Error: {e.stderr}", file=sys.stderr)
                sys.exit(1)
            except FileNotFoundError:
                print("Error: pipower5 command not found, please make sure it is installed and in the environment variables", file=sys.stderr)
                sys.exit(1)

    # Update settings
    # ----------------------------------------
    if new_sys_config:
        update_config_file({'system': new_sys_config}, config_path)
