import json
import os
import tempfile


SECRET_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
)


def is_secret_key(key):
    lowered = str(key).lower()
    return any(marker in lowered for marker in SECRET_MARKERS)


def redact_secrets(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if is_secret_key(key):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def write_json_private(path, data, mode=0o600):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, mode=0o750, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory or None, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.write("\n")
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        os.chmod(path, mode)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
