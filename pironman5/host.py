import socket
import subprocess
import time
from dataclasses import dataclass

import psutil

from ._constants import APP_NAME

_net_io_counter = None
_net_io_counter_time = None


@dataclass
class CPUFreq:
    current: float = 0.0
    min: float = 0.0
    max: float = 0.0


@dataclass
class DiskInfo:
    total: int = 0
    used: int = 0
    free: int = 0
    percent: float = 0.0
    type: str = "unknown"
    temperature: float = None
    path: str = None
    mounted: bool = False


@dataclass
class NetworkSpeed:
    upload: int = 0
    download: int = 0


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


def get_disk_info(mountpoint="/"):
    usage = psutil.disk_usage(mountpoint)
    return DiskInfo(
        total=usage.total,
        used=usage.used,
        free=usage.free,
        percent=usage.percent,
        path="total",
        mounted=True,
    )


def get_disks_info(disks=None, temperature=False):
    disks = disks or get_disks()
    partitions = psutil.disk_partitions(all=False)
    info = {}
    for disk in disks:
        name = disk.rsplit("/", 1)[-1]
        disk_info = DiskInfo(path=disk, type=_disk_type(disk), mounted=False)
        for partition in partitions:
            if not partition.device.startswith(disk):
                continue
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except OSError:
                continue
            disk_info = DiskInfo(
                total=usage.total,
                used=usage.used,
                free=usage.free,
                percent=usage.percent,
                type=_disk_type(disk),
                temperature=None,
                path=disk,
                mounted=True,
            )
            break
        info[name] = disk_info
    return info


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


def get_macs():
    macs = {}
    for interface, addresses in psutil.net_if_addrs().items():
        for address in addresses:
            if address.family == getattr(socket, "AF_PACKET", object()):
                macs[interface] = address.address
                break
    return macs


def get_network_connection_type():
    active = []
    stats = psutil.net_if_stats()
    for interface, stat in stats.items():
        if not stat.isup or interface == "lo":
            continue
        if interface.startswith(("wl", "wifi")):
            active.append("wifi")
        elif interface.startswith(("en", "eth")):
            active.append("ethernet")
        else:
            active.append(interface)
    return active


def get_network_speed():
    global _net_io_counter, _net_io_counter_time
    current = psutil.net_io_counters()
    current_time = time.time()
    if _net_io_counter is None or _net_io_counter_time is None:
        _net_io_counter = current
        _net_io_counter_time = current_time
        return NetworkSpeed()

    interval = current_time - _net_io_counter_time
    if interval <= 0:
        return NetworkSpeed()
    speed = NetworkSpeed(
        upload=round((current.bytes_sent - _net_io_counter.bytes_sent) / interval),
        download=round((current.bytes_recv - _net_io_counter.bytes_recv) / interval),
    )
    _net_io_counter = current
    _net_io_counter_time = current_time
    return speed


def get_cpu_temperature():
    try:
        return int(_read_text("/sys/class/thermal/thermal_zone0/temp")) / 1000
    except (OSError, ValueError):
        return None


def get_gpu_temperature():
    result = subprocess.run(
        ("vcgencmd", "measure_temp"),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.split("=", 1)[1].split("'", 1)[0])
    except (IndexError, ValueError):
        return None


def get_cpu_percent(percpu=False):
    return psutil.cpu_percent(percpu=percpu)


def get_cpu_freq():
    freq = psutil.cpu_freq()
    if freq is None:
        return CPUFreq()
    return CPUFreq(current=freq.current, min=freq.min, max=freq.max)


def get_cpu_count():
    return psutil.cpu_count()


def get_memory_info():
    return psutil.virtual_memory()


def get_boot_time():
    return psutil.boot_time()


def shutdown():
    subprocess.run(("systemctl", "poweroff", "-i"), check=False)


def reboot():
    subprocess.run(("systemctl", "reboot", "-i"), check=False)


def _disk_type(disk_path):
    name = disk_path.rsplit("/", 1)[-1]
    if name.startswith("nvme"):
        return "nvme"
    if name.startswith("mmcblk"):
        return "sd"
    if name.startswith("sd"):
        return "usb"
    return "unknown"


def _read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()
