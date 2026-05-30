# Pironman 5

A cleaner Pironman 5 software fork for Raspberry Pi 5 cases.

This fork keeps the command-line tool easy to install, moves the long-running
service into a dedicated system environment, and only installs optional hardware
packages when the matching hardware is detected or explicitly requested.

## Contents

- [About This Fork](#about-this-fork)
- [Install](#install)
- [Hardware Detection](#hardware-detection)
- [Common Commands](#common-commands)
- [RGB Lights](#rgb-lights)
- [Optional Hardware](#optional-hardware)
- [Service Administration](#service-administration)
- [Troubleshooting](#troubleshooting)
- [Compatibility](#compatibility)
- [Development](#development)
- [Release Checklist](#release-checklist)

## About This Fork

This project started from SunFounder's Pironman 5 package. The hardware support
is still for Pironman 5 family cases, but the install and service model has been
reworked:

- install the user-facing `pironman5` command with `pipx` or `uv`
- run privileged setup explicitly with `pironman5 setup`
- run systemd from `/opt/pironman5-venv`, not a user's home directory
- detect Pironman 5 hardware when possible
- keep dashboard, UPS, and legacy hardware dependencies optional
- use SQLite for local history instead of installing InfluxDB by default

Links:

- Fork repository: <https://github.com/geoffbelknap/pironman5>
- Latest stable release: <https://github.com/geoffbelknap/pironman5/releases/tag/v1.0.1>
- Upstream hardware documentation: <https://docs.sunfounder.com/projects/pironman5/en/latest/>

## Install

`pipx` is the primary install path. It installs the CLI without root. The
separate `setup` step applies the OS-level pieces the case needs: systemd,
udev/group access, device tree overlays, and the service virtual environment.

Use the absolute command path when running setup with `sudo`. Many systems reset
`sudo`'s `PATH`, so a bare command name may not find the pipx command.

```bash
sudo apt-get update
sudo apt-get install pipx -y
pipx ensurepath
pipx install git+https://github.com/geoffbelknap/pironman5.git@v1.0.1

PIRONMAN5_CLI="$(command -v pironman5)"
pironman5 setup --dry-run
sudo "$PIRONMAN5_CLI" setup
pironman5 doctor
```

To install a specific branch, tag, or commit, append the Git ref:

```bash
pipx install git+https://github.com/geoffbelknap/pironman5.git@v1.0.1
```

`uv` works too if you already use it:

```bash
uv tool install git+https://github.com/geoffbelknap/pironman5.git@v1.0.1

PIRONMAN5_CLI="$(command -v pironman5)"
pironman5 setup --dry-run
sudo "$PIRONMAN5_CLI" setup
pironman5 doctor
```

## Hardware Detection

`pironman5 detect` reports the case variant and optional hardware the tool can
see. Setup defaults to `--variant auto`; pass `--variant` only when detection is
unavailable or you intentionally want to override it.

```bash
pironman5 detect
pironman5 detect --json
pironman5 setup --variant max --dry-run
PIRONMAN5_CLI="$(command -v pironman5)"
sudo "$PIRONMAN5_CLI" setup --variant max
```

Supported variant keys are `pironman5`, `max`, `mini`, `nas`, `pro-max`, and
`ups`.

## Common Commands

Check the install:

```bash
pironman5 doctor
sudo "$PIRONMAN5_CLI" doctor
```

Read or change settings:

```bash
pironman5 config get debug_level
sudo "$PIRONMAN5_CLI" config set debug_level INFO
```

After upgrading the pipx/uv command, refresh the service environment:

```bash
pipx reinstall pironman5
PIRONMAN5_CLI="$(command -v pironman5)"
sudo "$PIRONMAN5_CLI" service refresh
pironman5 doctor
```

## RGB Lights

Some Pironman 5 variants have a few internal RGB accent lights, not a full
display. This fork treats them as simple case lighting with a few useful modes:

- `ambient`: decorative profiles such as breathing blue, solid white, rainbow,
  and flow
- `status thermal`: whole-case color as a simple temperature signal
- `night`: an overlay that dims the current mode during configured hours
- `off`: disables the lights

```bash
pironman5 rgb list
sudo "$PIRONMAN5_CLI" rgb set ambient breathing-blue
sudo "$PIRONMAN5_CLI" rgb set status thermal
sudo "$PIRONMAN5_CLI" rgb night --brightness 10 --from 22:00 --to 07:00
sudo "$PIRONMAN5_CLI" rgb off
```

## Optional Hardware

Optional hardware is detected during setup. The PiPower5 UPS path still depends
on an unaudited upstream compatibility package, so it is only installed when you
ask for it:

```bash
sudo "$PIRONMAN5_CLI" setup --variant ups --with pipower5
```

Dashboard, graph history, and legacy hardware drivers are optional extras. The
default history backend is SQLite. InfluxDB is no longer installed by default.

To remove the dashboard package from the service install:

```bash
sudo "$PIRONMAN5_CLI" dashboard remove
```

To enable dashboard browser auto-start for the current desktop user:

```bash
pironman5 launch-browser --auto-start=on
```

## Service Administration

Rebuild the service install:

```bash
sudo "$PIRONMAN5_CLI" service refresh
```

Remove system integration while keeping runtime config:

```bash
sudo "$PIRONMAN5_CLI" service uninstall
```

Remove system integration, `/opt/pironman5`, and logs:

```bash
sudo "$PIRONMAN5_CLI" service uninstall --purge
```

The legacy `install.py` entry point now prints migration guidance by default.
Use it only if you explicitly need the old compatibility workflow:

```bash
git clone https://github.com/geoffbelknap/pironman5.git
cd pironman5
sudo python3 install.py --legacy-installer
```

## Troubleshooting

If setup fails with `sudo: pironman5: command not found`, rerun it with the
absolute pipx command path:

```bash
PIRONMAN5_CLI="$(command -v pironman5)"
sudo "$PIRONMAN5_CLI" setup
```

If the service is not active after setup or refresh:

```bash
sudo "$PIRONMAN5_CLI" doctor
sudo systemctl status pironman5.service --no-pager
sudo journalctl -u pironman5.service -n 80 --no-pager
```

If `pironman5 doctor` reports `protected`, run it with sudo. Some service-owned
files are intentionally not readable by the login user:

```bash
sudo "$PIRONMAN5_CLI" doctor
```

If the user-facing command and the systemd service disagree after an upgrade,
refresh the service environment:

```bash
pipx reinstall pironman5
PIRONMAN5_CLI="$(command -v pironman5)"
sudo "$PIRONMAN5_CLI" service refresh
sudo "$PIRONMAN5_CLI" doctor
```

## Compatibility

This fork is validated on Raspberry Pi OS Bookworm 64-bit with a Raspberry Pi 5
and Pironman 5 Max hardware. Upstream lists broader OS compatibility; treat that
as unverified for this fork until it passes the setup and doctor flow.

Known-good release validation:

| System | Hardware | Status |
| :--- | :--- | :--- |
| Raspberry Pi OS Bookworm 64-bit | Raspberry Pi 5 + Pironman 5 Max | Validated |

## Development

Clone the dependency you want to debug or edit. Treat SunFounder dependencies
as unreviewed until pinned to an audited fork or exact commit.

```bash
git clone https://github.com/geoffbelknap/pironman5.git
git clone https://github.com/geoffbelknap/pm_dashboard.git
git clone https://github.com/geoffbelknap/pm_auto.git  # legacy UPS only
```

Make adjustments, then install from local folders. Avoid floating Git installs
in hardened deployments.

```bash
sudo /opt/pironman5-venv/bin/pip uninstall pironman5 -y
sudo /opt/pironman5-venv/bin/pip install "$HOME/pironman5[legacy-ups]" --no-build-isolation

sudo /opt/pironman5-venv/bin/pip uninstall pm_auto -y
sudo /opt/pironman5-venv/bin/pip install ~/pm_auto --no-build-isolation
```

## Release Checklist

Before tagging a release from this fork:

```bash
python3 -m pytest
python3 -m build
PIRONMAN5_CLI="$(command -v pironman5)"
pironman5 setup --variant max --dry-run
sudo "$PIRONMAN5_CLI" service refresh
sudo "$PIRONMAN5_CLI" doctor
sudo systemctl status pironman5.service --no-pager
```
