#!/bin/bash
set -euo pipefail
trap 'echo "Error occurred. Exiting..." >&2; exit 1' ERR

# Check root privileges
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

# Check if argument exists before accessing \$1
if [ $# -ge 1 ] && [ "$1" == "--uninstall" ]; then
    echo "Uninstalling PiPower 5 driver"
    rm -rf /lib/modules/$(uname -r)/kernel/drivers/misc/pipower5_driver.ko
    rm -rf /etc/modules-load.d/pipower5_driver.conf
    rm -rf /opt/pipower5/
    exit 0
fi

DEBIAN_FRONTEND=noninteractive apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install curl unzip -y
DEBIAN_FRONTEND=noninteractive apt-get install linux-headers-$(uname -r) -y

download_and_verify() {
    local url="$1"
    local output="$2"
    local sha256="$3"

    curl -fsSLo "$output" "$url"
    echo "$sha256  $output" | sha256sum -c -
}

echo "Installing PiPower 5 driver"

rm -rf driver.zip driver/
download_and_verify \
    "https://github.com/sunfounder/pipower5/releases/download/1.2.1/driver.zip" \
    "driver.zip" \
    "0e346fb9fdeca94c5d2ca8f2388c494690576ef99b0aa1882f886a408db66d82"
unzip driver.zip
cd driver
bash install.sh
cd ..
rm -rf driver.zip driver/

echo "Setting up email templates"

download_and_verify \
    "https://github.com/sunfounder/pipower5/releases/download/1.2.1/email_templates.zip" \
    "email_templates.zip" \
    "7cc1bf3612c7bf4fcdf18846da9eeefc1043e16dd98a1262a1ac0afbfea1b868"
unzip email_templates.zip
if [ ! -d /opt/pipower5 ]; then
    mkdir /opt/pipower5
fi
if [ -d /opt/pipower5/email_templates ]; then
    rm -rf /opt/pipower5/email_templates
fi
mv email_templates/ /opt/pipower5/email_templates/
rm -rf email_templates.zip email_templates/

# create pipower5 user
if ! id -u pipower5 > /dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin pipower5
fi
#create udev rules
if [ ! -d /etc/udev/rules.d ]; then
    mkdir /etc/udev/rules.d
fi
if [ ! -f /etc/udev/rules.d/99-pipower5.rules ]; then
    echo 'SUBSYSTEM=="pipower5", KERNEL=="pipower5", MODE="0660", GROUP="pipower5"' > /etc/udev/rules.d/99-pipower5.rules
fi
