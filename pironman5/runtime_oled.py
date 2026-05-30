import asyncio
import logging
import time
from os import path


class SSD1306TextDisplay:
    WIDTH = 128
    HEIGHT = 64
    ADDRESS_1 = 0x3C
    ADDRESS_2 = 0x3D

    def __init__(self, rotation=0, bus=1):
        from PIL import Image, ImageDraw, ImageFont
        from smbus2 import SMBus

        if not path.exists(f"/dev/i2c-{bus}"):
            raise RuntimeError(f"I2C bus {bus} is not enabled")
        self.Image = Image
        self.ImageDraw = ImageDraw
        self.ImageFont = ImageFont
        self.SMBus = SMBus
        self.bus_number = bus
        self.address = self._detect_address()
        if self.address is None:
            raise RuntimeError("SSD1306 OLED was not detected on I2C")
        self.bus = SMBus(bus)
        self.rotation = rotation
        self.pages = self.HEIGHT // 8
        self.buffer = [0] * (self.WIDTH * self.pages)
        self.image = Image.new("1", (self.WIDTH, self.HEIGHT))
        self.draw = ImageDraw.Draw(self.image)
        self.font = ImageFont.load_default()
        self._initialize()
        self.clear()
        self.display()

    def _detect_address(self):
        for address in (self.ADDRESS_1, self.ADDRESS_2):
            try:
                with self.SMBus(self.bus_number) as bus:
                    bus.write_quick(address)
                return address
            except OSError:
                continue
        return None

    def _command(self, value):
        self.bus.write_byte_data(self.address, 0x00, value)

    def _data(self, values):
        for offset in range(0, len(values), 16):
            self.bus.write_i2c_block_data(self.address, 0x40, values[offset:offset + 16])

    def _initialize(self):
        for command in (
            0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14,
            0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1,
            0xDB, 0x40, 0xA4, 0xA6, 0xAF,
        ):
            self._command(command)

    def is_ready(self):
        return True

    def set_rotation(self, rotation):
        if rotation not in (0, 180):
            raise ValueError("OLED rotation must be 0 or 180")
        self.rotation = rotation

    def clear(self):
        self.draw.rectangle((0, 0, self.WIDTH, self.HEIGHT), outline=0, fill=0)
        self.buffer = [0] * (self.WIDTH * self.pages)

    def draw_text(self, text, x, y, fill=1, align="left", size=None):
        text = str(text)
        width = self.draw.textlength(text, font=self.font)
        if align == "center":
            x -= width / 2
        elif align == "right":
            x -= width
        self.draw.text((x, y), text, font=self.font, fill=fill)

    def display(self):
        image = self.image.rotate(self.rotation)
        pixels = image.load()
        index = 0
        for page in range(self.pages):
            for x in range(self.WIDTH):
                bits = 0
                for bit in range(8):
                    bits <<= 1
                    bits |= 0 if pixels[(x, page * 8 + 7 - bit)] == 0 else 1
                self.buffer[index] = bits
                index += 1
        self._command(0x21)
        self._command(0)
        self._command(self.WIDTH - 1)
        self._command(0x22)
        self._command(0)
        self._command(self.pages - 1)
        self._data(self.buffer)

    def off(self):
        self._command(0xAE)


class OLEDModule:
    MIN_SLEEP_TIMEOUT = 0
    MAX_SLEEP_TIMEOUT = 3600
    DEFAULT_PAGES = ["mix", "performance", "ips", "disk"]

    def __init__(self, config, peripherals, event, log=None, display_factory=None):
        self.config = dict(config or {})
        self.peripherals = list(peripherals or [])
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.display = (display_factory or SSD1306TextDisplay)(int(self.config.get("oled_rotation", 0)))
        self.available_pages = sorted(
            peripheral.removeprefix("oled_page_")
            for peripheral in self.peripherals
            if peripheral.startswith("oled_page_")
        )
        self.data = {}
        self.running = False
        self.task = None
        self.wake_flag = True
        self.wake_started_at = time.time()
        self.page_index = 0
        self.shutdown_reason = None
        self.enable = bool(self.config.get("oled_enable", True))
        self.rotation = int(self.config.get("oled_rotation", 0))
        self.sleep_timeout = self._clamp_sleep_timeout(self.config.get("oled_sleep_timeout", 10))
        self.oled_pages = self._valid_pages(self.config.get("oled_pages", self.DEFAULT_PAGES), init=True)
        self.event.subscribe("data_changed", self.handle_data_changed)
        self.event.subscribe("oled_wake_page_next", self.wake_page_next)
        self.event.subscribe("oled_page_prev", self.page_prev)
        self.event.subscribe("shutdown", self.show_shutdown_screen)
        self.event.subscribe("oled_show_shutdown_screen", self.show_shutdown_screen)

    def _clamp_sleep_timeout(self, value):
        return max(self.MIN_SLEEP_TIMEOUT, min(self.MAX_SLEEP_TIMEOUT, int(value)))

    def _valid_pages(self, pages, init=False):
        valid = []
        for page in pages:
            if page in valid:
                self.log.warning("Duplicate OLED page %s", page)
                continue
            if not init and self.available_pages and page not in self.available_pages:
                self.log.warning("Invalid OLED page %s, must be in %s", page, self.available_pages)
                continue
            valid.append(page)
        return valid

    def handle_data_changed(self, data, delete_keys=None):
        for key in delete_keys or []:
            self.data.pop(key, None)
        self.data.update(data)

    def update_config(self, config):
        patch = {}
        if "oled_enable" in config:
            self.enable = bool(config["oled_enable"])
            patch["oled_enable"] = self.enable
            if self.enable:
                self.wake()
            else:
                self.sleep()
        if "oled_rotation" in config:
            rotation = int(config["oled_rotation"])
            if rotation in (0, 180):
                self.rotation = rotation
                patch["oled_rotation"] = rotation
                self.display.set_rotation(rotation)
            else:
                self.log.error("Invalid OLED rotation value, must be 0 or 180")
        if "oled_sleep_timeout" in config:
            self.sleep_timeout = self._clamp_sleep_timeout(config["oled_sleep_timeout"])
            patch["oled_sleep_timeout"] = self.sleep_timeout
        if "temperature_unit" in config and config["temperature_unit"] in ("C", "F"):
            patch["temperature_unit"] = config["temperature_unit"]
        if "oled_pages" in config:
            self.oled_pages = self._valid_pages(config["oled_pages"])
            self.page_index = 0
            patch["oled_pages"] = self.oled_pages
            self.wake()
        self.config.update(patch)
        return patch

    def wake(self):
        self.wake_flag = True
        self.wake_started_at = time.time()

    def wake_page_next(self, *_args, **_kwargs):
        if not self.wake_flag:
            self.wake()
            return
        if self.oled_pages:
            self.page_index = (self.page_index + 1) % len(self.oled_pages)
        self.wake_started_at = time.time()

    def page_prev(self, *_args, **_kwargs):
        if self.wake_flag and self.oled_pages:
            self.page_index = (self.page_index - 1) % len(self.oled_pages)
            self.wake_started_at = time.time()

    def show_shutdown_screen(self, reason=None):
        self.shutdown_reason = reason or "shutdown"
        self.wake()

    def sleep(self):
        self.wake_flag = False
        self.display.clear()
        self.display.display()

    def _format_value(self, value, suffix=""):
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.1f}{suffix}"
        return f"{value}{suffix}"

    def _page_lines(self, page):
        if self.shutdown_reason:
            return ["Powering off", str(self.shutdown_reason)[:20]]
        if page == "performance":
            return [
                f"CPU {self._format_value(self.data.get('cpu_percent'), '%')}",
                f"T {self._format_value(self.data.get('cpu_temperature'), 'C')}",
                f"RAM {self._format_value(self.data.get('memory_percent'), '%')}",
            ]
        if page == "ips":
            ips = self.data.get("ips") or {}
            lines = ["IP addresses"]
            for name, values in list(ips.items())[:3]:
                lines.append(f"{name}: {', '.join(values)[:16]}")
            return lines
        if page == "disk":
            disks = self.data.get("disks") or {}
            lines = ["Disks"]
            for name, disk in list(disks.items())[:3]:
                percent = getattr(disk, "percent", None)
                lines.append(f"{name}: {self._format_value(percent, '%')}")
            return lines
        if page == "battery":
            return [
                f"Battery {self._format_value(self.data.get('battery_percentage'), '%')}",
                f"Source {self.data.get('power_source', '-')}",
            ]
        if page == "input":
            return [
                f"In {self._format_value(self.data.get('input_voltage'), 'V')}",
                f"{self._format_value(self.data.get('input_current'), 'A')}",
            ]
        if page == "rpi_power":
            return [
                f"Out {self._format_value(self.data.get('output_voltage'), 'V')}",
                f"{self._format_value(self.data.get('output_current'), 'A')}",
            ]
        return [
            f"CPU {self._format_value(self.data.get('cpu_percent'), '%')}",
            f"RAM {self._format_value(self.data.get('memory_percent'), '%')}",
            f"Net {self._format_value(self.data.get('network_download_speed'))}",
        ]

    def render_once(self):
        if not self.enable:
            self.sleep()
            return
        if self.sleep_timeout > 0 and time.time() - self.wake_started_at > self.sleep_timeout:
            self.sleep()
            return
        if not self.wake_flag:
            return
        pages = self.oled_pages or ["mix"]
        page = pages[self.page_index % len(pages)]
        self.display.clear()
        for index, line in enumerate(self._page_lines(page)[:5]):
            self.display.draw_text(line, 0, index * 12)
        self.display.display()

    async def _run(self):
        while self.running:
            self.render_once()
            await asyncio.sleep(1)

    async def start(self):
        self.running = True
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        self.running = False
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.display.clear()
        self.display.display()
        self.display.off()
