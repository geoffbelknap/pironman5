import json
import os

from .security import write_json_private


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
