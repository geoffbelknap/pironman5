import asyncio
import logging


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
