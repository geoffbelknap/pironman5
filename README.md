# Pironman 5

Pironman 5 case

Quick Links:

- [Pironman 5](#pironman-5)
  - [About Pironman5](#about-pironman5)
  - [Links](#links)
  - [Installation](#installation)
  - [Auto launch dashboard on browser](#auto-launch-dashboard-on-browser)
  - [Update](#update)
  - [Compatible Systems](#compatible-systems)
    - [Ubuntu 24.04 server eth0 and wifi not work](#ubuntu-2404-server-eth0-and-wifi-not-work)
    - [Debug](#debug)
  - [About SunFounder](#about-sunfounder)
  - [Contact us](#contact-us)

## About Pironman5

## Links

- SunFounder Online Store &emsp; <https://www.sunfounder.com/>
- Documentation &emsp; <https://docs.sunfounder.com/projects/pironman5/en/latest/>

## Installation

`pipx` is the primary install path for this fork. It installs the user-facing
CLI without root, and `pironman5 system setup` performs the small set of
privileged OS integration steps explicitly.

1. install the Python application without root with `pipx`
2. review the privileged system changes
3. run the system setup command with `sudo`

System setup creates a root-owned service environment at `/opt/pironman5-venv`
for systemd. This avoids running the service out of a user's home directory.

```bash
sudo apt-get update
sudo apt-get install pipx -y
pipx ensurepath
pipx install git+https://github.com/geoffbelknap/pironman5.git
pironman5 system plan
sudo pironman5 system setup
pironman5 system doctor
```

Optional hardware is detected during system setup. To force-enable the PiPower5
UPS HAT when it is not auto-detected, use:

```bash
sudo pironman5 system setup --variant ups --with pipower5
```

`uv` is also supported for users who already have it installed:

```bash
uv tool install git+https://github.com/geoffbelknap/pironman5.git
pironman5 system plan
sudo pironman5 system setup
pironman5 system doctor
```

To rebuild the service install:

```bash
sudo pironman5 system update
```

After upgrading the user-facing command, refresh the service environment too:

```bash
pipx reinstall pironman5
sudo pironman5 system update
pironman5 system doctor
```

To remove system integration while keeping runtime config, use:

```bash
sudo pironman5 system uninstall
```

To also remove `/opt/pironman5` and logs, use:

```bash
sudo pironman5 system uninstall --purge
```

The legacy `install.py` entry point now prints migration guidance by default.
Use it only if you explicitly need the old compatibility workflow:

```bash
git clone https://github.com/geoffbelknap/pironman5.git
cd pironman5
sudo python3 install.py --legacy-installer
```

Dashboard, graph history, and legacy hardware drivers are optional package
extras. `pironman5 system setup` installs the legacy hardware extra into the
service environment only when the selected case profile needs it. The default
history backend is SQLite. The old InfluxDB path is no longer installed by
default.

To remove the dashboard package from the service install:

```bash
sudo pironman5 dashboard remove
```

Read or change settings through the config command:

```bash
pironman5 config get debug_level
sudo pironman5 config set debug_level INFO
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

## Update

<https://github.com/sunfounder/pironman5/blob/main/CHANGELOG.md>

## Compatible Systems

Operate Systems that passed the test on the Raspberry Pi 5:

Operate System | Release Date | Compatible
:---   | :---: | :---: 
Raspberry Pi OS Desktop - bookworm (64 bit) | 2024-11-19 | &#x2705;
Raspberry Pi OS Desktop - bookworm (32 bit) | 2024-11-19 |  &#x2705;
Raspberry Pi OS Full - bookworm (64 bit) | 2024-11-19 |  &#x2705;
Raspberry Pi OS Full - bookworm (32 bit) | 2024-11-19 |  &#x2705;
Raspberry Pi OS lite - bookworm (64 bit) | 2024-11-19 |  &#x2705;
Raspberry Pi OS lite - bookworm (64 bit) | 2024-11-19 |  &#x2705;
Ubuntu Desktop 24.04.1 LTS (64 bit) | 2024-08-29 |  &#x2705;
Ubuntu Server 24.04.1 LTS (64 bit) | 2024-10-10 |  &#x2705;
Ubuntu Desktop 24.10 (64 bit) | 2024-10-10 |   &#x2705;
Ubuntu Server 24.10 (64 bit) | 2024-08-29 |   &#x2705;
Kali Linux | 2024-08-27 | &#x2705;
Home Assistant OS 14.0 | 2024-12-03 | &#x2705;
Homebridge bookworm (64 bit) | 2024-05-03 | &#x2705;
Homebridge bookworm (64 bit) | 2024-05-03 | &#x2705;
Batocera Linux | 2024-07-31 | &#x2705;

### Ubuntu 24.04 server eth0 and wifi not work

https://www.reddit.com/r/Ubuntu/comments/1d0s8v5/ubuntu_2404_server_on_my_raspberry_pi_5_and_eth0/


### Debug

Clone the dependency you want to debug or edit. Treat SunFounder dependencies
as unreviewed until pinned to an audited fork or exact commit.

```bash
git clone https://github.com/geoffbelknap/pironman5.git
git clone https://github.com/geoffbelknap/pm_dashboard.git
git clone https://github.com/geoffbelknap/pm_auto.git
```

Make adjustments, then manually install from local folders. Avoid floating Git
installs in hardened deployments.

```bash
# install from folder
sudo /opt/pironman5-venv/bin/pip uninstall pironman5 -y
sudo /opt/pironman5-venv/bin/pip install "$HOME/pironman5[legacy-hardware]" --no-build-isolation

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

## About SunFounder

SunFounder is a company focused on STEAM education with products like open source robots, development boards, STEAM kit, modules, tools and other smart devices distributed globally. In SunFounder, we strive to help elementary and middle school students as well as hobbyists, through STEAM education, strengthen their hands-on practices and problem-solving abilities. In this way, we hope to disseminate knowledge and provide skill training in a full-of-joy way, thus fostering your interest in programming and making, and exposing you to a fascinating world of science and engineering. To embrace the future of artificial intelligence, it is urgent and meaningful to learn abundant STEAM knowledge.

## Contact us

website:
    www.sunfounder.com

E-mail:
    service@sunfounder.com
