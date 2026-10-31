"""Import des SugarWOD-CSV-Exports (App → More → Tools & Resources → Export Workouts).

Erwartete Spalten (Groß/Kleinschreibung egal, fehlende Spalten sind erlaubt):
date, title, description, best_result_raw, best_result_display, score_type,
barbell_lift, set_details, notes, rx_or_scaled, pr
"""
import csv
import hashlib
import io
import json
import re
from datetime import datetime

import db
import movements
from config import LBS_PER_KG, OPTIONS

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%d.%m.%Y", "%m/%d/%y", "%Y/%m/%d")

COLUMN_ALIASES = {
    "date": ["date", "datum"],
    "title": ["title", "workout", "name"],
    "description": ["description", "beschreibung"],
    "best_raw": ["best_result_raw", "result_raw", "score_raw"],
    "best_display": ["best_result_display", "result", "score", "best_result"],
    "score_type": ["score_type", "type"],
    "lift": ["barbell_lift", "lift", "movement"],
    "set_details": ["set_details", "sets"],
    "notes": ["notes", "notizen"],
    "rx": ["rx_or_scaled", "rx", "scaled"],
    "pr": ["pr", "is_pr"],
}


class ImportError_(Exception):
    pass


def parse_date(text):
    text = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    # z. B. "2024-03-05T00:00:00Z"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    return None


def parse_rep_scheme(text):
    """Wiederholungen pro Satz aus Titel/Beschreibung, z. B. '5-5-3-3-1', '5x5', '3RM'."""
    t = (text or "").lower().replace("×", "x")
    m = re.search(r"(?<![\d.])(\d{1,2}(?:\s*-\s*\d{1,2}){1,15})(?![\d.]|\s*(?:min|sec|m\b|cal|kg|lb))", t)
    if m:
        reps = [int(x) for x in re.split(r"\s*-\s*", m.group(1))]
        if all(0 < r <= 30 for r in reps):
            return reps
    m = re.search(r"(?<![\d.])(\d{1,2})\s*x\s*(\d{1,2})(?![\d.])", t)
    if m:
        sets, reps = int(m.group(1)), int(m.group(2))
        if 0 < reps <= 30 and 0 < sets <= 20:
            return [reps] * sets
    m = re.search(r"(\d{1,2})\s*sets?\s*(?:of|x)\s*(\d{1,2})", t)
    if m:
        return [int(m.group(2))] * int(m.group(1))
    m = re.search(r"(?<![\d.])(\d{1,2})\s*-?\s*rm\b", t)
    if m:
        return [int(m.group(1))]
    for word, n in (("single", 1), ("double", 2), ("triple", 3)):
        if re.search(r"\bheavy\s+" + word, t) or re.search(r"\bbuild\w*\s+to\s+a\s+(heavy\s+)?" + word, t):
            return [n]
    return None


def _to_kg(value):
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if OPTIONS["export_unit"] == "lbs":
        v = v / LBS_PER_KG
    return round(v, 2)


def parse_sets(raw_sets, scheme, best_raw, score_type):
    """Liste von dicts {load_kg, reps, reps_assumed, success}."""
    entries = []
    details = None
    if raw_sets:
        try:
            details = json.loads(raw_sets)
        except ValueError:
            details = None
    if isinstance(details, dict):
        details = details.get("sets") or [details]
    if isinstance(details, list):
        for i, d in enumerate(details):
            if not isinstance(d, dict):
                continue
            load = _to_kg(d.get("load") or d.get("weight"))
            if load is None:
                continue
            reps = d.get("reps")
            assumed = 0
            try:
                reps = int(reps) if reps not in (None, "") else None
            except (TypeError, ValueError):
                reps = None
            if not reps:
                if scheme:
                    reps = scheme[i] if i < len(scheme) else scheme[-1]
                else:
                    reps, assumed = 1, 1
            success = d.get("success", True)
            success = 0 if success in (False, "false", "False", 0, "0") else 1
            entries.append({"load_kg": load, "reps": reps, "reps_assumed": assumed, "success": success})
    if not entries and (score_type or "").lower() in ("load", "weight", ""):
        load = _to_kg(best_raw)
        if load:
            if scheme:
                reps, assumed = max(scheme) if len(set(scheme)) == 1 else min(scheme), 0
            else:
                reps, assumed = 1, 1
            entries.append({"load_kg": load, "reps": reps, "reps_assumed": assumed, "success": 1})
    return entries


def _column_map(fieldnames):
    lower = {f.strip().lower(): f for f in fieldnames if f}
    cmap = {}
    for key, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in lower:
                cmap[key] = lower[a]
                break
    return cmap


def import_csv(content, filename="upload.csv"):
    """Importiert CSV-Text. Doppelte Einträge werden übersprungen."""
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig", errors="replace")
    sample = content[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    if not reader.fieldnames:
        raise ImportError_("Die Datei ist leer.")
    cmap = _column_map(reader.fieldnames)
    if "date" not in cmap:
        raise ImportError_("Keine Spalte 'date' gefunden – ist das ein SugarWOD-Export?")

    def col(row, key):
        name = cmap.get(key)
        return (row.get(name) or "").strip() if name else ""

    total, new, skipped = 0, 0, 0
    with db.transaction() as con:
        cur = con.execute(
            "INSERT INTO imports(filename, at, rows, new_rows, export_unit) VALUES (?, ?, 0, 0, ?)",
            (filename, datetime.now().isoformat(timespec="seconds"), OPTIONS["export_unit"]),
        )
        import_id = cur.lastrowid
        for row in reader:
            total += 1
            date = parse_date(col(row, "date"))
            if not date:
                skipped += 1
                continue
            title = col(row, "title")
            desc = col(row, "description")
            lift_raw = col(row, "lift")
            lift = movements.canonical_lift(lift_raw) or (
                movements.detect_lift_in_text(title) if not lift_raw and (col(row, "score_type").lower() == "load") else None
            )
            if lift_raw and not lift:
                lift = lift_raw  # unbekannte Übung trotzdem behalten
            score_type = col(row, "score_type")
            h = hashlib.sha1("|".join([
                date, title, desc, lift_raw, col(row, "best_raw"), col(row, "set_details"),
            ]).encode()).hexdigest()
            if con.execute("SELECT 1 FROM workouts WHERE hash = ?", (h,)).fetchone():
                continue
            if lift:
                cats = [movements.lift_category(lift)] if movements.lift_category(lift) else []
            else:
                cats = movements.metcon_categories(title, desc)
            pr = col(row, "pr").lower() in ("true", "1", "yes", "pr", "x")
            cur = con.execute(
                """INSERT INTO workouts(hash, date, title, description, score_type, lift, lift_raw,
                   categories, best_raw, best_display, rx, pr, notes, import_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (h, date, title, desc, score_type, lift, lift_raw, ",".join(cats),
                 col(row, "best_raw"), col(row, "best_display"), col(row, "rx"),
                 1 if pr else 0, col(row, "notes"), import_id),
            )
            wid = cur.lastrowid
            if lift:
                scheme = parse_rep_scheme(f"{title} {desc}")
                for i, s in enumerate(parse_sets(col(row, "set_details"), scheme, col(row, "best_raw"), score_type)):
                    con.execute(
                        "INSERT INTO sets(workout_id, idx, load_kg, reps, reps_assumed, success) VALUES (?,?,?,?,?,?)",
                        (wid, i, s["load_kg"], s["reps"], s["reps_assumed"], s["success"]),
                    )
            new += 1
        con.execute("UPDATE imports SET rows = ?, new_rows = ? WHERE id = ?", (total, new, import_id))
    return {"datei": filename, "zeilen": total, "neu": new, "uebersprungen": skipped,
            "doppelt": total - new - skipped}
