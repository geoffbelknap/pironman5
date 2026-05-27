import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from importlib.resources import files as resource_files
from pathlib import Path

from .variants import PRODUCT_DEFINITIONS, detect_hardware_variant, get_product_definition, normalize_variant_key

MODULES_FILE = Path("/etc/modules-load.d/pironman5.conf")
SERVICE_FILE = Path("/etc/systemd/system/pironman5.service")
UDEV_RULES_FILE = Path("/etc/udev/rules.d/99-com.rules")
WRAPPER_FILE = Path("/usr/local/bin/pironman5")
WORK_DIR = Path("/opt/pironman5")
SERVICE_VENV = Path("/opt/pironman5-venv")
LOG_DIR = Path("/var/log/pironman5")
SERVICE_NAME = "pironman5.service"
SERVICE_USER = "pironman5"


@dataclass(frozen=True)
class Command:
    description: str
    args: tuple

    def shell(self):
        import shlex
        return " ".join(shlex.quote(str(arg)) for arg in self.args)


def _selected_variant(variant):
    if variant != "auto":
        return normalize_variant_key(variant), "selected"
    detected = detect_hardware_variant()
    return detected["variant"], detected["source"]


def _plan_lines(variant):
    variant_key, source = _selected_variant(variant)
    product = get_product_definition(variant_key)
    overlays = product.get("dt_overlays", []) if product else []
    config_txt = product.get("config_txt", {}) if product else {}

    lines = [
        "System setup plan",
        f"Variant: {product['name']} ({variant_key}, {source})",
        "No changes made.",
        "",
        "Privileged changes:",
    ]
    for overlay in overlays:
        lines.append(f"- Install overlay: /boot/firmware/overlays/{overlay}")
    if "oled" in product.get("modules", []):
        lines.append("- Write module config: /etc/modules-load.d/pironman5.conf (i2c-dev)")
    elif config_txt:
        lines.append("- Write module config: /etc/modules-load.d/pironman5.conf when I2C devices are enabled")
    for name, value in config_txt.items():
        lines.append(f"- Set boot config: {name}={value}")
    lines.extend([
        "- Install udev/device access rules for i2c, spi, gpio, and pwm devices",
        "- Create or update the pironman5 service user and systemd service",
    ])
    return lines


def _overlay_dir():
    for path in (Path("/boot/firmware/overlays"), Path("/boot/overlays"), Path("/boot/firmware/current/overlays")):
        if path.exists():
            return path
    return Path("/boot/firmware/overlays")


def _asset_path(*parts):
    return Path(str(resource_files("pironman5").joinpath("assets", *parts)))


def _variant_product(variant):
    variant_key, source = _selected_variant(variant)
    return variant_key, source, get_product_definition(variant_key)


def _wrapper_source():
    return f"""#!{SERVICE_VENV / "bin" / "python"}
from pironman5._cli import main

if __name__ == "__main__":
    main()
"""


def _install_spec():
    try:
        direct_url = metadata.distribution("pironman5").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        direct_url = None
    if direct_url:
        data = json.loads(direct_url)
        url = data.get("url")
        vcs_info = data.get("vcs_info", {})
        revision = vcs_info.get("requested_revision") or vcs_info.get("commit_id")
        if data.get("vcs_info", {}).get("vcs") == "git" and url and revision:
            return f"git+{url}@{revision}"
        if url and data.get("dir_info", {}).get("editable") is not None:
            return url
    return str(Path(__file__).resolve().parents[1])


def _create_or_refresh_venv_commands(refresh_venv):
    install_spec = _install_spec()
    if refresh_venv:
        return [
            Command("Remove service application venv", ("rm", "-rf", str(SERVICE_VENV))),
            Command("Create service application venv directory", ("install", "-d", "-m", "0755", "-o", "root", "-g", "root", str(SERVICE_VENV))),
            Command("Create service application venv", ("python3", "-m", "venv", str(SERVICE_VENV))),
            Command("Upgrade service application installer", (str(SERVICE_VENV / "bin" / "pip"), "install", "--upgrade", "pip")),
            Command("Install service application package", (str(SERVICE_VENV / "bin" / "pip"), "install", "--upgrade", install_spec)),
            Command("Make service application venv non-writable by group/other", ("chmod", "-R", "go-w", str(SERVICE_VENV))),
        ]

    setup_script = (
        f"if [ ! -x {SERVICE_VENV / 'bin' / 'python'} ]; then "
        f"install -d -m 0755 -o root -g root {SERVICE_VENV} && "
        f"python3 -m venv {SERVICE_VENV} && "
        f"{SERVICE_VENV / 'bin' / 'pip'} install --upgrade pip && "
        f"{SERVICE_VENV / 'bin' / 'pip'} install --upgrade {install_spec} && "
        f"chmod -R go-w {SERVICE_VENV}; "
        "fi"
    )
    return [
        Command("Ensure service application venv", ("sh", "-c", setup_script)),
    ]


def setup_commands(variant, refresh_venv=False):
    variant_key, _source, product = _variant_product(variant)
    overlay_dir = _overlay_dir()
    commands = [
        Command("Create service group", ("sh", "-c", f"getent group {SERVICE_USER} >/dev/null || groupadd -r {SERVICE_USER}")),
        Command("Create service user", ("sh", "-c", f"getent passwd {SERVICE_USER} >/dev/null || useradd -r -g {SERVICE_USER} -s /sbin/nologin -d {WORK_DIR} --no-create-home {SERVICE_USER}")),
        Command("Create service home", ("install", "-d", "-m", "0750", "-o", SERVICE_USER, "-g", SERVICE_USER, str(WORK_DIR))),
        Command("Create log directory", ("install", "-d", "-m", "0750", "-o", SERVICE_USER, "-g", SERVICE_USER, str(LOG_DIR))),
    ]
    commands.extend(_create_or_refresh_venv_commands(refresh_venv))
    commands.extend([
        Command("Write selected variant", ("install", "-m", "0640", "-o", SERVICE_USER, "-g", SERVICE_USER, "/dev/stdin", str(WORK_DIR / ".variant"))),
        Command("Install CLI wrapper", ("install", "-m", "0755", "-o", "root", "-g", "root", "/dev/stdin", str(WRAPPER_FILE))),
        Command("Install udev rules", ("install", "-m", "0644", "-o", "root", "-g", "root", str(_asset_path("bin", "99-com.rules")), str(UDEV_RULES_FILE))),
        Command("Write module load config", ("install", "-m", "0644", "-o", "root", "-g", "root", "/dev/stdin", str(MODULES_FILE))),
        Command("Install systemd service", ("install", "-m", "0644", "-o", "root", "-g", "root", str(_asset_path("bin", SERVICE_NAME)), str(SERVICE_FILE))),
        Command("Reload systemd", ("systemctl", "daemon-reload")),
        Command("Enable service", ("systemctl", "enable", SERVICE_NAME)),
    ])
    for group in ("i2c", "spi", "gpio", "input", "video"):
        commands.append(Command(f"Add service user to {group}", ("sh", "-c", f"getent group {group} >/dev/null && usermod -aG {group} {SERVICE_USER} || true")))
    for overlay in product.get("dt_overlays", []):
        commands.append(Command(
            f"Install overlay {overlay}",
            ("install", "-m", "0644", "-o", "root", "-g", "root", str(_asset_path("overlays", overlay)), str(overlay_dir / overlay)),
        ))
    commands.append(Command("Restart service", ("systemctl", "restart", SERVICE_NAME)))
    return variant_key, commands


def uninstall_commands(variant, purge=False):
    _variant_key, _source, product = _variant_product(variant)
    overlay_dir = _overlay_dir()
    commands = [
        Command("Stop service", ("systemctl", "stop", SERVICE_NAME)),
        Command("Disable service", ("systemctl", "disable", SERVICE_NAME)),
        Command("Remove service file", ("rm", "-f", str(SERVICE_FILE))),
        Command("Remove CLI wrapper", ("rm", "-f", str(WRAPPER_FILE))),
        Command("Remove service application venv", ("rm", "-rf", str(SERVICE_VENV))),
        Command("Remove module load config", ("rm", "-f", str(MODULES_FILE))),
        Command("Remove udev rules", ("rm", "-f", str(UDEV_RULES_FILE))),
    ]
    for overlay in product.get("dt_overlays", []):
        commands.append(Command(f"Remove overlay {overlay}", ("rm", "-f", str(overlay_dir / overlay))))
    if purge:
        commands.extend([
            Command("Remove runtime state", ("rm", "-rf", str(WORK_DIR))),
            Command("Remove logs", ("rm", "-rf", str(LOG_DIR))),
        ])
    commands.append(Command("Reload systemd", ("systemctl", "daemon-reload")))
    return commands


def _run_commands(commands, dry_run, stdin_by_description=None):
    stdin_by_description = stdin_by_description or {}
    if dry_run:
        print("DRY RUN: no changes made.")
        for command in commands:
            print(command.shell())
        return
    if os.geteuid() != 0:
        print("pironman5 system setup must be run as root; use sudo.", file=sys.stderr)
        raise SystemExit(1)
    for command in commands:
        subprocess.run(
            command.args,
            input=stdin_by_description.get(command.description),
            text=True,
            check=True,
        )


def _doctor_lines(variant):
    _variant_key, _source, product = _variant_product(variant)
    overlay_dir = _overlay_dir()
    checks = [
        WRAPPER_FILE,
        SERVICE_FILE,
        MODULES_FILE,
        UDEV_RULES_FILE,
        SERVICE_VENV / "bin" / "python",
        WORK_DIR / ".variant",
    ]
    checks.extend(overlay_dir / overlay for overlay in product.get("dt_overlays", []))
    lines = ["System setup doctor"]
    for path in checks:
        state = "ok" if path.exists() else "missing"
        lines.append(f"- {state}: {path}")
    lines.extend(_doctor_status_lines())
    return lines


def _command_output(args):
    try:
        result = subprocess.run(args, check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return "unknown"
    value = result.stdout.strip()
    return value or "unknown"


def _wrapper_target():
    if not WRAPPER_FILE.exists():
        return "missing"
    try:
        first_line = WRAPPER_FILE.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError, UnicodeDecodeError):
        return "unreadable"
    if first_line.startswith("#!"):
        return first_line[2:]
    return "invalid"


def _variant_marker():
    variant_path = WORK_DIR / ".variant"
    if not variant_path.exists():
        return "missing"
    try:
        return variant_path.read_text(encoding="utf-8").strip() or "empty"
    except OSError:
        return "unreadable"


def _legacy_i2c_dev_count():
    modules_conf = Path("/etc/modules-load.d/modules.conf")
    if not modules_conf.exists():
        return 0
    try:
        return sum(1 for line in modules_conf.read_text(encoding="utf-8").splitlines() if line.strip() == "i2c-dev")
    except OSError:
        return "unknown"


def _doctor_status_lines():
    return [
        f"- service active: {_command_output(('systemctl', 'is-active', SERVICE_NAME))}",
        f"- service enabled: {_command_output(('systemctl', 'is-enabled', SERVICE_NAME))}",
        f"- current variant: {_variant_marker()}",
        f"- wrapper target: {_wrapper_target()}",
        f"- legacy modules.conf i2c-dev entries: {_legacy_i2c_dev_count()}",
    ]


def build_parser():
    parser = argparse.ArgumentParser(prog="pironman5 system", description="Manage Pironman 5 system integration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    variant_choices = ["auto", *sorted(PRODUCT_DEFINITIONS)]
    plan = subparsers.add_parser("plan", help="Show privileged setup actions without changing the system")
    plan.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    setup = subparsers.add_parser("setup", help="Apply privileged system integration")
    setup.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    setup.add_argument("--refresh-venv", action="store_true", help="Recreate and reinstall the root-owned service virtualenv")
    setup.add_argument("--dry-run", action="store_true", help="Print commands without changing the system")
    doctor = subparsers.add_parser("doctor", help="Check privileged system integration")
    doctor.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    uninstall = subparsers.add_parser("uninstall", help="Remove privileged system integration")
    uninstall.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    uninstall.add_argument("--purge", action="store_true", help="Also remove runtime state and logs")
    uninstall.add_argument("--dry-run", action="store_true", help="Print commands without changing the system")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        print("\n".join(_plan_lines(args.variant)))
    elif args.command == "setup":
        variant_key, commands = setup_commands(args.variant, refresh_venv=args.refresh_venv)
        _run_commands(
            commands,
            args.dry_run,
            {
                "Write selected variant": f"{variant_key}\n",
                "Install CLI wrapper": _wrapper_source(),
                "Write module load config": "i2c-dev\n",
            },
        )
    elif args.command == "doctor":
        print("\n".join(_doctor_lines(args.variant)))
    elif args.command == "uninstall":
        _run_commands(uninstall_commands(args.variant, purge=args.purge), args.dry_run)
