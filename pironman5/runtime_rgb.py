import asyncio
import logging
import time
from datetime import datetime
from math import cos, pi
from os import path


RGB_STYLES = ["solid", "breathing", "flow", "flow_reverse", "rainbow", "rainbow_reverse", "hue_cycle"]
RGB_MODES = ["ambient", "status", "off"]
RGB_AMBIENT_PROFILES = {
    "breathing-blue": {
        "rgb_color": "0a1aff",
        "rgb_style": "breathing",
        "rgb_brightness": 40,
        "rgb_speed": 50,
    },
    "solid-white": {
        "rgb_color": "ffffff",
        "rgb_style": "solid",
        "rgb_brightness": 35,
        "rgb_speed": 50,
    },
    "rainbow": {
        "rgb_style": "rainbow",
        "rgb_brightness": 35,
        "rgb_speed": 50,
    },
    "flow": {
        "rgb_color": "0a1aff",
        "rgb_style": "flow",
        "rgb_brightness": 40,
        "rgb_speed": 50,
    },
}
RGB_STATUS_PROFILES = ["thermal"]


def map_value(value, from_low, from_high, to_low, to_high):
    return (value - from_low) * (to_high - to_low) / (from_high - from_low) + to_low


class WS2812Strip:
    def __init__(self, led_count):
        if not path.exists("/dev/spidev0.0"):
            raise RuntimeError("SPI not enabled")
        import board
        import neopixel_spi as neopixel

        spi = board.SPI()
        self.strip = neopixel.NeoPixel_SPI(
            spi,
            led_count,
            pixel_order=neopixel.GRB,
            auto_write=False,
        )
        time.sleep(0.01)
        self.fill(0)
        self.show()

    def fill(self, color):
        self.strip.fill(color)

    def show(self):
        self.strip.show()

    def __setitem__(self, index, value):
        self.strip[index] = value


class WS2812Module:
    def __init__(self, config, event, log=None, strip_factory=None, now_fn=None):
        self.config = dict(config or {})
        self.event = event
        self.log = log or logging.getLogger(__name__)
        self.strip_factory = strip_factory or WS2812Strip
        self.now_fn = now_fn or (lambda: datetime.now().time())
        self.task = None
        self.strip = None
        self.counter = 0
        self.counter_max = 100
        self.position = []
        self.led_count = 4
        self.enable = True
        self.color = (0, 255, 255)
        self.brightness = 100
        self.style = "breathing"
        self.speed = 50
        self.mode = "ambient"
        self.profile = "breathing-blue"
        self.night_brightness = None
        self.night_start = None
        self.night_end = None
        self.latest_data = {}
        self.event.subscribe("data_changed", self._handle_data_changed)
        self.update_config(
            {
                "rgb_led_count": self.config.get("rgb_led_count", 4),
                "rgb_enable": self.config.get("rgb_enable", True),
                "rgb_color": self.config.get("rgb_color", "#00ffff"),
                "rgb_brightness": self.config.get("rgb_brightness", 100),
                "rgb_style": self.config.get("rgb_style", "breathing"),
                "rgb_speed": self.config.get("rgb_speed", 50),
                "rgb_position": self.config.get("rgb_position", []),
                "rgb_mode": self.config.get("rgb_mode", "ambient"),
                "rgb_profile": self.config.get("rgb_profile", "breathing-blue"),
                "rgb_night_brightness": self.config.get("rgb_night_brightness"),
                "rgb_night_start": self.config.get("rgb_night_start"),
                "rgb_night_end": self.config.get("rgb_night_end"),
            }
        )
        self._init_strip()

    def update_config(self, config):
        patch = {}
        if "rgb_led_count" in config:
            led_count = config["rgb_led_count"]
            if isinstance(led_count, int):
                minimum = self.config.get("rgb_led_count_min")
                if minimum is not None and led_count < minimum:
                    led_count = minimum
                    self.log.warning(f"rgb_led_count {led_count} too small, available led count: >= {minimum}")
                self.led_count = led_count
                self.config["rgb_led_count"] = led_count
                if not self.position:
                    self.position = list(range(self.led_count))
                patch["rgb_led_count"] = led_count
            else:
                self.log.error(f"Invalid rgb_led_count: {led_count}")
        if "rgb_enable" in config:
            enable = config["rgb_enable"]
            if isinstance(enable, bool):
                self.enable = enable
                self.config["rgb_enable"] = enable
                patch["rgb_enable"] = enable
            else:
                self.log.error(f"Invalid rgb_enable: {enable}")
        if "rgb_color" in config:
            color = config["rgb_color"]
            if isinstance(color, str):
                try:
                    self.color = self.hex_to_rgb(color)
                    self.config["rgb_color"] = color
                    patch["rgb_color"] = color
                except ValueError:
                    self.log.error(f"Invalid rgb_color: {color}")
            else:
                self.log.error(f"Invalid rgb_color: {color}")
        if "rgb_brightness" in config:
            brightness = config["rgb_brightness"]
            if isinstance(brightness, int):
                self.brightness = brightness
                self.config["rgb_brightness"] = brightness
                patch["rgb_brightness"] = brightness
            else:
                self.log.error(f"Invalid rgb_brightness: {brightness}")
        if "rgb_speed" in config:
            speed = config["rgb_speed"]
            if isinstance(speed, int):
                self.speed = speed
                self.config["rgb_speed"] = speed
                patch["rgb_speed"] = speed
            else:
                self.log.error(f"Invalid rgb_speed: {speed}")
        if "rgb_style" in config:
            style = config["rgb_style"]
            if isinstance(style, str) and style in RGB_STYLES:
                self.style = style
                self.config["rgb_style"] = style
                patch["rgb_style"] = style
            else:
                self.log.error(f"Invalid rgb_style: {style}")
        if "rgb_position" in config:
            position = config["rgb_position"]
            if isinstance(position, list):
                self.position = list(position)
                if len(position) != self.led_count:
                    self.position += [i for i in range(self.led_count) if i not in self.position]
                self.config["rgb_position"] = self.position
                patch["rgb_position"] = self.position
            else:
                self.log.error(f"Invalid rgb_position: {position}")
        if "rgb_mode" in config:
            mode = config["rgb_mode"]
            if mode in RGB_MODES:
                self.mode = mode
                self.config["rgb_mode"] = mode
                patch["rgb_mode"] = mode
            else:
                self.log.error(f"Invalid rgb_mode: {mode}")
        if "rgb_profile" in config:
            profile = config["rgb_profile"]
            if isinstance(profile, str):
                self.profile = profile
                self.config["rgb_profile"] = profile
                patch["rgb_profile"] = profile
            else:
                self.log.error(f"Invalid rgb_profile: {profile}")
        if "rgb_night_brightness" in config:
            brightness = config["rgb_night_brightness"]
            if brightness is None or isinstance(brightness, int):
                self.night_brightness = brightness
                self.config["rgb_night_brightness"] = brightness
                patch["rgb_night_brightness"] = brightness
            else:
                self.log.error(f"Invalid rgb_night_brightness: {brightness}")
        if "rgb_night_start" in config:
            start = config["rgb_night_start"]
            if start is None or self._parse_hhmm(start) is not None:
                self.night_start = start
                self.config["rgb_night_start"] = start
                patch["rgb_night_start"] = start
            else:
                self.log.error(f"Invalid rgb_night_start: {start}")
        if "rgb_night_end" in config:
            end = config["rgb_night_end"]
            if end is None or self._parse_hhmm(end) is not None:
                self.night_end = end
                self.config["rgb_night_end"] = end
                patch["rgb_night_end"] = end
            else:
                self.log.error(f"Invalid rgb_night_end: {end}")
        return patch

    def render_once(self):
        if self.strip is None:
            return 1
        if not self.enable or self.mode == "off":
            self.clear()
            self.strip.show()
            return 1
        if self.mode == "status" and self.profile == "thermal":
            return self.thermal_status()
        style_func = getattr(self, self.style)
        delay = style_func()
        self.counter += 1
        if self.counter >= self.counter_max:
            self.counter = 0
        return delay

    def clear(self):
        if self.strip is not None:
            self.strip.fill(0)

    async def start(self):
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        self.clear()
        if self.strip is not None:
            self.strip.show()

    async def _run(self):
        while True:
            try:
                delay = self.render_once()
            except Exception:
                self.log.exception("WS2812 service error")
                delay = 5
            await asyncio.sleep(delay)

    def solid(self):
        self.strip.fill(self._brightness_color(self.color))
        self.strip.show()
        return 1

    def thermal_status(self):
        temperature = self.latest_data.get("cpu_temperature")
        if temperature is None:
            color = (10, 26, 255)
        elif temperature >= 70:
            color = (255, 0, 0)
        elif temperature >= 55:
            color = (255, 120, 0)
        else:
            color = (10, 26, 255)
        self.strip.fill(self._brightness_color(color))
        self.strip.show()
        return 1

    def breathing(self):
        self.counter_max = 200
        if self.counter >= self.counter_max:
            self.counter = 0
        delay = map_value(self.speed, 0, 100, 0.1, 0.001)
        color = self._brightness_color(self.color)
        level = self.counter if self.counter < 100 else 200 - self.counter
        self.strip.fill(tuple(int(x * level * 0.01) for x in color))
        self.strip.show()
        return delay

    def flow(self, reverse=False):
        self.counter_max = self.led_count
        if self.counter >= self.counter_max:
            self.counter = 0
        delay = map_value(self.speed, 0, 100, 0.5, 0.1)
        order = list(self.position)
        if reverse:
            order.reverse()
        self.strip.fill(0)
        self.strip[order[self.counter]] = self._brightness_color(self.color)
        self.strip.show()
        return delay

    def flow_reverse(self):
        return self.flow(reverse=True)

    def rainbow(self, reverse=False):
        self.counter_max = 360
        if self.counter >= self.counter_max:
            self.counter = 0
        delay = map_value(self.speed, 0, 100, 0.1, 0.005)
        pattern = self.create_rainbow_pattern(self.led_count, self.counter)
        order = list(self.position)
        if reverse:
            order.reverse()
        for i, led in enumerate(order):
            self.strip[led] = self.hsl_to_rgb(pattern[i], 1, self._active_brightness() * 0.01)
        self.strip.show()
        return delay

    def rainbow_reverse(self):
        return self.rainbow(reverse=True)

    def hue_cycle(self):
        self.counter_max = 360
        if self.counter >= self.counter_max:
            self.counter = 0
        delay = map_value(self.speed, 0, 100, 0.1, 0.005)
        self.strip.fill(self.hsl_to_rgb(self.counter, 1, self._active_brightness() * 0.01))
        self.strip.show()
        return delay

    def create_rainbow_pattern(self, num, offset=0):
        return [(i * 360.0 / num) + offset for i in range(num)]

    def create_gradient_pattern(self, num, offset=0):
        pattern = []
        for i in range(num):
            x = i / num * 2 * pi - pi
            pattern.append(int(cos(x + offset) * 50 + 50))
        return pattern

    def hsl_to_rgb(self, hue, saturation=1, brightness=1):
        hue = hue % 360
        hi = int((hue / 60) % 6)
        f = hue / 60.0 - hi
        p = brightness * (1 - saturation)
        q = brightness * (1 - f * saturation)
        t = brightness * (1 - (1 - f) * saturation)
        values = {
            0: (brightness, t, p),
            1: (q, brightness, p),
            2: (p, brightness, t),
            3: (p, q, brightness),
            4: (t, p, brightness),
            5: (brightness, p, q),
        }[hi]
        return tuple(int(value * 255) for value in values)

    def hex_to_rgb(self, value):
        value = value.strip().replace("#", "")
        if len(value) != 6:
            raise ValueError("RGB color must be six hex characters")
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))

    def _brightness_color(self, color):
        return tuple(int(value * self._active_brightness() * 0.01) for value in color)

    def _active_brightness(self):
        if (
            self.night_brightness is not None
            and self.night_start is not None
            and self.night_end is not None
            and self._in_night_schedule()
        ):
            return self.night_brightness
        return self.brightness

    def _in_night_schedule(self):
        start = self._parse_hhmm(self.night_start)
        end = self._parse_hhmm(self.night_end)
        if start is None or end is None:
            return False
        now = self.now_fn()
        if start <= end:
            return start <= now < end
        return now >= start or now < end

    def _parse_hhmm(self, value):
        if not isinstance(value, str):
            return None
        try:
            return datetime.strptime(value, "%H:%M").time()
        except ValueError:
            return None

    def _handle_data_changed(self, data, **_kwargs):
        if isinstance(data, dict):
            self.latest_data.update(data)

    def _init_strip(self):
        try:
            self.strip = self.strip_factory(self.led_count)
        except Exception as exc:
            self.log.error(f"Failed to initialize WS2812 service: {exc}")
            self.strip = None
