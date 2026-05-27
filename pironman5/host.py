import socket
import subprocess

import psutil

from ._constants import APP_NAME


def restart_service(service_name=f"{APP_NAME}.service"):
    """Restart the systemd service backing this application."""
    subprocess.run(("systemctl", "restart", service_name), check=False)


def get_disks():
    result = subprocess.run(
        ("lsblk", "-J", "-o", "NAME,TYPE,PATH"),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return []

    import json

    data = json.loads(result.stdout or "{}")
    disks = []
    for device in data.get("blockdevices", []):
        if device.get("type") != "disk":
            continue
        path = device.get("path")
        name = device.get("name", "")
        if path and not name.startswith(("loop", "ram")):
            disks.append(path)
    return disks


def get_ips():
    ips = {}
    for interface, addresses in psutil.net_if_addrs().items():
        values = []
        for address in addresses:
            if address.family in (socket.AF_INET, socket.AF_INET6):
                values.append(address.address)
        if values:
            ips[interface] = values
    return ips
