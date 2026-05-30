import argparse
import grp
import json
import os
import pwd
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from importlib.resources import files as resource_files
from pathlib import Path

from .variants import PRODUCT_DEFINITIONS, detect_hardware_variant, detect_optional_hardware, get_product_definition, normalize_variant_key
from .variants.hardware_policy import (
    OPTIONAL_HARDWARE_CHOICES,
    filter_enabled_modules,
    normalize_enabled_optional_hardware,
    normalize_optional_hardware_name,
)

MODULES_FILE = Path("/etc/modules-load.d/pironman5.conf")
SERVICE_FILE = Path("/etc/systemd/system/pironman5.service")
UDEV_RULES_FILE = Path("/etc/udev/rules.d/99-com.rules")
WRAPPER_FILE = Path("/usr/local/bin/pironman5")
WORK_DIR = Path("/opt/pironman5")
CONFIG_FILE = WORK_DIR / "config.json"
OPTIONAL_HARDWARE_FILE = WORK_DIR / ".enabled_optional_hardware"
SERVICE_VENV = Path("/opt/pironman5-venv")
LOG_DIR = Path("/var/log/pironman5")
SERVICE_NAME = "pironman5.service"
SERVICE_USER = "pironman5"
REMOVABLE_TREES = {
    SERVICE_VENV,
    WORK_DIR,
    LOG_DIR,
}
LEGACY_HARDWARE_MODULES = {
    "pipower5",
    "sf_rgb_led",
}
LEGACY_UPS_EXTRA = "legacy-ups"


@dataclass(frozen=True)
class Command:
    description: str
    args: tuple

    def shell(self):
        import shlex
        if self.args[0] == "ensure-group":
            return f"getent group {shlex.quote(str(self.args[1]))} >/dev/null || groupadd -r {shlex.quote(str(self.args[1]))}"
        if self.args[0] == "ensure-user":
            user, group, home = self.args[1:4]
            return (
                f"getent passwd {shlex.quote(str(user))} >/dev/null || "
                f"useradd -r -g {shlex.quote(str(group))} -s /sbin/nologin "
                f"-d {shlex.quote(str(home))} --no-create-home {shlex.quote(str(user))}"
            )
        if self.args[0] == "add-user-to-group-if-exists":
            user, group = self.args[1:3]
            return f"getent group {shlex.quote(str(group))} >/dev/null && usermod -aG {shlex.quote(str(group))} {shlex.quote(str(user))} || true"
        if self.args[0] == "ensure-service-venv":
            install_spec = self.args[1]
            return "\n".join([
                f"install -d -m 0755 -o root -g root {shlex.quote(str(SERVICE_VENV))}",
                f"python3 -m venv {shlex.quote(str(SERVICE_VENV))}",
                f"{shlex.quote(str(SERVICE_VENV / 'bin' / 'pip'))} install --upgrade pip",
                f"{shlex.quote(str(SERVICE_VENV / 'bin' / 'pip'))} install --upgrade {shlex.quote(str(install_spec))}",
                f"chgrp -R {shlex.quote(SERVICE_USER)} {shlex.quote(str(SERVICE_VENV))}",
                f"chmod -R g+rX,o-rwx {shlex.quote(str(SERVICE_VENV))}",
            ])
        if self.args[0] == "remove-tree":
            return f"rm -rf {shlex.quote(str(self.args[1]))}"
        if self.args[0] == "chown-if-exists":
            user, group, path = self.args[1:4]
            return f"test ! -e {shlex.quote(str(path))} || chown {shlex.quote(str(user))}:{shlex.quote(str(group))} {shlex.quote(str(path))}"
        if self.args[0] == "chmod-if-exists":
            mode, path = self.args[1:3]
            return f"test ! -e {shlex.quote(str(path))} || chmod {shlex.quote(str(mode))} {shlex.quote(str(path))}"
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


def _setup_product(variant, enabled_optional_hardware=None):
    variant_key, source, product = _variant_product(variant)
    product = dict(product)
    enabled_optional_hardware = normalize_enabled_optional_hardware(enabled_optional_hardware or [])
    product["modules"] = filter_enabled_modules(
        product.get("modules", []),
        detected_hardware=detect_optional_hardware(),
        enabled_optional_hardware=enabled_optional_hardware,
    )
    product["enabled_optional_hardware"] = enabled_optional_hardware
    return variant_key, source, product


def _wrapper_source():
    return f"""#!{SERVICE_VENV / "bin" / "python"}
from pironman5._cli import main

if __name__ == "__main__":
    main()
"""


def _with_extras(install_spec, extras):
    if not extras:
        return install_spec
    extras_spec = ",".join(sorted(extras))
    if install_spec.startswith(("git+", "file://")):
        return f"pironman5[{extras_spec}] @ {install_spec}"
    return f"{install_spec}[{extras_spec}]"


def _install_spec(extras=()):
    try:
        direct_url = metadata.distribution("pironman5").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        direct_url = None
    install_spec = str(Path(__file__).resolve().parents[1])
    if direct_url:
        data = json.loads(direct_url)
        url = data.get("url")
        vcs_info = data.get("vcs_info", {})
        revision = vcs_info.get("requested_revision") or vcs_info.get("commit_id")
        if data.get("vcs_info", {}).get("vcs") == "git" and url and revision:
            install_spec = f"git+{url}@{revision}"
            return _with_extras(install_spec, extras)
        if url and data.get("dir_info", {}).get("editable") is not None:
            install_spec = url
    return _with_extras(install_spec, extras)


def _service_package_extras(product):
    extras = []
    modules = set(product.get("modules", []))
    if modules & LEGACY_HARDWARE_MODULES:
        extras.append(LEGACY_UPS_EXTRA)
    if "pipower5" in modules and "pipower5" in product.get("enabled_optional_hardware", ()):
        extras.append("ups")
    return tuple(extras)


def _installed_variant_product():
    marker = _variant_marker()
    if marker in PRODUCT_DEFINITIONS:
        _variant_key, _source, product = _setup_product(marker, _enabled_optional_hardware_marker())
        return product
    return {}


def _enabled_optional_hardware_marker():
    try:
        if not OPTIONAL_HARDWARE_FILE.exists():
            return set()
        return normalize_enabled_optional_hardware(OPTIONAL_HARDWARE_FILE.read_text(encoding="utf-8").splitlines())
    except OSError:
        return set()


def _create_or_refresh_venv_commands(refresh_venv, product=None):
    install_spec = _install_spec(_service_package_extras(product or {}))
    if refresh_venv:
        return [
            Command("Remove service application venv", ("remove-tree", str(SERVICE_VENV))),
            Command("Create service application venv directory", ("install", "-d", "-m", "0755", "-o", "root", "-g", "root", str(SERVICE_VENV))),
            Command("Create service application venv", ("python3", "-m", "venv", str(SERVICE_VENV))),
            Command("Upgrade service application installer", (str(SERVICE_VENV / "bin" / "pip"), "install", "--upgrade", "pip")),
            Command("Install service application package", (str(SERVICE_VENV / "bin" / "pip"), "install", "--upgrade", install_spec)),
            Command("Set service application venv group", ("chgrp", "-R", SERVICE_USER, str(SERVICE_VENV))),
            Command("Make service application venv readable by service group", ("chmod", "-R", "g+rX,o-rwx", str(SERVICE_VENV))),
        ]

    return [
        Command("Ensure service application venv", ("ensure-service-venv", install_spec)),
    ]


def upgrade_service_commands():
    commands = _create_or_refresh_venv_commands(refresh_venv=True, product=_installed_variant_product())
    commands.extend([
        Command("Install CLI wrapper", ("install", "-m", "0755", "-o", "root", "-g", "root", "/dev/stdin", str(WRAPPER_FILE))),
        Command("Restart service", ("systemctl", "restart", SERVICE_NAME)),
    ])
    return commands


def setup_commands(variant, refresh_venv=False, enabled_optional_hardware=None):
    variant_key, _source, product = _setup_product(variant, enabled_optional_hardware)
    overlay_dir = _overlay_dir()
    commands = [
        Command("Create service group", ("ensure-group", SERVICE_USER)),
        Command("Create service user", ("ensure-user", SERVICE_USER, SERVICE_USER, str(WORK_DIR))),
        Command("Create service home", ("install", "-d", "-m", "0750", "-o", SERVICE_USER, "-g", SERVICE_USER, str(WORK_DIR))),
        Command("Repair config owner", ("chown-if-exists", SERVICE_USER, SERVICE_USER, str(CONFIG_FILE))),
        Command("Repair config mode", ("chmod-if-exists", "0640", str(CONFIG_FILE))),
        Command("Create log directory", ("install", "-d", "-m", "0750", "-o", SERVICE_USER, "-g", SERVICE_USER, str(LOG_DIR))),
    ]
    commands.extend(_create_or_refresh_venv_commands(refresh_venv, product))
    commands.extend([
        Command("Write selected variant", ("install", "-m", "0640", "-o", SERVICE_USER, "-g", SERVICE_USER, "/dev/stdin", str(WORK_DIR / ".variant"))),
        Command("Write enabled optional hardware", ("install", "-m", "0640", "-o", SERVICE_USER, "-g", SERVICE_USER, "/dev/stdin", str(OPTIONAL_HARDWARE_FILE))),
        Command("Install CLI wrapper", ("install", "-m", "0755", "-o", "root", "-g", "root", "/dev/stdin", str(WRAPPER_FILE))),
        Command("Install udev rules", ("install", "-m", "0644", "-o", "root", "-g", "root", str(_asset_path("bin", "99-com.rules")), str(UDEV_RULES_FILE))),
        Command("Write module load config", ("install", "-m", "0644", "-o", "root", "-g", "root", "/dev/stdin", str(MODULES_FILE))),
        Command("Install systemd service", ("install", "-m", "0644", "-o", "root", "-g", "root", str(_asset_path("bin", SERVICE_NAME)), str(SERVICE_FILE))),
        Command("Reload systemd", ("systemctl", "daemon-reload")),
        Command("Enable service", ("systemctl", "enable", SERVICE_NAME)),
    ])
    for group in ("i2c", "spi", "gpio", "input", "video"):
        commands.append(Command(f"Add service user to {group}", ("add-user-to-group-if-exists", SERVICE_USER, group)))
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
        Command("Remove service application venv", ("remove-tree", str(SERVICE_VENV))),
        Command("Remove module load config", ("rm", "-f", str(MODULES_FILE))),
        Command("Remove udev rules", ("rm", "-f", str(UDEV_RULES_FILE))),
    ]
    for overlay in product.get("dt_overlays", []):
        commands.append(Command(f"Remove overlay {overlay}", ("rm", "-f", str(overlay_dir / overlay))))
    if purge:
        commands.extend([
            Command("Remove runtime state", ("remove-tree", str(WORK_DIR))),
            Command("Remove logs", ("remove-tree", str(LOG_DIR))),
        ])
    commands.append(Command("Reload systemd", ("systemctl", "daemon-reload")))
    return commands


def _run_service_venv_bootstrap(install_spec):
    if (SERVICE_VENV / "bin" / "python").exists():
        return
    subprocess.run(("install", "-d", "-m", "0755", "-o", "root", "-g", "root", str(SERVICE_VENV)), text=True, check=True)
    subprocess.run(("python3", "-m", "venv", str(SERVICE_VENV)), text=True, check=True)
    subprocess.run((str(SERVICE_VENV / "bin" / "pip"), "install", "--upgrade", "pip"), text=True, check=True)
    subprocess.run((str(SERVICE_VENV / "bin" / "pip"), "install", "--upgrade", install_spec), text=True, check=True)
    subprocess.run(("chgrp", "-R", SERVICE_USER, str(SERVICE_VENV)), text=True, check=True)
    subprocess.run(("chmod", "-R", "g+rX,o-rwx", str(SERVICE_VENV)), text=True, check=True)


def _run_internal_command(command):
    action = command.args[0]
    if action == "ensure-group":
        group = command.args[1]
        try:
            grp.getgrnam(group)
        except KeyError:
            subprocess.run(("groupadd", "-r", group), text=True, check=True)
        return True
    if action == "ensure-user":
        user, group, home = command.args[1:4]
        try:
            pwd.getpwnam(user)
        except KeyError:
            subprocess.run(("useradd", "-r", "-g", group, "-s", "/sbin/nologin", "-d", home, "--no-create-home", user), text=True, check=True)
        return True
    if action == "add-user-to-group-if-exists":
        user, group = command.args[1:3]
        try:
            grp.getgrnam(group)
        except KeyError:
            return True
        subprocess.run(("usermod", "-aG", group, user), text=True, check=True)
        return True
    if action == "ensure-service-venv":
        _run_service_venv_bootstrap(command.args[1])
        return True
    if action == "remove-tree":
        path = Path(command.args[1])
        if path not in REMOVABLE_TREES:
            raise ValueError(f"Refusing to remove unapproved tree: {path}")
        shutil.rmtree(path, ignore_errors=True)
        return True
    if action == "chown-if-exists":
        user, group, path = command.args[1:4]
        if Path(path).exists():
            shutil.chown(path, user=user, group=group)
        return True
    if action == "chmod-if-exists":
        mode, path = command.args[1:3]
        if Path(path).exists():
            os.chmod(path, int(mode, 8))
        return True
    return False


def _run_commands(
    commands,
    dry_run,
    stdin_by_description=None,
    dry_run_header=None,
    dry_run_summary=None,
    root_command="pironman5 system setup",
):
    stdin_by_description = stdin_by_description or {}
    if dry_run:
        if dry_run_header:
            print(dry_run_header)
            print("")
        print("DRY RUN: no changes made.")
        if dry_run_summary:
            print("")
            for line in dry_run_summary:
                print(line)
        print("")
        print("Commands:")
        for command in commands:
            print(command.shell())
        return
    if os.geteuid() != 0:
        print(f"{root_command} must be run as root; use sudo.", file=sys.stderr)
        raise SystemExit(1)
    for command in commands:
        if _run_internal_command(command):
            continue
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
    lines = ["Pironman 5 service doctor"]
    for path in checks:
        state = _path_state(path)
        lines.append(f"- {state}: {path}")
    lines.extend(_doctor_status_lines())
    return lines


def _setup_dry_run_summary(variant_key, source, product):
    lines = [
        f"Variant: {product['name']} ({variant_key}, {source})",
        "",
        "Privileged changes:",
        "- Create or update the pironman5 service user and group",
        "- Create /opt/pironman5, /opt/pironman5-venv, and /var/log/pironman5",
        "- Install the service package into the root-owned service venv",
        "- Install the pironman5 CLI wrapper, udev rules, module config, and overlays",
        "- Install and enable pironman5.service",
        "- Add the service user to hardware access groups when available",
        "- Restart pironman5.service",
    ]
    if product.get("enabled_optional_hardware"):
        enabled = ", ".join(sorted(product["enabled_optional_hardware"]))
        lines.insert(1, f"Enabled optional hardware: {enabled}")
    return lines


def _path_state(path):
    try:
        return "ok" if path.exists() else "missing"
    except OSError:
        return "unreadable"


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
    try:
        if not variant_path.exists():
            return "missing"
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
    user_info = _current_install_info()
    service_info = _service_install_info()
    lines = [
        f"- service active: {_command_output(('systemctl', 'is-active', SERVICE_NAME))}",
        f"- service enabled: {_command_output(('systemctl', 'is-enabled', SERVICE_NAME))}",
        f"- current variant: {_variant_marker()}",
        f"- wrapper target: {_wrapper_target()}",
        f"- pipx/user version: {user_info['version']}",
        f"- service version: {service_info['version']}",
        f"- pipx/user source: {user_info['source']}",
        f"- service source: {service_info['source']}",
        f"- install drift: {_install_drift(user_info, service_info)}",
        f"- legacy modules.conf i2c-dev entries: {_legacy_i2c_dev_count()}",
    ]
    lines.extend(_doctor_hardware_lines())
    return lines


def _doctor_hardware_lines():
    detected = detect_hardware_variant()
    product = get_product_definition(detected["variant"])
    product_name = product["name"] if product else detected["variant"]
    source = detected["source"]
    part_number = detected.get("part_number")
    source_label = f"{source} {part_number}" if part_number else source
    optional = detect_optional_hardware()
    optional_summary = ", ".join(
        f"{name}={'detected' if value else 'not detected'}"
        for name, value in sorted(optional.items())
    ) or "none"
    device_checks = (
        ("i2c device", Path("/dev/i2c-1")),
        ("spi device", Path("/dev/spidev0.0")),
        ("gpio chip", Path("/dev/gpiochip0")),
        ("pwm chip", Path("/sys/class/pwm/pwmchip0")),
    )
    lines = [
        f"- detected variant: {product_name} ({detected['variant']}, {source_label})",
        f"- optional hardware: {optional_summary}",
    ]
    lines.extend(f"- {label}: {_path_state(path)} {path}" for label, path in device_checks)
    return lines


def _current_install_info():
    return _distribution_info()


def _service_install_info():
    python = SERVICE_VENV / "bin" / "python"
    try:
        if not python.exists():
            return {"version": "missing", "source": "missing", "commit": None}
    except OSError:
        return {"version": "unreadable", "source": "unreadable", "commit": None}
    script = (
        "from pironman5.system import _distribution_info; "
        "import json; "
        "print(json.dumps(_distribution_info()))"
    )
    try:
        result = subprocess.run(
            (str(python), "-c", script),
            check=False,
            cwd="/",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return {"version": "unknown", "source": "unknown", "commit": None}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"version": "unknown", "source": "unknown", "commit": None}


def _distribution_info():
    try:
        dist = metadata.distribution("pironman5")
    except metadata.PackageNotFoundError:
        return {"version": "missing", "source": "missing", "commit": None}
    source, commit = _direct_url_info(dist.read_text("direct_url.json"))
    return {
        "version": dist.version,
        "source": source,
        "commit": commit,
    }


def _direct_url_info(direct_url):
    if not direct_url:
        return "unknown", None
    try:
        data = json.loads(direct_url)
    except json.JSONDecodeError:
        return "unknown", None
    url = data.get("url", "unknown")
    vcs_info = data.get("vcs_info", {})
    commit = vcs_info.get("commit_id")
    revision = vcs_info.get("requested_revision")
    if data.get("vcs_info", {}).get("vcs") == "git":
        if revision:
            return f"{url}@{revision}", commit
        if commit:
            return f"{url}@{commit}", commit
    return url, commit


def _install_drift(user_info, service_info):
    if service_info["version"] in ("missing", "unknown", "unreadable"):
        return service_info["version"]
    if user_info["version"] != service_info["version"]:
        return "version mismatch"
    if user_info.get("commit") and service_info.get("commit") and user_info["commit"] != service_info["commit"]:
        return "commit mismatch"
    if user_info["source"] != service_info["source"]:
        return "source mismatch"
    return "none"


def build_parser(prog="pironman5 system", update_command_name="update"):
    parser = argparse.ArgumentParser(prog=prog, description="Manage Pironman 5 system integration")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="{plan,setup,doctor,uninstall,update}")

    variant_choices = ["auto", *sorted(PRODUCT_DEFINITIONS)]
    plan = subparsers.add_parser("plan", help="Show privileged setup actions without changing the system")
    plan.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    setup = subparsers.add_parser("setup", help="Apply privileged system integration")
    setup.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    setup.add_argument("--with", dest="enabled_hardware", action="append", default=[], type=normalize_optional_hardware_name, choices=OPTIONAL_HARDWARE_CHOICES, help="Enable hardware that was not auto-detected")
    setup.add_argument("--enable-optional-hardware", dest="enabled_hardware", action="append", type=normalize_optional_hardware_name, choices=OPTIONAL_HARDWARE_CHOICES, help=argparse.SUPPRESS)
    setup.add_argument("--fresh", dest="refresh_venv", action="store_true", help="Recreate the service install")
    setup.add_argument("--refresh-venv", dest="refresh_venv", action="store_true", help=argparse.SUPPRESS)
    setup.add_argument("--dry-run", action="store_true", help="Print commands without changing the system")
    doctor = subparsers.add_parser("doctor", help="Check privileged system integration")
    doctor.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    uninstall = subparsers.add_parser("uninstall", help="Remove privileged system integration")
    uninstall.add_argument("--variant", choices=variant_choices, default="auto", type=normalize_variant_key)
    uninstall.add_argument("--purge", action="store_true", help="Also remove runtime state and logs")
    uninstall.add_argument("--dry-run", action="store_true", help="Print commands without changing the system")
    upgrade = subparsers.add_parser(update_command_name, help="Refresh the service install and restart")
    upgrade.add_argument("--dry-run", action="store_true", help="Print commands without changing the system")
    return parser


def main(argv=None, prog="pironman5 system", update_command_name="update"):
    parser = build_parser(prog=prog, update_command_name=update_command_name)
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)
    if argv and argv[0] == "upgrade-service":
        argv[0] = "update"
    args = parser.parse_args(argv)
    if update_command_name != "update" and args.command == update_command_name:
        args.command = "update"
    if args.command == "plan":
        print("\n".join(_plan_lines(args.variant)))
    elif args.command == "setup":
        enabled_optional_hardware = normalize_enabled_optional_hardware(args.enabled_hardware)
        variant_key, source, product = _setup_product(args.variant, enabled_optional_hardware)
        variant_key, commands = setup_commands(
            args.variant,
            refresh_venv=args.refresh_venv,
            enabled_optional_hardware=enabled_optional_hardware,
        )
        _run_commands(
            commands,
            args.dry_run,
            {
                "Write selected variant": f"{variant_key}\n",
                "Write enabled optional hardware": "".join(f"{name}\n" for name in sorted(enabled_optional_hardware)),
                "Install CLI wrapper": _wrapper_source(),
                "Write module load config": "i2c-dev\n",
            },
            dry_run_header="Pironman 5 setup dry run",
            dry_run_summary=_setup_dry_run_summary(variant_key, source, product),
            root_command=f"{prog} setup",
        )
    elif args.command == "doctor":
        print("\n".join(_doctor_lines(args.variant)))
    elif args.command == "uninstall":
        _run_commands(
            uninstall_commands(args.variant, purge=args.purge),
            args.dry_run,
            root_command=f"{prog} uninstall",
        )
    elif args.command == "update":
        _run_commands(
            upgrade_service_commands(),
            args.dry_run,
            {"Install CLI wrapper": _wrapper_source()},
            root_command=f"{prog} {update_command_name}",
        )
