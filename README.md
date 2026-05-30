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

This project started from SunFounder's Pironman 5 package. The goal is one
clean package that should work across the Pironman 5 family instead of making
users choose between separate branches or one-off install scripts.

What this fork focuses on:

- **Simplified install**: install with `pipx` or `uv`, then run one setup
  command.
- **Single package for Pironman 5 variants**: one CLI can detect and configure
  supported Pironman 5 cases.
- **Safer setup**: preview system changes with `--dry-run` before applying
  them.
- **More reliable service**: the background service runs from a dedicated
  system environment, not a user folder.
- **Easier upgrades**: update the CLI, then refresh the service with one
  command.
- **Less bloat**: optional dashboard, UPS, and bridge packages are not
  installed unless needed.
- **Safer dependencies**: risky or poorly reviewed optional packages are gated
  behind detection or explicit flags.
- **SQLite history**: local history works without installing InfluxDB.
- **Better diagnostics**: `doctor` checks service health, hardware detection,
  permissions, devices, and install drift.
- **Safer config writes**: changing settings with sudo should not break service
  access to config files.
- **Better RGB controls**: simple modes for ambient lighting, thermal status,
  night dimming, and off.
- **Clearer docs**: install, setup, common commands, troubleshooting, and
  hardware options are documented in one place.

Links:

- Fork repository: <https://github.com/geoffbelknap/pironman5>
- Latest stable release: <https://github.com/geoffbelknap/pironman5/releases/tag/v1.0.1>
- Upstream hardware documentation: <https://docs.sunfounder.com/projects/pironman5/en/latest/>

## Install

`pipx` is the primary install path. It installs the CLI without root. The
separate `setup` step applies the OS-level pieces the case needs: systemd,
udev/group access, device tree overlays, and the service virtual environment.

Use the absolute command path when running setup with `sudo`. Many systems reset
`sudo`'s `PATH`, so a bare command name may not find the pipx command. The
examples below use the default pipx/uv shim path; replace it with your real
absolute path if you configured a different tool location.

After setup completes, it creates `/usr/local/bin/pironman5`. At that point,
normal privileged commands can use `sudo pironman5 ...`.

```bash
sudo apt-get update
sudo apt-get install pipx -y
pipx ensurepath
pipx install git+https://github.com/geoffbelknap/pironman5.git@v1.0.1

pironman5 setup --dry-run
sudo ~/.local/bin/pironman5 setup
pironman5 doctor
```

To install a specific branch, tag, or commit, append the Git ref:

```bash
pipx install git+https://github.com/geoffbelknap/pironman5.git@v1.0.1
```

`uv` works too if you already use it:

```bash
uv tool install git+https://github.com/geoffbelknap/pironman5.git@v1.0.1

pironman5 setup --dry-run
sudo ~/.local/bin/pironman5 setup
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
sudo ~/.local/bin/pironman5 setup --variant max
```

Supported variant keys are `pironman5`, `max`, `mini`, `nas`, `pro-max`, and
`ups`.

## Common Commands

Check the install:

```bash
pironman5 status
pironman5 status --json
pironman5 doctor
sudo pironman5 doctor
```

Read or change settings:

```bash
pironman5 config list
pironman5 config list --json
pironman5 config explain debug_level
pironman5 config get debug_level
pironman5 config set debug_level INFO --dry-run
sudo pironman5 config set debug_level INFO
```

Config writes are validated before they replace the saved file. When a change
is saved successfully, the running service is signaled to reload the config
without a full restart.

Set the fan profile without remembering config integers:

```bash
pironman5 fan list
pironman5 fan status
pironman5 fan status --json
sudo pironman5 fan set balanced
```

Manage the OLED without editing JSON:

```bash
pironman5 oled status
pironman5 oled status --json
pironman5 oled pages list
sudo pironman5 oled pages set mix performance
sudo pironman5 oled sleep 60
sudo pironman5 oled off
```

After upgrading the pipx/uv command, refresh the service environment:

```bash
pipx reinstall pironman5
sudo pironman5 service refresh
pironman5 doctor
```

If `pironman5 status` reports install drift, `service repair` is the same
repair path with a clearer name:

```bash
sudo pironman5 service repair
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
sudo pironman5 rgb set ambient breathing-blue
sudo pironman5 rgb set status thermal
sudo pironman5 rgb night --brightness 10 --from 22:00 --to 07:00
sudo pironman5 rgb off
```

## Optional Hardware

Optional hardware is detected during setup. The PiPower5 UPS path still depends
on an unaudited upstream compatibility package, so it is only installed when you
ask for it:

```bash
sudo ~/.local/bin/pironman5 setup --variant ups --with pipower5
```

Dashboard, graph history, and optional bridge drivers are separate extras. The
default history backend is SQLite. InfluxDB is no longer installed by default.

To remove the dashboard package from the service install:

```bash
sudo pironman5 dashboard remove
```

To enable dashboard browser auto-start for the current desktop user:

```bash
pironman5 launch-browser --auto-start=on
```

## Service Administration

Rebuild the service install:

```bash
sudo pironman5 service refresh
```

Remove system integration while keeping runtime config:

```bash
sudo pironman5 service uninstall
```

Remove system integration, `/opt/pironman5`, and logs:

```bash
sudo pironman5 service uninstall --purge
```

## Troubleshooting

If setup fails with `sudo: pironman5: command not found`, rerun it with the
absolute pipx command path:

```bash
sudo ~/.local/bin/pironman5 setup
```

If the service is not active after setup or refresh:

```bash
sudo pironman5 doctor
pironman5 service logs
sudo systemctl status pironman5.service --no-pager
sudo journalctl -u pironman5.service -n 80 --no-pager
```

If `pironman5 doctor` reports `protected`, run it with sudo. Some service-owned
files are intentionally not readable by the login user:

```bash
sudo pironman5 doctor
```

If the user-facing command and the systemd service disagree after an upgrade,
refresh the service environment:

```bash
pipx reinstall pironman5
sudo pironman5 service refresh
sudo pironman5 doctor
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

Clone this repository and install it in editable mode for CLI and service
development. Optional bridge and dashboard packages are pinned in
`pyproject.toml`; update those pins deliberately instead of editing live
service environments by hand.

```bash
git clone https://github.com/geoffbelknap/pironman5.git
cd pironman5
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
```

After changing service code, refresh the system service install in
`/opt/pironman5-venv` from your current checkout:

```bash
python3 -m pytest
sudo ~/.local/bin/pironman5 service refresh
```

## Release Checklist

Before tagging a release from this fork:

```bash
python3 scripts/check_release_version.py --tag v<version>
python3 -m pytest
python3 -m build
pironman5 setup --variant max --dry-run
sudo pironman5 service refresh
sudo pironman5 doctor
sudo systemctl status pironman5.service --no-pager
```

For a stable release, also run:

```bash
python3 scripts/check_release_version.py --stable --tag v<version>
```
