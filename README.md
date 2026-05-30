# Pironman 5

Production-focused fork of the SunFounder Pironman 5 software for Raspberry Pi
5 cases. This fork keeps the public CLI small, installs the long-running service
into a root-owned system environment, and gates optional hardware packages on
detected or explicitly requested hardware.

Quick Links:

- [Pironman 5](#pironman-5)
  - [About This Fork](#about-this-fork)
  - [Links](#links)
  - [Installation](#installation)
  - [Hardware Detection](#hardware-detection)
  - [Alternate Tool Installer](#alternate-tool-installer)
  - [Service Management](#service-management)
  - [Auto launch dashboard on browser](#auto-launch-dashboard-on-browser)
  - [Troubleshooting](#troubleshooting)
  - [Release Checklist](#release-checklist)
  - [Compatible Systems](#compatible-systems)
  - [Development](#development)

## About This Fork

This project is based on SunFounder's Pironman 5 package, but the install and
service model has been reworked for this fork:

- install the user-facing CLI with `pipx` or `uv`, without root
- apply OS integration explicitly with `pironman5 setup`
- run systemd from `/opt/pironman5-venv`, not a user's home directory
- auto-detect Pironman 5 hardware when possible
- keep dashboard, UPS, and legacy hardware dependencies optional

## Links

- Fork repository: <https://github.com/geoffbelknap/pironman5>
- Latest stable release: <https://github.com/geoffbelknap/pironman5/releases/tag/v1.0.0>
- Upstream hardware documentation: <https://docs.sunfounder.com/projects/pironman5/en/latest/>

## Installation

`pipx` is the primary install path for this fork. It installs the user-facing
CLI without root, and `pironman5 setup` performs the small set of
privileged OS integration steps explicitly.

1. install the Python application without root with `pipx`
2. review the privileged system changes
3. run setup with `sudo`

System setup creates a root-owned service environment at `/opt/pironman5-venv`
for systemd. This avoids running the service out of a user's home directory.
Use the absolute command path when invoking setup with `sudo`; many systems
intentionally reset `sudo`'s `PATH`, so running setup through a bare command
name may not find the pipx-installed command.

```bash
sudo apt-get update
sudo apt-get install pipx -y
pipx ensurepath
pipx install git+https://github.com/geoffbelknap/pironman5.git@v1.0.0
PIRONMAN5_CLI="$(command -v pironman5)"
pironman5 setup --dry-run
sudo "$PIRONMAN5_CLI" setup
pironman5 doctor
```

To install a specific branch, tag, or commit, append the Git ref to the install
URL:

```bash
pipx install git+https://github.com/geoffbelknap/pironman5.git@v1.0.0
```

Optional hardware is detected during system setup. The PiPower5 UPS HAT still
depends on an unaudited upstream compatibility package, so its Python package is
installed only when explicitly requested:

```bash
sudo "$PIRONMAN5_CLI" setup --variant ups --with pipower5
```

## Hardware Detection

`pironman5 detect` reports the case variant inferred from HAT EEPROM data when
available. `pironman5 setup` defaults to `--variant auto`; use `--variant` only
when detection is unavailable or you intentionally want to override it.

```bash
pironman5 detect
pironman5 detect --json
pironman5 setup --variant max --dry-run
sudo "$PIRONMAN5_CLI" setup --variant max
```

Supported variant keys are `pironman5`, `max`, `mini`, `nas`, `pro-max`, and
`ups`.

## Alternate Tool Installer

`uv` is also supported for users who already have it installed:

```bash
uv tool install git+https://github.com/geoffbelknap/pironman5.git@v1.0.0
PIRONMAN5_CLI="$(command -v pironman5)"
pironman5 setup --dry-run
sudo "$PIRONMAN5_CLI" setup
pironman5 doctor
```

## Service Management

To rebuild the service install:

```bash
sudo "$PIRONMAN5_CLI" service refresh
```

After upgrading the user-facing command, refresh the service environment too:

```bash
pipx reinstall pironman5
PIRONMAN5_CLI="$(command -v pironman5)"
sudo "$PIRONMAN5_CLI" service refresh
pironman5 doctor
```

To remove system integration while keeping runtime config, use:

```bash
sudo "$PIRONMAN5_CLI" service uninstall
```

To also remove `/opt/pironman5` and logs, use:

```bash
sudo "$PIRONMAN5_CLI" service uninstall --purge
```

`pironman5 doctor` can be run without sudo for a quick check. Some service-owned
files are intentionally protected from the login user; if doctor reports
`protected`, run the same command with sudo for service install details:

```bash
sudo "$PIRONMAN5_CLI" doctor
```

The legacy `install.py` entry point now prints migration guidance by default.
Use it only if you explicitly need the old compatibility workflow:

```bash
git clone https://github.com/geoffbelknap/pironman5.git
cd pironman5
sudo python3 install.py --legacy-installer
```

Dashboard, graph history, and legacy hardware drivers are optional package
extras. `pironman5 setup` installs the legacy hardware extra into the
service environment only when the selected case profile needs it. The default
history backend is SQLite. The old InfluxDB path is no longer installed by
default.

To remove the dashboard package from the service install:

```bash
sudo "$PIRONMAN5_CLI" dashboard remove
```

Read or change settings through the config command:

```bash
pironman5 config get debug_level
sudo "$PIRONMAN5_CLI" config set debug_level INFO
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

If the user-facing pipx command and the systemd service disagree after an
upgrade, refresh the service environment:

```bash
pipx reinstall pironman5
PIRONMAN5_CLI="$(command -v pironman5)"
sudo "$PIRONMAN5_CLI" service refresh
sudo "$PIRONMAN5_CLI" doctor
```

## Auto launch dashboard on browser

```bash
pironman5 launch-browser --auto-start=on
```

You also want to change touchscreen mode to Multitouch instead of Mouse Emulation.

1. **Raspberry Pi Icon** >> **Preferences** >> **Control Centre**.
2. Select **Screen** tab.
3. Long press/right click on **DSI-2**, 
4. Select **Touchscreen** >> **Mode** >> **Multitouch**.

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

## Compatible Systems

This fork is validated on Raspberry Pi OS Bookworm 64-bit with a Raspberry Pi 5
and Pironman 5 Max hardware. The upstream project lists broader operating
system compatibility, but this fork should treat those as unverified until they
are tested through the setup/doctor flow.

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

Make adjustments, then manually install from local folders. Avoid floating Git
installs in hardened deployments.

```bash
# install from folder
sudo /opt/pironman5-venv/bin/pip uninstall pironman5 -y
sudo /opt/pironman5-venv/bin/pip install "$HOME/pironman5[legacy-ups]" --no-build-isolation

sudo /opt/pironman5-venv/bin/pip uninstall pm_auto -y
sudo /opt/pironman5-venv/bin/pip install ~/pm_auto --no-build-isolation
```


Start/stop the service for debug

```bash
sudo systemctl stop pironman5.service
sudo systemctl start pironman5.service
sudo systemctl restart pironman5.service
sudo -u pironman5 /opt/pironman5-venv/bin/python

journalctl -xefu pironman5.service
sudo systemctl restart pironman5.service && journalctl -xefu pironman5.service
```
