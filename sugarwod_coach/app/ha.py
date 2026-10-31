"""Sensoren über die Supervisor-API an Home Assistant melden."""
import logging
import os
import re
from datetime import date, timedelta

import requests

import analysis
import db
from config import OPTIONS, to_display

log = logging.getLogger("sugarwod.ha")

API = os.environ.get("HA_API", "http://supervisor/core/api")


def _slug(text):
    text = text.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _post(entity_id, state, attributes):
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return False
    r = requests.post(
        f"{API}/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"state": state, "attributes": attributes},
        timeout=10,
    )
    if r.status_code >= 300:
        log.warning("Sensor %s: HTTP %s %s", entity_id, r.status_code, r.text[:200])
        return False
    return True


def build_states(today=None):
    """Liste von (entity_id, state, attributes) – getrennt, damit man sie testen kann."""
    unit = OPTIONS["display_unit"]
    states = []
    summaries = {s["lift"]: s for s in analysis.all_lifts(today=today)}
    for lift in OPTIONS.get("sensor_lifts") or []:
        s = summaries.get(lift)
        if not s:
            continue
        states.append((f"sensor.sugarwod_{_slug(lift)}_1rm", round(to_display(s["current_kg"]), 1), {
            "friendly_name": f"SugarWOD {lift} 1RM",
            "unit_of_measurement": unit,
            "icon": "mdi:weight-lifter",
            "state_class": "measurement",
            "bestwert_gesamt": round(to_display(s["all_time_kg"]), 1),
            "zuletzt_trainiert": s["last_date"],
            "trend": s["trend"],
            "trend_prozent_90_tage": round(s["trend_pct"], 1) if s["trend_pct"] is not None else None,
            "geschaetzt": True,
        }))
    last = db.query("SELECT date, title FROM workouts ORDER BY date DESC, id DESC LIMIT 1")
    if last:
        today = today or date.today()
        n30 = db.query("SELECT COUNT(DISTINCT date) AS n FROM workouts WHERE date >= ?",
                       ((today - timedelta(days=30)).isoformat(),))[0]["n"]
        states.append(("sensor.sugarwod_letztes_training", last[0]["date"], {
            "friendly_name": "SugarWOD letztes Training",
            "device_class": "date",
            "icon": "mdi:calendar-check",
            "workout": last[0]["title"],
            "trainingstage_30_tage": n30,
        }))
        states.append(("sensor.sugarwod_trainingstage_30_tage", n30, {
            "friendly_name": "SugarWOD Trainingstage (30 Tage)",
            "unit_of_measurement": "Tage",
            "icon": "mdi:counter",
            "state_class": "measurement",
        }))
    return states


def push_sensors():
    if not OPTIONS.get("ha_sensors"):
        return {"gesendet": 0, "hinweis": "Sensoren sind in den Optionen ausgeschaltet."}
    if not os.environ.get("SUPERVISOR_TOKEN"):
        return {"gesendet": 0, "hinweis": "Kein SUPERVISOR_TOKEN – läuft nicht als Add-on."}
    sent = 0
    for entity_id, state, attrs in build_states():
        try:
            if _post(entity_id, state, attrs):
                sent += 1
        except requests.RequestException as e:
            log.warning("Sensor %s nicht gesendet: %s", entity_id, e)
    return {"gesendet": sent}
