#!/bin/bash
set -euo pipefail
trap 'echo "Error occurred. Exiting..." >&2; exit 1' ERR

usage() {
    cat <<'EOF'
Usage:
  setup_pipower5.sh --driver-zip PATH --sha256 SHA256
  setup_pipower5.sh --uninstall

This legacy helper installs the PiPower 5 kernel driver from a local driver
archive only. Download the archive yourself, inspect its source, and pass the
expected SHA256 explicitly.
EOF
}

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root" >&2
    exit 1
fi

driver_zip=""
expected_sha256=""
uninstall=false

while [ $# -gt 0 ]; do
    case "$1" in
        --driver-zip)
            if [ $# -lt 2 ]; then
                echo "--driver-zip requires a path" >&2
                exit 2
            fi
            driver_zip="$2"
            shift 2
            ;;
        --sha256)
            if [ $# -lt 2 ]; then
                echo "--sha256 requires a checksum" >&2
                exit 2
            fi
            expected_sha256="$2"
            shift 2
            ;;
        --uninstall)
            uninstall=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ "$uninstall" = true ]; then
    echo "Uninstalling PiPower 5 driver"
    rm -f "/lib/modules/$(uname -r)/kernel/drivers/misc/pipower5_driver.ko"
    rm -f /etc/modules-load.d/pipower5_driver.conf
    exit 0
fi

if [ -z "$driver_zip" ] || [ -z "$expected_sha256" ]; then
    usage >&2
    exit 2
fi

if [ ! -f "$driver_zip" ]; then
    echo "Driver archive not found: $driver_zip" >&2
    exit 1
fi

if ! command -v unzip >/dev/null 2>&1; then
    echo "unzip is required to extract the driver archive" >&2
    exit 1
fi

echo "$expected_sha256  $driver_zip" | sha256sum -c -

work_dir="$(mktemp -d)"
cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT

echo "Installing PiPower 5 driver from local archive"
unzip -q "$driver_zip" -d "$work_dir"
driver_dir="$work_dir/driver"
if [ ! -x "$driver_dir/install.sh" ]; then
    echo "Driver archive does not contain executable driver/install.sh" >&2
    exit 1
fi

(cd "$driver_dir" && bash install.sh)

if ! id -u pipower5 >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin pipower5
fi

install -d -m 0755 -o root -g root /etc/udev/rules.d
if [ ! -f /etc/udev/rules.d/99-pipower5.rules ]; then
    printf '%s\n' 'SUBSYSTEM=="pipower5", KERNEL=="pipower5", MODE="0660", GROUP="pipower5"' > /etc/udev/rules.d/99-pipower5.rules
fi
