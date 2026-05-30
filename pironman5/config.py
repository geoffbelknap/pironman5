import json
import os
from dataclasses import dataclass

from .security import write_json_private


@dataclass(frozen=True)
class ConfigField:
    key: str
    description: str
    value_type: str
    reload: str = "live"
    allowed: tuple = ()


CONFIG_SCHEMA = {
    "database_retention_days": ConfigField(
        "database_retention_days",
        "Days of local history to keep.",
        "integer",
    ),
    "debug_level": ConfigField(
        "debug_level",
        "Service log verbosity.",
        "string",
        allowed=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
    ),
    "enable_history": ConfigField(
        "enable_history",
        "Enable local SQLite metric history.",
        "boolean",
    ),
    "temperature_unit": ConfigField(
        "temperature_unit",
        "Temperature display unit.",
        "string",
        allowed=("C", "F"),
    ),
    "gpio_fan_mode": ConfigField(
        "gpio_fan_mode",
        "Fan profile.",
        "integer",
        allowed=("0 off", "1 performance", "2 cool", "3 balanced", "4 quiet"),
    ),
    "gpio_fan_led": ConfigField(
        "gpio_fan_led",
        "Fan LED behavior.",
        "string",
        allowed=("follow", "on", "off"),
    ),
    "oled_enable": ConfigField("oled_enable", "Enable the OLED display.", "boolean"),
    "oled_pages": ConfigField("oled_pages", "OLED pages to cycle through.", "json list"),
    "oled_rotation": ConfigField("oled_rotation", "OLED screen rotation.", "integer", allowed=("0", "180")),
    "oled_sleep_timeout": ConfigField("oled_sleep_timeout", "Seconds before the OLED sleeps.", "integer"),
    "rgb_enable": ConfigField("rgb_enable", "Enable case RGB lights.", "boolean"),
    "rgb_brightness": ConfigField("rgb_brightness", "RGB brightness from 0 to 100.", "integer"),
    "rgb_color": ConfigField("rgb_color", "RGB color as a hex value.", "string"),
    "rgb_mode": ConfigField("rgb_mode", "RGB behavior mode.", "string", allowed=("ambient", "status", "off")),
    "rgb_profile": ConfigField("rgb_profile", "RGB mode profile.", "string"),
    "rgb_style": ConfigField(
        "rgb_style",
        "Legacy RGB animation style.",
        "string",
        allowed=("solid", "breathing", "rainbow", "rainbow_reverse", "flow", "flow_reverse", "hue_cycle"),
    ),
    "rgb_speed": ConfigField("rgb_speed", "RGB animation speed from 0 to 100.", "integer"),
    "rgb_night_brightness": ConfigField("rgb_night_brightness", "RGB brightness during night mode.", "integer"),
    "rgb_night_start": ConfigField("rgb_night_start", "Night mode start time in HH:MM.", "string"),
    "rgb_night_end": ConfigField("rgb_night_end", "Night mode end time in HH:MM.", "string"),
}


def config_field(key):
    return CONFIG_SCHEMA.get(key)


def iter_config_fields(defaults):
    keys = sorted(set(defaults) | set(CONFIG_SCHEMA))
    for key in keys:
        yield CONFIG_SCHEMA.get(key, ConfigField(key, "Undocumented config value.", type(defaults.get(key)).__name__))


def validate_config_document(config):
    if not isinstance(config, dict):
        raise ValueError("Config must be a JSON object")
    if "system" in config and not isinstance(config["system"], dict):
        raise ValueError("Config system must be an object")
    for key, value in config.items():
        if not isinstance(value, dict):
            raise ValueError(f"Config section {key} must be an object")


def load_config_file(config_path):
    if not os.path.exists(config_path):
        return {"system": {}}
    with open(config_path, "r", encoding="utf-8") as f:
        try:
            content = f.read()
            if content == "":
                return {"system": {}}
            config = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid config file: {config_path}") from exc
    validate_config_document(config)
    return config


def update_config_file(config, config_path):
    current = load_config_file(config_path)
    validate_config_document(config)
    for key in config:
        if key in current:
            current[key].update(config[key])
        else:
            current[key] = config[key]
    validate_config_document(current)
    write_json_private(config_path, current)
