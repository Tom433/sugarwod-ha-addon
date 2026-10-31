"""Add-on-Optionen aus /data/options.json (oder Umgebung beim lokalen Test)."""
import json
import os

DEFAULTS = {
    "export_unit": "lbs",
    "display_unit": "kg",
    "plate_increment": 2.5,
    "formula": "mittel",
    "body_weight_kg": 0,
    "ha_sensors": True,
    "sensor_lifts": [
        "Back Squat", "Front Squat", "Deadlift", "Clean",
        "Snatch", "Clean & Jerk", "Strict Press",
    ],
    "watch_folder": "/share/sugarwod",
}

DATA_DIR = os.environ.get("DATA_DIR", "/data")
OPTIONS_FILE = os.environ.get("OPTIONS_FILE", os.path.join(DATA_DIR, "options.json"))
DB_PATH = os.path.join(DATA_DIR, "sugarwod.db")
PORT = int(os.environ.get("PORT", "8099"))

LBS_PER_KG = 2.20462262


def load_options():
    opts = dict(DEFAULTS)
    try:
        with open(OPTIONS_FILE, encoding="utf-8") as f:
            opts.update(json.load(f))
    except (OSError, ValueError):
        pass
    return opts


OPTIONS = load_options()


def to_display(kg):
    """kg -> Anzeigeeinheit."""
    if kg is None:
        return None
    if OPTIONS["display_unit"] == "lbs":
        return kg * LBS_PER_KG
    return kg


def from_display(value):
    if OPTIONS["display_unit"] == "lbs":
        return value / LBS_PER_KG
    return value


def unit():
    return OPTIONS["display_unit"]
