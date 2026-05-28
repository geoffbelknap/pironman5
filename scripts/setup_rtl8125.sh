#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  setup_rtl8125.sh --write-efuse --confirm-mac-unset --tool-dir PATH

This script writes RTL8125 eFuse data and is not part of normal install.
Download and inspect the rtnicpg tool yourself, then pass its local directory
with --tool-dir. The directory must contain pgdrv.ko, Makefile, and the
rtnicpg-aarch64-linux-gnu executable.
EOF
}

write_efuse=false
confirm_mac_unset=false
tool_dir=""

while [ $# -gt 0 ]; do
  case "$1" in
    --write-efuse)
      write_efuse=true
      shift
      ;;
    --confirm-mac-unset)
      confirm_mac_unset=true
      shift
      ;;
    --tool-dir)
      if [ $# -lt 2 ]; then
        echo "--tool-dir requires a path" >&2
        exit 2
      fi
      tool_dir="$2"
      shift 2
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

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root" >&2
  exit 1
fi

if [ "$write_efuse" != true ] || [ "$confirm_mac_unset" != true ] || [ -z "$tool_dir" ]; then
  usage >&2
  exit 2
fi

if [ ! -d "$tool_dir" ]; then
  echo "Tool directory not found: $tool_dir" >&2
  exit 1
fi

tool_dir="$(cd "$tool_dir" && pwd)"
tool="$tool_dir/rtnicpg-aarch64-linux-gnu"
driver="$tool_dir/pgdrv.ko"

if [ ! -f "$tool_dir/Makefile" ] || [ ! -f "$driver" ] || [ ! -x "$tool" ]; then
  echo "Tool directory must contain Makefile, pgdrv.ko, and executable rtnicpg-aarch64-linux-gnu" >&2
  exit 1
fi

DRIVER_8125="r8169"

run() {
  echo "Do $*"
  "$@"
}

cleanup() {
  lsmod | grep -q "pgdrv" && rmmod pgdrv.ko 2>/dev/null || true
  modprobe "$DRIVER_8125" 2>/dev/null || true
}
trap cleanup EXIT

get_efuse_mac_address() {
  "$tool" /efuse /vMac | grep "MAC_Address" | awk -F 'MAC_Address=' '{print $2}'
}

is_mac_address_set() {
  local mac
  mac="$(get_efuse_mac_address)"
  [ "$mac" != "00 00 00 00 00 00" ]
}

write_mac_to_efuse() {
  local new_mac
  new_mac="$(dmesg | grep RTL8125B | grep -oE '[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}' | head -n 1 | tr -d ':')"
  if [ -z "$new_mac" ]; then
    echo "Could not find RTL8125B MAC address in dmesg" >&2
    exit 1
  fi
  run "$tool" /w /efuse /manchg
  run "$tool" /efuse /nodeid "$new_mac"
}

echo "Starting RTL8125 eFuse setup from local tool directory: $tool_dir"
run make -C "$tool_dir"
rmmod "$DRIVER_8125" 2>/dev/null || true
run insmod "$driver"

if is_mac_address_set; then
  echo "MAC address is already set. Skipping eFuse write."
else
  write_mac_to_efuse
fi

echo "Done"
