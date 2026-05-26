import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from importlib.resources import files as resource_files
from pathlib import Path

from .variants import PRODUCT_DEFINITIONS, detect_hardware_variant, get_product_definition, normalize_variant_key

MODULES_FILE = Path("/etc/modules-load.d/pironman5.conf")
SERVICE_FILE = Path("/etc/systemd/system/pironman5.service")
UDEV_RULES_FILE = Path("/etc/udev/rules.d/99-com.rules")
WRAPPER_FILE = Path("/usr/local/bin/pironman5")
WORK_DIR = Path("/opt/pironman5")
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
    return f"""#!{sys.executable}
from pironman5._cli import main

if __name__ == "__main__":
    main()
"""


def setup_commands(variant):
    variant_key, _source, product = _variant_product(variant)
    overlay_dir = _overlay_dir()
    commands = [
        Command("Create service group", ("sh", "-c", f"getent group {SERVICE_USER} >/dev/null || groupadd -r {SERVICE_USER}")),
        Command("Create service user", ("sh", "-c", f"getent passwd {SERVICE_USER} >/dev/null || useradd -r -g {SERVICE_USER} -s /sbin/nologin -d {WORK_DIR} --no-create-home {SERVICE_USER}")),
        Command("Create service home", ("install", "-d", "-m", "0750", "-o", SERVICE_USER, "-g", SERVICE_USER, str(WORK_DIR))),
        Command("Create log directory", ("install", "-d", "-m", "0750", "-o", SERVICE_USER, "-g", SERVICE_USER, str(LOG_DIR))),
        Command("Write selected variant", ("install", "-m", "0640", "-o", SERVICE_USER, "-g", SERVICE_USER, "/dev/stdin", str(WORK_DIR / ".variant"))),
        Command("Install CLI wrapper", ("install", "-m", "0755", "-o", "root", "-g", "root", "/dev/stdin", str(WRAPPER_FILE))),
        Command("Install udev rules", ("install", "-m", "0644", "-o", "root", "-g", "root", str(_asset_path("bin", "99-com.rules")), str(UDEV_RULES_FILE))),
        Command("Write module load config", ("install", "-m", "0644", "-o", "root", "-g", "root", "/dev/stdin", str(MODULES_FILE))),
        Command("Install systemd service", ("install", "-m", "0644", "-o", "root", "-g", "root", str(_asset_path("bin", SERVICE_NAME)), str(SERVICE_FILE))),
        Command("Reload systemd", ("systemctl", "daemon-reload")),
        Command("Enable service", ("systemctl", "enable", SERVICE_NAME)),
    ]
    for group in ("i2c", "spi", "gpio", "input", "video"):
        commands.append(Command(f"Add service user to {group}", ("sh", "-c", f"getent group {group} >/dev/null && usermod -aG {group} {SERVICE_USER} || true")))
    for overlay in product.get("dt_overlays", []):
        commands.append(Command(
            f"Install overlay {overlay}",
            ("install", "-m", "0644", "-o", "root", "-g", "root", str(_asset_path("overlays", overlay)), str(overlay_dir / overlay)),
        ))
    return variant_key, commands


def uninstall_commands(variant):
    _variant_key, _source, product = _variant_product(variant)
    overlay_dir = _overlay_dir()
    commands = [
        Command("Stop service", ("systemctl", "stop", SERVICE_NAME)),
        Command("Disable service", ("systemctl", "disable", SERVICE_NAME)),
        Command("Remove service file", ("rm", "-f", str(SERVICE_FILE))),
        Command("Remove CLI wrapper", ("rm", "-f", str(WRAPPER_FILE))),
        Command("Remove module load config", ("rm", "-f", str(MODULES_FILE))),
        Command("Remove udev rules", ("rm", "-f", str(UDEV_RULES_FILE))),
    ]
    for overlay in product.get("dt_overlays", []):
        commands.append(Command(f"Remove overlay {overlay}", ("rm", "-f", str(overlay_dir / overlay))))
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
        WORK_DIR / ".variant",
    ]
    checks.extend(overlay_dir / overlay for overlay in product.get("dt_overlays", []))
    lines = ["System setup doctor"]
    for path in checks:
        state = "ok" if path.exists() else "missing"
        lines.append(f"- {state}: {path}")
    return lines


def build_parser():
    parser = argparse.ArgumentParser(prog="pironman5 system", description="Manage Pironman 5 system integration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    variant_choices = ["auto", *sorted(PRODUCT_DEFINITIONS)]
    plan = subparsers.add_parser("plan", help="Show privileged setup actions without changing the system")
    plan.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    setup = subparsers.add_parser("setup", help="Apply privileged system integration")
    setup.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    setup.add_argument("--dry-run", action="store_true", help="Print commands without changing the system")
    doctor = subparsers.add_parser("doctor", help="Check privileged system integration")
    doctor.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    uninstall = subparsers.add_parser("uninstall", help="Remove privileged system integration")
    uninstall.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    uninstall.add_argument("--dry-run", action="store_true", help="Print commands without changing the system")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        print("\n".join(_plan_lines(args.variant)))
    elif args.command == "setup":
        variant_key, commands = setup_commands(args.variant)
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
        _run_commands(uninstall_commands(args.variant), args.dry_run)
