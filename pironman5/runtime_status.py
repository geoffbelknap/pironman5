import logging
import time

from . import host
from .runtime_core import TaskScheduler


class SystemStatusModule:
    def __init__(self, event, log=None):
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.tasks = TaskScheduler()
        self.disk_keys = []
        self.event.subscribe("shutdown", self._on_shutdown)
        self.event.subscribe("reboot", self._on_reboot)
        self.event.subscribe("restart_service", self._on_restart_service)

    def task_once(self):
        data = {"cpu_count": int(host.get_cpu_count() or 0)}
        for name, mac in host.get_macs().items():
            data[f"mac_{name}"] = mac
        self.event.publish("data_changed", data)

    def task_1s(self):
        data = {"boot_time": float(host.get_boot_time() or 0)}
        cpu_temperature = host.get_cpu_temperature()
        gpu_temperature = host.get_gpu_temperature()
        data["cpu_temperature"] = float(cpu_temperature) if cpu_temperature is not None else None
        data["gpu_temperature"] = float(gpu_temperature) if gpu_temperature is not None else None
        data["cpu_percent"] = float(host.get_cpu_percent())
        for i, percent in enumerate(host.get_cpu_percent(percpu=True)):
            data[f"cpu_{i}_percent"] = float(percent)

        cpu_freq = host.get_cpu_freq()
        data["cpu_freq"] = float(cpu_freq.current)
        data["cpu_freq_min"] = float(cpu_freq.min)
        data["cpu_freq_max"] = float(cpu_freq.max)

        memory = host.get_memory_info()
        data["memory_total"] = int(memory.total)
        data["memory_available"] = int(memory.available)
        data["memory_percent"] = float(memory.percent)
        data["memory_used"] = int(memory.used)

        network_speed = host.get_network_speed()
        data["network_upload_speed"] = int(network_speed.upload)
        data["network_download_speed"] = int(network_speed.download)
        self.event.publish("data_changed", data)

    def task_3s(self):
        data = {}
        ips = host.get_ips()
        data["ips"] = ips
        for name, values in ips.items():
            data[f"ip_{name}"] = values
        data["network_type"] = "&".join(host.get_network_connection_type())
        self.event.publish("data_changed", data)

    def task_5s(self):
        data = {"disk_list": host.get_disks()}
        disks = host.get_disks_info(temperature=True)
        data["disks"] = disks
        for disk_name, disk in disks.items():
            data[f"disk_{disk_name}_mounted"] = int(disk.mounted)
            data[f"disk_{disk_name}_total"] = int(disk.total)
            data[f"disk_{disk_name}_used"] = int(disk.used)
            data[f"disk_{disk_name}_free"] = int(disk.free)
            data[f"disk_{disk_name}_percent"] = float(disk.percent)
            if disk.temperature is not None:
                data[f"disk_{disk_name}_temperature"] = float(disk.temperature)

        keys = list(data.keys())
        delete_keys = [key for key in self.disk_keys if key not in keys]
        self.disk_keys = keys
        self.event.publish("data_changed", data, delete_keys=delete_keys)

    async def start(self):
        await self.tasks.run_once(self.task_once, 1)
        await self.tasks.run_periodically(self.task_1s, 1)
        await self.tasks.run_periodically(self.task_3s, 3)
        await self.tasks.run_periodically(self.task_5s, 5)

    async def stop(self):
        await self.tasks.stop()

    def _on_shutdown(self, reason=None):
        self.log.info(f"Shutdown reason: {reason}")
        self.event.publish("before_shutdown", reason)
        time.sleep(2)
        host.shutdown()

    def _on_reboot(self, *_args):
        host.reboot()

    def _on_restart_service(self, *_args):
        host.restart_service()
