"""Webserver (Ingress) und Hintergrundaufgaben."""
import logging
import os
import shutil
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from waitress import serve

import analysis
import db
import ha
import importer
from config import OPTIONS, PORT, to_display

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sugarwod")

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

KG_KEYS = {"current_kg", "all_time_kg", "top_kg", "e1rm_kg", "one_rm_kg", "weight_kg", "low_kg", "high_kg", "kg"}


def disp(obj):
    """Alle *_kg-Felder rekursiv in die Anzeigeeinheit umrechnen."""
    if isinstance(obj, dict):
        return {k: (round(to_display(v), 1) if k in KG_KEYS and isinstance(v, (int, float)) else disp(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [disp(x) for x in obj]
    return obj


def after_import():
    threading.Thread(target=ha.push_sensors, daemon=True).start()


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(STATIC, name)


@app.get("/api/status")
def status():
    counts = db.query("""SELECT COUNT(*) AS workouts, MIN(date) AS first, MAX(date) AS last,
                         COUNT(DISTINCT lift) AS lifts FROM workouts""")[0]
    imports = db.query("SELECT filename, at, rows, new_rows, export_unit FROM imports ORDER BY id DESC LIMIT 10")
    return jsonify({
        **counts,
        "imports": imports,
        "unit": OPTIONS["display_unit"],
        "export_unit": OPTIONS["export_unit"],
        "formula": OPTIONS["formula"],
        "plate_increment": OPTIONS["plate_increment"],
        "body_weight_kg": OPTIONS["body_weight_kg"],
        "watch_folder": OPTIONS["watch_folder"],
        "sensor_lifts": OPTIONS["sensor_lifts"],
        "ha_available": bool(os.environ.get("SUPERVISOR_TOKEN")),
    })


@app.post("/api/import")
def do_import():
    files = request.files.getlist("file")
    if not files:
        return jsonify({"ok": False, "fehler": "Keine Datei ausgewählt."}), 400
    results = []
    for f in files:
        try:
            results.append(importer.import_csv(f.read(), f.filename or "upload.csv"))
        except importer.ImportError_ as e:
            return jsonify({"ok": False, "fehler": f"{f.filename}: {e}"}), 400
    after_import()
    return jsonify({"ok": True, "ergebnisse": results})


@app.delete("/api/data")
def delete_data():
    db.wipe()
    return jsonify({"ok": True})


@app.get("/api/lifts")
def lifts():
    return jsonify(disp(analysis.all_lifts()))


@app.get("/api/history")
def history():
    lift = request.args.get("lift", "")
    return jsonify(disp({"lift": lift, "summary": analysis.lift_summary(lift),
                         "points": analysis.lift_history(lift)}))


@app.post("/api/suggest")
def suggest():
    p = request.get_json(force=True) or {}
    try:
        reps = int(p.get("reps") or 1)
        sets = int(p.get("sets") or 1)
        percent = float(p["percent"]) if p.get("percent") not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"ok": False, "fehler": "Ungültige Zahl."}), 400
    if p.get("mode") == "prozent" and not percent:
        return jsonify({"ok": False, "fehler": "Bitte einen Prozentwert angeben."}), 400
    res = analysis.suggest(p.get("lift", ""), max(reps, 1), max(sets, 1),
                           p.get("mode", "kraft"), p.get("intensity", "moderat"), percent)
    return jsonify(disp(res))


@app.get("/api/analysis")
def full_analysis():
    return jsonify(disp(analysis.full_analysis()))


@app.get("/api/workouts")
def workouts():
    limit = min(int(request.args.get("limit", 30)), 500)
    rows = db.query("""SELECT w.date, w.title, w.score_type, w.lift, w.best_display, w.rx, w.pr, w.categories,
                              (SELECT MAX(load_kg) FROM sets s WHERE s.workout_id = w.id AND s.success = 1) AS top_kg
                       FROM workouts w ORDER BY w.date DESC, w.id DESC LIMIT ?""", (limit,))
    for r in rows:
        # SugarWOD zeigt Gewichte in der Export-Einheit – hier in der Anzeigeeinheit
        if r["top_kg"]:
            r["best_display"] = f'{to_display(r["top_kg"]):.1f}'.replace(".", ",").removesuffix(",0") + f' {OPTIONS["display_unit"]}'
    return jsonify(rows)


@app.post("/api/sensors")
def sensors():
    return jsonify(ha.push_sensors())


# ---------------------------------------------------------------- Hintergrund

def watch_folder_loop():
    folder = OPTIONS.get("watch_folder")
    if not folder:
        return
    done_dir = os.path.join(folder, "importiert")
    while True:
        try:
            if os.path.isdir(folder):
                for name in sorted(os.listdir(folder)):
                    path = os.path.join(folder, name)
                    if not name.lower().endswith(".csv") or not os.path.isfile(path):
                        continue
                    target = done_dir
                    try:
                        with open(path, "rb") as f:
                            res = importer.import_csv(f.read(), name)
                        log.info("Ordner-Import %s: %s neu von %s", name, res["neu"], res["zeilen"])
                        after_import()
                    except importer.ImportError_ as e:
                        log.warning("Ordner-Import %s fehlgeschlagen: %s", name, e)
                        target = os.path.join(folder, "fehlerhaft")
                    os.makedirs(target, exist_ok=True)
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    shutil.move(path, os.path.join(target, f"{stamp}_{name}"))
        except Exception:  # noqa: BLE001 – Schleife darf nicht sterben
            log.exception("Fehler beim Ordner-Import")
        time.sleep(60)


def sensor_loop():
    # Über die API gesetzte Zustände verschwinden beim HA-Neustart – daher regelmäßig erneuern.
    while True:
        try:
            ha.push_sensors()
        except Exception:  # noqa: BLE001
            log.exception("Fehler beim Senden der Sensoren")
        time.sleep(1800)


def main():
    db.get()
    threading.Thread(target=watch_folder_loop, daemon=True).start()
    threading.Thread(target=sensor_loop, daemon=True).start()
    log.info("SugarWOD Coach läuft auf Port %s", PORT)
    serve(app, host="0.0.0.0", port=PORT, threads=4)


if __name__ == "__main__":
    main()
