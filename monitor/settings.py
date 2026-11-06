import json
import os
from pathlib import Path


def settings_path():
    return Path(os.environ.get("APPDATA", Path.home() / ".config")) / "HealthManaMonitor" / "settings.json"


def defaults():
    return {name: {"region": None, "color": color, "threshold": threshold, "enabled": True}
            for name, color, threshold in [("health", [220, 40, 40], 30), ("mana", [40, 80, 220], 20)]}


def validate(data):
    for name in ("health", "mana"):
        item = data[name]
        region = item["region"]
        if region is not None:
            if not isinstance(region, list) or len(region) != 4 or any(type(v) is not int for v in region):
                raise ValueError("Invalid region")
            if region[0] < 0 or region[1] < 0 or region[2] - region[0] < 2 or region[3] - region[1] < 2:
                raise ValueError("Invalid region dimensions")
        color = item["color"]
        if not isinstance(color, list) or len(color) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in color):
            raise ValueError("Invalid color")
        if type(item["threshold"]) not in (int, float) or not 0 <= item["threshold"] <= 100:
            raise ValueError("Threshold must be between 0 and 100")
        if type(item["enabled"]) is not bool:
            raise ValueError("Invalid alert setting")
    return data


def load(path=None):
    path = path or settings_path()
    if not path.exists():
        return defaults()
    return validate(json.loads(path.read_text(encoding="utf-8")))


def save(data, path=None):
    validate(data)
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(path)
