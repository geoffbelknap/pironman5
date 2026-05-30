
import argparse
import json
import sys
import os
import subprocess

from ._launch_browser import run as launch_browser
from .config import config_field, iter_config_fields, load_config_file, update_config_file
from .variants import NAME, PERIPHERALS, SYSTEM_DEFAULT_CONFIG, detect_hardware_variant, detect_optional_hardware, get_product_definition
from .version import __version__
from .utils import is_included

RGB_MATRIX_EFFECT_LIST = [
    "solid",
    "breathing",
    "rainbow",
    "rainbow_reverse",
    "flow",
    "flow_reverse",
]
TRUE_LIST = ['true', 'True', 'TRUE', '1', 'on', 'On', 'ON']
FALSE_LIST = ['false', 'False', 'FALSE', '0', 'off', 'Off', 'OFF']
RGB_TIME_RE = r"^\d{2}:\d{2}$"
EXTRA_CONFIG_DEFAULTS = {
    'debug_level': 'INFO',
}
INT_CONFIG_KEYS = {
    "rgb_night_brightness",
}
OPTIONAL_HARDWARE_LABELS = {
    "pipower5": "PiPower5 UPS",
    "rtl8125": "RTL8125 NIC",
    "i2c_bus": "I2C bus",
    "spi0": "SPI0 device",
    "gpio_chip": "GPIO chip",
    "pwm": "PWM chip",
}
FAN_PROFILES = {
    "off": 0,
    "performance": 1,
    "cool": 2,
    "balanced": 3,
    "quiet": 4,
}


def available_oled_pages(peripherals):
    pages = []
    for peripheral in peripherals:
        if peripheral.startswith("oled_page_"):
            pages.append(peripheral.removeprefix("oled_page_"))
    return pages


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
            autostart_file = os.path.expanduser("~/.config/autostart/pironman5-dashboard.desktop")
            try:
                os.remove(autostart_file)
            except FileNotFoundError:
                pass
        else:
            print(f"Invalid value for auto start, it should be true/on/1 or false/off/0")
            quit()
    else:
        launch_browser()


def reload_running_service():
    result = subprocess.run(
        ("systemctl", "kill", "-s", "HUP", "pironman5.service"),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or "").strip() or "service reload signal failed"
        print(f"Config saved, but service reload was skipped: {message}", file=sys.stderr)
        return False
    print("Reloaded running service.")
    return True


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
    if isinstance(default, int) or key in INT_CONFIG_KEYS:
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
    if args.config_action == 'list':
        defaults = get_config_defaults()
        if args.json:
            payload = {}
            for field in iter_config_fields(defaults):
                if field.key not in defaults and field.key not in current_config.get("system", {}):
                    continue
                payload[field.key] = {
                    "description": field.description,
                    "type": field.value_type,
                    "reload": field.reload,
                    "allowed": list(field.allowed),
                    "default": defaults.get(field.key),
                }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        for field in iter_config_fields(defaults):
            if field.key not in defaults and field.key not in current_config.get("system", {}):
                continue
            default = defaults.get(field.key)
            default_text = f", default={format_config_value(default)}" if default is not None else ""
            print(f"{field.key}: {field.description} ({field.value_type}, {field.reload}{default_text})")
        return
    if args.config_action == 'explain':
        default = ensure_known_config_key(args.config_key)
        field = config_field(args.config_key)
        print(args.config_key)
        if field is None:
            print("Description: Undocumented config value.")
            print(f"Type: {type(default).__name__}")
            print("Reload: live")
        else:
            print(f"Description: {field.description}")
            print(f"Type: {field.value_type}")
            if field.allowed:
                print(f"Allowed: {', '.join(str(value) for value in field.allowed)}")
            print(f"Reload: {field.reload}")
        print(f"Default: {format_config_value(default)}")
        return
    if args.config_action == 'set':
        value = parse_config_value(args.config_key, args.config_value)
        if args.dry_run:
            print(f"Would set {args.config_key}: {format_config_value(value)}")
            print("Would reload running service after saving.")
            return
        try:
            update_config_file({'system': {args.config_key: value}}, config_path)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"Set {args.config_key}: {format_config_value(value)}")
        reload_running_service()
        return
    print("Invalid config command")
    quit()


def _fan_profile_name(mode):
    for name, value in FAN_PROFILES.items():
        if value == mode:
            return name
    return "custom"


def handle_fan_command(args, current_config, config_path):
    if args.fan_action == "list":
        for name, value in FAN_PROFILES.items():
            print(f"{name}: {value}")
        return
    if args.fan_action == "status":
        mode = get_system_config_value(current_config, "gpio_fan_mode", FAN_PROFILES["off"])
        if args.json:
            print(json.dumps({"profile": _fan_profile_name(mode), "mode": mode}, indent=2, sort_keys=True))
            return
        print(f"Fan profile: {_fan_profile_name(mode)} ({mode})")
        return
    if args.fan_action == "set":
        mode = FAN_PROFILES[args.profile]
        if args.dry_run:
            print(f"Would set fan profile: {args.profile} ({mode})")
            print("Would reload running service after saving.")
            return
        try:
            update_config_file({"system": {"gpio_fan_mode": mode}}, config_path)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"Set fan profile: {args.profile} ({mode})")
        reload_running_service()
        return
    print("Invalid fan command")
    quit()


def _write_config_patch(patch, config_path, dry_run_message=None, dry_run=False):
    if dry_run:
        if dry_run_message:
            print(dry_run_message)
        print("Would reload running service after saving.")
        return
    try:
        update_config_file({"system": patch}, config_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    reload_running_service()


def handle_oled_command(args, current_config, config_path):
    if args.oled_action == "status":
        enabled = bool(get_system_config_value(current_config, "oled_enable", True))
        pages = get_system_config_value(current_config, "oled_pages", [])
        timeout = get_system_config_value(current_config, "oled_sleep_timeout", 10)
        if args.json:
            print(json.dumps({"enabled": enabled, "pages": pages, "sleep_timeout": timeout}, indent=2, sort_keys=True))
            return
        print(f"OLED: {'on' if enabled else 'off'}")
        print(f"Pages: {', '.join(pages) if pages else 'none'}")
        print(f"Sleep timeout: {timeout}")
        return
    if args.oled_action == "on":
        _write_config_patch({"oled_enable": True}, config_path)
        print("Set OLED: on")
        return
    if args.oled_action == "off":
        _write_config_patch({"oled_enable": False}, config_path)
        print("Set OLED: off")
        return
    if args.oled_action == "sleep":
        _write_config_patch(
            {"oled_sleep_timeout": args.seconds},
            config_path,
            dry_run_message=f"Would set OLED sleep timeout: {args.seconds}",
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            if args.seconds == 0:
                print("Set OLED sleep timeout: disabled")
            else:
                print(f"Set OLED sleep timeout: {args.seconds}")
        return
    if args.oled_action == "pages":
        if args.pages_action == "list":
            pages = available_oled_pages(PERIPHERALS)
            print("OLED pages:")
            for page in pages:
                print(f"- {page}")
            return
        if args.pages_action == "set":
            available = set(available_oled_pages(PERIPHERALS))
            invalid = [page for page in args.pages if page not in available]
            if invalid:
                print(f"Invalid OLED page: {invalid[0]}", file=sys.stderr)
                raise SystemExit(1)
            _write_config_patch(
                {"oled_pages": args.pages},
                config_path,
                dry_run_message=f"Would set OLED pages: {', '.join(args.pages)}",
                dry_run=args.dry_run,
            )
            if not args.dry_run:
                print(f"Set OLED pages: {', '.join(args.pages)}")
            return
    print("Invalid OLED command")
    quit()


def _validate_rgb_time(value, label):
    import re
    from datetime import datetime

    if not re.match(RGB_TIME_RE, value):
        raise ValueError(f"{label} must use HH:MM format")
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError(f"{label} must use a valid 24-hour HH:MM time") from exc


def _print_rgb_list():
    from .runtime import RGB_AMBIENT_PROFILES, RGB_MODES, RGB_STATUS_PROFILES

    print(f"Modes: {', '.join(RGB_MODES)}")
    print(f"Ambient profiles: {', '.join(RGB_AMBIENT_PROFILES)}")
    print(f"Status profiles: {', '.join(RGB_STATUS_PROFILES)}")


def handle_rgb_command(args, _current_config, config_path):
    from .runtime import RGB_AMBIENT_PROFILES, RGB_STATUS_PROFILES

    if args.rgb_action == "list":
        _print_rgb_list()
        return

    if args.rgb_action == "off":
        _write_config_patch({"rgb_enable": False, "rgb_mode": "off"}, config_path)
        print("Set RGB mode: off")
        return

    if args.rgb_action == "set":
        patch = {"rgb_enable": True, "rgb_mode": args.rgb_mode, "rgb_profile": args.rgb_profile}
        if args.rgb_mode == "ambient":
            if args.rgb_profile not in RGB_AMBIENT_PROFILES:
                print(f"Invalid ambient RGB profile: {args.rgb_profile}")
                quit()
            patch.update(RGB_AMBIENT_PROFILES[args.rgb_profile])
        elif args.rgb_mode == "status":
            if args.rgb_profile not in RGB_STATUS_PROFILES:
                print(f"Invalid status RGB profile: {args.rgb_profile}")
                quit()
        else:
            print("Invalid RGB mode, it should be ambient or status")
            quit()
        _write_config_patch(patch, config_path)
        print(f"Set RGB mode: {args.rgb_mode} ({args.rgb_profile})")
        return

    if args.rgb_action == "night":
        if args.brightness < 0 or args.brightness > 100:
            print("Invalid RGB night brightness, it should be between 0 and 100")
            quit()
        try:
            _validate_rgb_time(args.from_time, "RGB night start")
            _validate_rgb_time(args.to_time, "RGB night end")
        except ValueError as exc:
            print(str(exc))
            quit()
        _write_config_patch(
            {
                "rgb_night_brightness": args.brightness,
                "rgb_night_start": args.from_time,
                "rgb_night_end": args.to_time,
            },
            config_path,
        )
        print(f"Set RGB night brightness: {args.brightness} from {args.from_time} to {args.to_time}")
        return

    print("Invalid RGB command")
    quit()


def remove_dashboard(pip_path):
    print("Remove Dashboard")
    try:
        subprocess.run([pip_path, "uninstall", "pm_dashboard", "-y"], check=False)
    except FileNotFoundError:
        print(f"Dashboard removal skipped: {pip_path} not found", file=sys.stderr)
    print("Dashboard removed, restart pironman5 to apply changes: sudo systemctl restart pironman5.service")


def _run_system_command(argv, prog="pironman5 system", update_command_name="update"):
    from .system import main as system_main

    system_main(argv, prog=prog, update_command_name=update_command_name)


def _route_system_command(argv):
    if not argv:
        return False
    command = argv[0]
    if command == "system":
        _run_system_command(argv[1:])
        return True
    if command in ("setup", "doctor", "status"):
        _run_system_command(argv, prog="pironman5")
        return True
    if command == "service" and len(argv) > 1:
        service_command = argv[1]
        service_args = argv[2:]
        if service_command == "refresh":
            _run_system_command(["refresh", *service_args], prog="pironman5 service", update_command_name="refresh")
            return True
        if service_command == "repair":
            _run_system_command(["repair", *service_args], prog="pironman5 service", update_command_name="repair")
            return True
        if service_command == "uninstall":
            _run_system_command(["uninstall", *service_args], prog="pironman5 service")
            return True
        if service_command == "logs":
            from .system import show_service_logs

            logs_parser = argparse.ArgumentParser(prog="pironman5 service logs")
            logs_parser.add_argument("-n", "--lines", type=int, default=80, help="Number of log lines to show")
            logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow service logs")
            logs_args = logs_parser.parse_args(service_args)
            show_service_logs(lines=logs_args.lines, follow=logs_args.follow)
            return True
    return False


def main():
    if _route_system_command(sys.argv[1:]):
        return
    if len(sys.argv) > 1 and sys.argv[1] == "detect":
        detect_parser = argparse.ArgumentParser(prog="pironman5 detect")
        detect_parser.add_argument("--json", action="store_true", help="Print detection results as JSON")
        detect_args = detect_parser.parse_args(sys.argv[2:])
        print_detect(json_output=detect_args.json)
        return

    __package_name__ = __name__.split('.')[0]
    CONFIG_PATH = "/opt/pironman5/config.json"
    PIP_PATH = "/opt/pironman5-venv/bin/pip"

    new_sys_config = {}
    help_requested = any(arg in ("-h", "--help") for arg in sys.argv[1:])

    parser = argparse.ArgumentParser(prog='pironman5',
                                    description=f'{NAME} command line interface')
    
    subparsers = parser.add_subparsers(dest="subcommand", title="Subcommands")

    parser.add_argument("-v", "--version", action="store_true", help="Show version")
    parser.add_argument("-c", "--config", action="store_true", help="Show config")
    parser.add_argument("-cp", "--config-path", nargs='?', default='', help="Config path")
    # vibration_switch
    if is_included(PERIPHERALS, "vibration_switch"):
        parser.add_argument("-vp", "--vibration-switch-pin", nargs='?', default='', help="Vibration switch pin")
        parser.add_argument("-vu", "--vibration-switch-pull-up", nargs='?', default='', help="Vibration switch pull up True/False")
    # rgb_matrix
    if is_included(PERIPHERALS, "rgb_matrix"):
        effect_list = [] if help_requested else RGB_MATRIX_EFFECT_LIST
        parser.add_argument("-rme", "--rgb-matrix-enable", nargs='?', default='', help="RGB enable True/False")
        parser.add_argument("-rms", "--rgb-matrix-style",  nargs='?', default='', help=f"RGB style: {effect_list}")
        parser.add_argument("-rmc", "--rgb-matrix-color", nargs='?', default='', help='RGB color in hex format without # (e.g. 00aabb)')
        parser.add_argument("-rmc2", "--rgb-matrix-color2", nargs='?', default='', help='RGB color in hex format without # (e.g. 00aabb)')
        parser.add_argument("-rmp", "--rgb-matrix-speed", nargs='?', default='', help="RGB speed 0-100")
        parser.add_argument("-rmb", "--rgb-matrix-brightness", nargs='?', default='', help="RGB brightness 0-100")
    # pipower5
    if is_included(PERIPHERALS, "pipower5"):
        # 定义pipower5子命令（用于调用独立的pipower5）
        subparsers.add_parser(
            "pipower5",
            add_help=False  # 禁用子命令的-h处理，确保透传
        )
    config_parser = subparsers.add_parser("config", help="Read or update config values")
    config_subparsers = config_parser.add_subparsers(dest="config_action")
    config_get_parser = config_subparsers.add_parser("get", help="Read a config value")
    config_get_parser.add_argument("config_key", help="System config key")
    config_list_parser = config_subparsers.add_parser("list", help="List known config values")
    config_list_parser.add_argument("--json", action="store_true", help="Print config metadata as JSON")
    config_explain_parser = config_subparsers.add_parser("explain", help="Explain a config value")
    config_explain_parser.add_argument("config_key", help="System config key")
    config_set_parser = config_subparsers.add_parser("set", help="Update a config value")
    config_set_parser.add_argument("config_key", help="System config key")
    config_set_parser.add_argument("config_value", help="New value")
    config_set_parser.add_argument("--dry-run", action="store_true", help="Preview the parsed value without saving")
    if is_included(PERIPHERALS, "ws2812"):
        rgb_parser = subparsers.add_parser("rgb", help="Manage case RGB lights")
        rgb_subparsers = rgb_parser.add_subparsers(dest="rgb_action")
        rgb_subparsers.add_parser("list", help="List RGB modes and profiles")
        rgb_set_parser = rgb_subparsers.add_parser("set", help="Set RGB mode and profile")
        rgb_set_parser.add_argument("rgb_mode", choices=["ambient", "status"], help="RGB behavior mode")
        rgb_set_parser.add_argument("rgb_profile", help="RGB profile name")
        rgb_night_parser = rgb_subparsers.add_parser("night", help="Set RGB night brightness schedule")
        rgb_night_parser.add_argument("--brightness", type=int, required=True, help="Night brightness 0-100")
        rgb_night_parser.add_argument("--from", dest="from_time", required=True, help="Night schedule start HH:MM")
        rgb_night_parser.add_argument("--to", dest="to_time", required=True, help="Night schedule end HH:MM")
        rgb_subparsers.add_parser("off", help="Turn RGB off")
    detect_parser = subparsers.add_parser("detect", help="Detect variant and optional hardware")
    detect_parser.add_argument("--json", action="store_true", help="Print detection results as JSON")
    fan_parser = subparsers.add_parser("fan", help="Manage case fan profile")
    fan_subparsers = fan_parser.add_subparsers(dest="fan_action")
    fan_subparsers.add_parser("list", help="List fan profiles")
    fan_status_parser = fan_subparsers.add_parser("status", help="Show current fan profile")
    fan_status_parser.add_argument("--json", action="store_true", help="Print fan status as JSON")
    fan_set_parser = fan_subparsers.add_parser("set", help="Set fan profile")
    fan_set_parser.add_argument("profile", choices=sorted(FAN_PROFILES), help="Fan profile")
    fan_set_parser.add_argument("--dry-run", action="store_true", help="Preview the change without saving")
    oled_parser = subparsers.add_parser("oled", help="Manage OLED display")
    oled_subparsers = oled_parser.add_subparsers(dest="oled_action")
    oled_status_parser = oled_subparsers.add_parser("status", help="Show OLED settings")
    oled_status_parser.add_argument("--json", action="store_true", help="Print OLED status as JSON")
    oled_subparsers.add_parser("on", help="Enable OLED")
    oled_subparsers.add_parser("off", help="Disable OLED")
    oled_sleep_parser = oled_subparsers.add_parser(
        "sleep",
        help="Set OLED sleep timeout in seconds (set to 0 to disable timeout)",
    )
    oled_sleep_parser.add_argument("seconds", type=int, help="Sleep timeout in seconds")
    oled_sleep_parser.add_argument("--dry-run", action="store_true", help="Preview the change without saving")
    oled_pages_parser = oled_subparsers.add_parser("pages", help="Manage OLED pages")
    oled_pages_subparsers = oled_pages_parser.add_subparsers(dest="pages_action")
    oled_pages_subparsers.add_parser("list", help="List available OLED pages")
    oled_pages_set_parser = oled_pages_subparsers.add_parser("set", help="Set OLED pages")
    oled_pages_set_parser.add_argument("pages", nargs="+", help="OLED pages")
    oled_pages_set_parser.add_argument("--dry-run", action="store_true", help="Preview the change without saving")
    subparsers.add_parser("setup", help="Apply privileged system integration")
    subparsers.add_parser("doctor", help="Check system integration")
    service_parser = subparsers.add_parser("service", help="Manage the systemd service install")
    service_subparsers = service_parser.add_subparsers(dest="service_action")
    service_subparsers.add_parser("refresh", help="Refresh the service install and restart")
    service_subparsers.add_parser("repair", help="Repair install drift by refreshing the service install")
    service_subparsers.add_parser("uninstall", help="Remove privileged system integration")
    dashboard_parser = subparsers.add_parser("dashboard", help="Manage dashboard")
    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_action")
    dashboard_subparsers.add_parser("remove", help="Remove dashboard package")
    subparsers.add_parser("start", help="Start Pironman5")
    subparsers.add_parser("stop", help="Stop Pironman5")
    launch_browser_parser = subparsers.add_parser("launch-browser", help="Launch browser")
    launch_browser_parser.add_argument("-a", "--auto-start", nargs='?', default='', help="Auto start browser on boot")

    # parse args
    # -----------------------------------------------------------
    # args = parser.parse_args()
    args, remaining_args = parser.parse_known_args()
    if remaining_args and args.subcommand != "pipower5":
        parser.error(f"unrecognized arguments: {' '.join(remaining_args)}")

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

    if args.subcommand == 'start':
        from .pironman5 import Pironman5
        pironman5 = Pironman5(config_path=config_path)
        pironman5.start()
        return
    if args.subcommand == 'stop':
        subprocess.run(["systemctl", "stop", "pironman5.service"], check=False)
        return
    if args.subcommand == 'launch-browser':
        handle_launch_browser(args.auto_start, TRUE_LIST, FALSE_LIST)
        return
    if args.subcommand == 'dashboard':
        if args.dashboard_action == 'remove':
            remove_dashboard(PIP_PATH)
            return
        dashboard_parser.print_help()
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
    if args.subcommand == 'fan':
        handle_fan_command(args, current_config, config_path)
        return
    if args.subcommand == 'oled':
        handle_oled_command(args, current_config, config_path)
        return
    if args.subcommand == 'rgb':
        handle_rgb_command(args, current_config, config_path)
        return

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
                if args.rgb_matrix_style not in RGB_MATRIX_EFFECT_LIST:
                    print(f"Invalid value for RGB Matrix style: {args.rgb_matrix_style}, it should be one of {RGB_MATRIX_EFFECT_LIST}")
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
        try:
            update_config_file({'system': new_sys_config}, config_path)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        reload_running_service()
