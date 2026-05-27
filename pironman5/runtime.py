import asyncio
import logging
import threading
import time

from . import host

try:
    from pm_auto.addons import Addons
except ImportError:
    Addons = None


class TaskScheduler:
    def __init__(self):
        self.tasks = {}
        self._stop_event = asyncio.Event()

    async def run_once(self, func, delay=0):
        task_id = f"once-{len(self.tasks)}"

        async def _wrapper():
            await asyncio.sleep(delay)
            if not self._stop_event.is_set():
                func()
            self.tasks.pop(task_id, None)

        self.tasks[task_id] = asyncio.create_task(_wrapper())
        return task_id

    async def run_periodically(self, func, interval):
        task_id = f"periodic-{len(self.tasks)}"

        async def _wrapper():
            while not self._stop_event.is_set():
                func()
                await asyncio.sleep(interval)

        self.tasks[task_id] = asyncio.create_task(_wrapper())
        return task_id

    async def stop(self):
        self._stop_event.set()
        for task in self.tasks.values():
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()


class EventBus:
    def __init__(self, log=None):
        self.log = log or logging.getLogger(__name__)
        self.subscribers = {}

    def subscribe(self, event_name, callback):
        self.subscribers.setdefault(event_name, []).append(callback)

    def unsubscribe(self, event_name, callback):
        if event_name in self.subscribers:
            self.subscribers[event_name].remove(callback)

    def publish(self, event_name, *args, **kwargs):
        for callback in self.subscribers.get(event_name, []):
            callback(*args, **kwargs)

    def connect(self, pub_event_name, sub_event_name):
        def bridge(*args, **kwargs):
            self.publish(sub_event_name, *args, **kwargs)

        self.subscribe(pub_event_name, bridge)


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


class LegacyHardwareRuntime:
    def __init__(self, config, peripherals, device_info, event, log=None):
        self.log = log or logging.getLogger(__name__)
        self.event = event or EventBus(log=self.log)
        self.peripherals = [peripheral for peripheral in peripherals if peripheral != "system"]
        self.addons = None
        if self.peripherals:
            if Addons is None:
                raise RuntimeError("pm_auto is required for legacy hardware modules")
            self.addons = Addons(
                peripherals=self.peripherals,
                config=config,
                device_info=device_info,
                event=self.event,
                log=self.log,
            )

    def update_config(self, config):
        if self.addons is None:
            return {}
        return self.addons.update_config(config)

    def test_smtp(self):
        if self.addons is None:
            return None
        return self.addons.pipower5.test_smtp()

    async def start(self):
        if self.addons is None:
            return
        await self.addons.start()

    async def stop(self):
        if self.addons is None:
            return
        await self.addons.stop()


class PironmanRuntime:
    def __init__(self, config, peripherals, device_info, event_map, log=None):
        self.log = log or logging.getLogger(__name__)
        self.event = EventBus(log=self.log)
        self.data = {}
        self.loop = None
        self.thread = None
        self.system = SystemStatusModule(event=self.event, log=self.log)
        self.hardware = LegacyHardwareRuntime(
            config=config,
            peripherals=peripherals,
            device_info=device_info,
            event=self.event,
            log=self.log,
        )
        for pub_event_name, sub_event_name in (event_map or {}).items():
            self.event.connect(pub_event_name, sub_event_name)
        self.event.subscribe("data_changed", self.handle_data_changed)

    def handle_data_changed(self, data, delete_keys=None):
        for key in delete_keys or []:
            self.data.pop(key, None)
        self.data.update(data)

    def read(self):
        return self.data

    def update_config(self, config):
        return self.hardware.update_config(config)

    def test_smtp(self):
        return self.hardware.test_smtp()

    def start(self):
        def run_event_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._start())
            self.loop.run_forever()
            self.loop.run_until_complete(self._stop())
            self.loop.close()

        self.thread = threading.Thread(target=run_event_loop, daemon=True)
        self.thread.start()

    def stop(self):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread and self.thread.is_alive():
            self.thread.join()

    async def _start(self):
        await self.system.start()
        await self.hardware.start()

    async def _stop(self):
        await self.hardware.stop()
        await self.system.stop()
