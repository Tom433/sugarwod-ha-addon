"""1RM-Schätzung, Gewichtsvorschläge, Verlauf und Stärken/Schwächen.

Alle Gewichte werden intern in kg gerechnet.
"""
import math
from collections import defaultdict
from datetime import date, timedelta

import db
import movements
from config import OPTIONS, from_display, to_display

MAX_REPS_FOR_ESTIMATE = 12  # darüber werden Formeln sehr ungenau
CURRENT_WINDOW_DAYS = 180
STALE_DAYS = 120

FORMULA_LABEL = {
    "epley": "Epley: 1RM = Gewicht × (1 + Wdh/30)",
    "brzycki": "Brzycki: 1RM = Gewicht × 36 / (37 − Wdh)",
    "mittel": "Mittelwert aus Epley und Brzycki",
}


# ---------------------------------------------------------------- Formeln

def e1rm(weight, reps, formula=None):
    formula = formula or OPTIONS["formula"]
    if not weight or not reps or reps < 1:
        return None
    if reps == 1:
        return weight
    r = min(reps, MAX_REPS_FOR_ESTIMATE)
    ep = weight * (1 + r / 30)
    br = weight * 36 / (37 - r)
    return {"epley": ep, "brzycki": br}.get(formula, (ep + br) / 2)


def weight_for_reps(one_rm, reps, formula=None):
    """Umkehrung: Gewicht, das man bei 1RM für `reps` Wdh. bis zum Versagen schafft."""
    formula = formula or OPTIONS["formula"]
    if reps <= 1:
        return one_rm
    r = min(reps, 30)
    ep = one_rm / (1 + r / 30)
    br = one_rm * (37 - min(r, 36)) / 36
    return {"epley": ep, "brzycki": br}.get(formula, (ep + br) / 2)


def de(x, digits=1):
    """Zahl mit deutschem Dezimalkomma."""
    return f"{x:.{digits}f}".replace(".", ",")


def fmt(kg):
    return f"{de(to_display(kg))} {OPTIONS['display_unit']}"


def round_to(value, step):
    if value is None:
        return None
    return round(round(value / step) * step, 2)


# ---------------------------------------------------------------- Daten

def _lift_sets(lift=None):
    sql = """SELECT w.id, w.date, w.title, w.lift, w.pr, s.load_kg, s.reps, s.reps_assumed, s.success
             FROM workouts w JOIN sets s ON s.workout_id = w.id
             WHERE s.success = 1"""
    params = ()
    if lift:
        sql += " AND w.lift = ?"
        params = (lift,)
    return db.query(sql + " ORDER BY w.date, w.id, s.idx", params)


def lift_history(lift):
    """Pro Trainingstag: schwerster Satz, bestes geschätztes 1RM, PR-Markierung."""
    days = {}
    for s in _lift_sets(lift):
        est = e1rm(s["load_kg"], s["reps"])
        d = days.setdefault(s["date"], {
            "date": s["date"], "title": s["title"], "top_kg": 0, "top_reps": None,
            "e1rm_kg": 0, "e1rm_set": None, "assumed": False, "sugarwod_pr": False,
        })
        if s["load_kg"] > d["top_kg"]:
            d["top_kg"], d["top_reps"] = s["load_kg"], s["reps"]
        if est and est > d["e1rm_kg"]:
            d["e1rm_kg"] = est
            d["e1rm_set"] = f'{s["reps"]} × {fmt(s["load_kg"])}'
            d["assumed"] = bool(s["reps_assumed"])
        d["sugarwod_pr"] = d["sugarwod_pr"] or bool(s["pr"])
    out = []
    best_e, best_w = 0, 0
    for d in sorted(days.values(), key=lambda x: x["date"]):
        d["pr_e1rm"] = d["e1rm_kg"] > best_e * 1.001
        d["pr_weight"] = d["top_kg"] > best_w * 1.001
        best_e = max(best_e, d["e1rm_kg"])
        best_w = max(best_w, d["top_kg"])
        out.append(d)
    return out


def _window_best(hist, start, end):
    vals = [h["e1rm_kg"] for h in hist if start <= h["date"] < end]
    return max(vals) if vals else None


def lift_summary(lift, hist=None, today=None):
    hist = hist if hist is not None else lift_history(lift)
    if not hist:
        return None
    today = today or date.today()
    iso = lambda d: d.isoformat()
    recent_start = iso(today - timedelta(days=CURRENT_WINDOW_DAYS))
    current = _window_best(hist, recent_start, "9999")
    all_time = max(h["e1rm_kg"] for h in hist)
    last = hist[-1]["date"]
    days_since = (today - date.fromisoformat(last)).days
    # Trend: bestes 1RM der letzten 90 Tage gegen die 90 Tage davor
    a = _window_best(hist, iso(today - timedelta(days=90)), "9999")
    b = _window_best(hist, iso(today - timedelta(days=180)), iso(today - timedelta(days=90)))
    if a and b:
        change = (a - b) / b * 100
        trend = "steigend" if change >= 2 else ("fallend" if change <= -3 else "stagnierend")
    else:
        change, trend = None, "zu wenig Daten"
    return {
        "lift": lift,
        "category": movements.lift_category(lift) or "Sonstige",
        "current_kg": current if current else all_time,
        "current_is_stale": current is None,
        "all_time_kg": all_time,
        "last_date": last,
        "days_since": days_since,
        "sessions": len(hist),
        "trend": trend,
        "trend_pct": change,
        "assumed_reps": any(h["assumed"] for h in hist[-5:]),
    }


def all_lifts(today=None):
    lifts = [r["lift"] for r in db.query(
        "SELECT DISTINCT w.lift FROM workouts w JOIN sets s ON s.workout_id = w.id WHERE w.lift IS NOT NULL")]
    out = []
    for lift in lifts:
        s = lift_summary(lift, today=today)
        if s:
            out.append(s)
    order = {c: i for i, c in enumerate(movements.CATEGORIES)}
    out.sort(key=lambda s: (order.get(s["category"], 99), -s["current_kg"]))
    return out


# ---------------------------------------------------------------- Vorschlag

INTENSITY_RIR = {
    "technik": (4, "Technik/leicht: ca. 4 Wiederholungen Reserve"),
    "moderat": (2, "Moderat: ca. 2 Wiederholungen Reserve (RPE 8)"),
    "schwer": (1, "Schwer: ca. 1 Wiederholung Reserve (RPE 9)"),
    "maximal": (0, "Maximal: bis kurz vor Muskelversagen (RPE 10)"),
}

# Metcon: typische Prozentbänder vom 1RM je Wiederholungen pro Runde/Satz
METCON_BANDS = [
    (3, 0.70, 0.80),
    (6, 0.60, 0.72),
    (10, 0.50, 0.62),
    (15, 0.42, 0.55),
    (21, 0.35, 0.48),
    (999, 0.30, 0.40),
]


def suggest(lift, reps, sets=1, mode="kraft", intensity="moderat", percent=None, today=None):
    summary = lift_summary(lift, today=today)
    if not summary:
        return {"ok": False, "fehler": f"Für {lift} gibt es noch keine Gewichtsdaten."}
    step_disp = float(OPTIONS["plate_increment"])
    step_kg = from_display(step_disp)
    one_rm = summary["current_kg"]
    assumptions = [
        f"Geschätztes 1RM: {fmt(one_rm)} – bestes Ergebnis der letzten {CURRENT_WINDOW_DAYS} Tage"
        if not summary["current_is_stale"] else
        f"Geschätztes 1RM: {fmt(one_rm)} – Bestwert insgesamt, aber älter als {CURRENT_WINDOW_DAYS} Tage (eher zu hoch)",
        FORMULA_LABEL[OPTIONS["formula"]] + f"; Sätze über {MAX_REPS_FOR_ESTIMATE} Wdh. werden wie {MAX_REPS_FOR_ESTIMATE} gezählt.",
        f"Gerundet auf {de(step_disp, 2).rstrip('0').rstrip(',')} {OPTIONS['display_unit']}.",
    ]
    if summary["assumed_reps"]:
        assumptions.append("Bei einigen Einträgen fehlten die Wiederholungen – dort wurde 1 Wdh. angenommen.")
    result = {"ok": True, "lift": lift, "one_rm_kg": one_rm, "summary": summary, "mode": mode}

    if mode == "prozent":
        pct = float(percent or 0) / 100
        w = one_rm * pct
        result.update(weight_kg=round_to(w, step_kg), low_kg=None, high_kg=None)
        assumptions.append(f"{percent:g} % vom geschätzten 1RM.")
        if reps and pct:
            possible = max(1, round(30 * (1 / pct - 1)))
            assumptions.append(f"Bei {percent:g} % sind laut Epley etwa {possible} Wdh. bis zum Versagen möglich.")
    elif mode == "metcon":
        for limit, lo, hi in METCON_BANDS:
            if reps <= limit:
                break
        if sets and sets >= 5:
            lo, hi = lo - 0.03, hi - 0.03
            assumptions.append("Viele Runden: Band um 3 Prozentpunkte gesenkt.")
        result.update(weight_kg=round_to(one_rm * (lo + hi) / 2, step_kg),
                      low_kg=round_to(one_rm * lo, step_kg), high_kg=round_to(one_rm * hi, step_kg))
        assumptions.append(
            f"Metcon mit {reps} Wdh. pro Runde: üblich sind {lo*100:.0f}–{hi*100:.0f} % vom 1RM, "
            "damit die Sätze unbroken oder in wenigen Blöcken gehen.")
    else:
        rir, label = INTENSITY_RIR.get(intensity, INTENSITY_RIR["moderat"])
        w = weight_for_reps(one_rm, reps + rir)
        if sets and sets >= 4 and rir < 2:
            w *= 0.975
            assumptions.append("Ab 4 Sätzen 2,5 % weniger, um Ermüdung über die Sätze aufzufangen.")
        result.update(weight_kg=round_to(w, step_kg),
                      low_kg=round_to(weight_for_reps(one_rm, reps + rir + 1), step_kg),
                      high_kg=round_to(weight_for_reps(one_rm, reps + max(rir - 1, 0)), step_kg))
        assumptions.append(f"{label}: gerechnet wie ein Satz mit {reps + rir} Wdh. bis zum Versagen.")

    result["percent_of_1rm"] = result["weight_kg"] / one_rm * 100 if one_rm else None
    result["table"] = [{"pct": p, "kg": round_to(one_rm * p / 100, step_kg)} for p in range(50, 105, 5)]
    result["assumptions"] = assumptions
    return result


# ---------------------------------------------------------------- Stärken & Schwächen

RATIOS = [
    ("Front Squat", "Back Squat", 0.80, 0.90,
     "Front Squat schwächer als erwartet: aufrechte Position, Core und Front-Rack-Mobilität trainieren, mehr Front-Squat-Volumen.",
     "Back Squat hinkt hinterher: Grundkraft der Beine und hintere Kette ausbauen."),
    ("Overhead Squat", "Back Squat", 0.60, 0.72,
     "Overhead Squat limitiert: Schulter-/Brustwirbel-Mobilität und Stabilität über Kopf (z. B. Sots Press, OHS-Pausen).",
     "Starke Überkopf-Position – Back Squat könnte mehr."),
    ("Clean", "Front Squat", 0.80, 0.90,
     "Die Kraft ist da, der Clean nutzt sie nicht: Zugtechnik, Explosivität und schnelles Unterkommen üben.",
     "Front Squat limitiert den Clean: Front Squats schwerer trainieren."),
    ("Snatch", "Clean & Jerk", 0.78, 0.85,
     "Snatch schwach im Vergleich: Technik, Überkopf-Stabilität und Geschwindigkeit unter die Stange.",
     "Clean & Jerk limitiert – oft ist der Jerk der Engpass."),
    ("Clean & Jerk", "Clean", 0.92, 1.00,
     "Der Jerk kostet Gewicht: Jerk-Technik, Dip & Drive und Überkopf-Kraft.",
     None),
    ("Snatch", "Back Squat", 0.55, 0.67,
     "Snatch liegt weit unter dem Kraftniveau: Technikarbeit lohnt sich hier am meisten.",
     "Für den Snatch fehlt Grundkraft: Kniebeugen priorisieren."),
    ("Push Press", "Strict Press", 1.25, 1.40,
     "Push Press nutzt die Beine zu wenig: Dip & Drive üben.",
     "Strict Press ist der Engpass: Schulter- und Trizepskraft aufbauen."),
    ("Strict Press", "Bench Press", 0.60, 0.70,
     "Überkopf-Drücken schwach im Vergleich zum Bankdrücken: mehr Strict Press und Schulterstabilität.",
     "Bankdrücken unterdurchschnittlich – für CrossFit meist unkritisch."),
    ("Deadlift", "Back Squat", 1.15, 1.30,
     "Kreuzheben schwach: hintere Kette (Hüftstreckung, Rücken) und Griffkraft trainieren.",
     "Beine (Kniebeuge) hinken dem Kreuzheben hinterher."),
    ("Power Clean", "Clean", 0.80, 0.90,
     "Wenig Zugkraft/Explosivität – Power Cleans und Pulls trainieren.",
     "Fast so viel Power wie Squat Clean: Unterkommen in die tiefe Hocke üben."),
    ("Power Snatch", "Snatch", 0.80, 0.90,
     "Wenig Zugkraft/Explosivität – Power Snatches und Snatch Pulls trainieren.",
     "Fast so viel Power wie Squat Snatch: Mobilität und Mut in der tiefen Position."),
]

# Richtwerte für relatives 1RM (× Körpergewicht), "solides Fortgeschrittenen-Niveau"
BW_STANDARDS = {
    "Back Squat": 1.75, "Front Squat": 1.45, "Deadlift": 2.1, "Strict Press": 0.7,
    "Clean": 1.25, "Snatch": 0.95, "Clean & Jerk": 1.2,
}


def ratios(summaries):
    by = {s["lift"]: s for s in summaries}
    out = []
    for num, den, lo, hi, txt_low, txt_high in RATIOS:
        if num not in by or den not in by:
            continue
        r = by[num]["current_kg"] / by[den]["current_kg"]
        if r < lo:
            status, hint = "niedrig", txt_low
        elif r > hi:
            status, hint = "hoch", txt_high
        else:
            status, hint = "ok", None
        mid = (lo + hi) / 2
        out.append({"name": f"{num} / {den}", "num": num, "den": den, "ratio": r,
                    "low": lo, "high": hi, "status": status, "hint": hint,
                    "deviation_pct": (r - mid) / mid * 100})
    return out


def relative_strength(summaries):
    bw = float(OPTIONS.get("body_weight_kg") or 0)
    if bw <= 0:
        return []
    out = []
    for s in summaries:
        if s["lift"] in BW_STANDARDS:
            rel = s["current_kg"] / bw
            std = BW_STANDARDS[s["lift"]]
            out.append({"lift": s["lift"], "relative": rel, "standard": std, "pct_of_standard": rel / std * 100})
    out.sort(key=lambda x: x["pct_of_standard"])
    return out


def category_balance(today=None):
    today = today or date.today()
    start = (today - timedelta(days=90)).isoformat()
    rows = db.query("SELECT date, categories FROM workouts WHERE date >= ?", (start,))
    counts = defaultdict(int)
    last = {}
    for r in db.query("SELECT date, categories FROM workouts"):
        for c in filter(None, (r["categories"] or "").split(",")):
            last[c] = max(last.get(c, ""), r["date"])
    for r in rows:
        for c in filter(None, (r["categories"] or "").split(",")):
            counts[c] += 1
    total = sum(counts.values()) or 1
    return [{"category": c, "count_90d": counts.get(c, 0), "share": counts.get(c, 0) / total,
             "last_date": last.get(c),
             "days_since": (today - date.fromisoformat(last[c])).days if c in last else None}
            for c in movements.CATEGORIES]


def _score_value(score_type, raw):
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v


def benchmarks():
    """Wiederholte Workouts ohne Langhantel-Hauptübung (z. B. Fran, Max Pull-ups)."""
    rows = db.query(
        """SELECT date, title, score_type, best_raw, best_display, rx, categories FROM workouts
           WHERE lift IS NULL AND title <> '' ORDER BY date""")
    groups = defaultdict(list)
    for r in rows:
        groups[(r["title"].strip().lower(), (r["score_type"] or "").lower())].append(r)
    out = []
    for (_, st), items in groups.items():
        vals = [(i, _score_value(st, i["best_raw"])) for i in items]
        vals = [(i, v) for i, v in vals if v is not None]
        if len(vals) < 2:
            continue
        lower_better = st.startswith("time")
        pick = min if lower_better else max
        best_item, best_v = pick(vals, key=lambda x: x[1])
        first_item, first_v = vals[0]
        last_item, last_v = vals[-1]
        if first_v:
            change = (first_v - last_v) / first_v * 100 if lower_better else (last_v - first_v) / first_v * 100
        else:
            change = None
        out.append({
            "title": items[-1]["title"], "score_type": items[-1]["score_type"],
            "count": len(vals), "first": first_item["best_display"], "first_date": first_item["date"],
            "last": last_item["best_display"], "last_date": last_item["date"],
            "best": best_item["best_display"], "best_date": best_item["date"],
            "change_pct": change, "categories": items[-1]["categories"],
            "benchmark": movements.is_benchmark(items[-1]["title"]),
        })
    out.sort(key=lambda b: (not b["benchmark"], b["title"].lower()))
    return out


def recommendations(summaries, ratio_list, balance, bench):
    recs = []
    for r in ratio_list:
        if r["status"] != "ok" and r["hint"]:
            recs.append({"prio": min(abs(r["deviation_pct"]), 40) + 10, "art": "Verhältnis",
                         "titel": f'{r["name"]}: {de(r["ratio"], 2)} (Ziel {de(r["low"], 2)}–{de(r["high"], 2)})',
                         "text": r["hint"]})
    main = set(OPTIONS.get("sensor_lifts") or [])
    for s in summaries:
        if s["lift"] not in main and s["sessions"] < 4:
            continue
        if s["trend"] == "fallend":
            recs.append({"prio": 30 + min(abs(s["trend_pct"] or 0), 20), "art": "Trend",
                         "titel": f'{s["lift"]} fällt ({de(s["trend_pct"]).replace("-", "−") if s["trend_pct"] < 0 else "+" + de(s["trend_pct"])} % in 90 Tagen)',
                         "text": "Erholung, Technik und Trainingsfrequenz prüfen; ggf. Deload und neu aufbauen."})
        elif s["trend"] == "stagnierend" and s["lift"] in main:
            recs.append({"prio": 22, "art": "Trend",
                         "titel": f'{s["lift"]} stagniert ({de(s["trend_pct"]).replace("-", "−") if s["trend_pct"] < 0 else "+" + de(s["trend_pct"])} % in 90 Tagen)',
                         "text": "Reiz verändern: anderes Wiederholungsschema, Varianten (Pause, Tempo) oder einen Kraftzyklus einplanen."})
        if s["lift"] in main and s["days_since"] > STALE_DAYS:
            recs.append({"prio": 15, "art": "Daten",
                         "titel": f'{s["lift"]} seit {s["days_since"]} Tagen nicht schwer trainiert',
                         "text": "Das 1RM ist eine alte Schätzung. Einen schweren Dreier oder Einer testen, damit die Vorschläge stimmen."})
    counts = [b["count_90d"] for b in balance]
    avg = sum(counts) / len(counts) if counts else 0
    for b in balance:
        if avg and b["count_90d"] < avg * 0.4:
            recs.append({"prio": 25 if b["count_90d"] == 0 else 18, "art": "Balance",
                         "titel": f'{b["category"]} kommt zu kurz ({b["count_90d"]} Einheiten in 90 Tagen)',
                         "text": f'Gezielt 1–2 Einheiten {b["category"]} pro Woche einbauen.'})
    for bm in bench:
        if bm["count"] >= 3 and bm["change_pct"] is not None and bm["change_pct"] < -3:
            recs.append({"prio": 20, "art": "Benchmark",
                         "titel": f'{bm["title"]} schlechter als beim ersten Mal ({bm["last"]} statt {bm["first"]})',
                         "text": "Pacing und die limitierende Bewegung in diesem Workout analysieren."})
    recs.sort(key=lambda r: -r["prio"])
    return recs[:8]


def strengths(summaries, ratio_list, bench):
    """Positive Punkte, damit die Analyse nicht nur Defizite zeigt."""
    out = []
    for s in summaries:
        if s["trend"] == "steigend" and s["trend_pct"]:
            out.append(f'{s["lift"]}: +{de(s["trend_pct"])} % in den letzten 90 Tagen')
    for r in ratio_list:
        if r["status"] == "hoch" and r["num"] not in ("Clean & Jerk",):
            out.append(f'{r["num"]} stark im Verhältnis zu {r["den"]} ({de(r["ratio"], 2)})')
    for bm in bench:
        if bm["change_pct"] and bm["change_pct"] >= 5:
            out.append(f'{bm["title"]}: {bm["first"]} → {bm["last"]}')
    return out[:8]


def full_analysis(today=None):
    summaries = all_lifts(today=today)
    ratio_list = ratios(summaries)
    balance = category_balance(today=today)
    bench = benchmarks()
    return {
        "lifts": summaries,
        "ratios": ratio_list,
        "relative": relative_strength(summaries),
        "balance": balance,
        "benchmarks": bench,
        "recommendations": recommendations(summaries, ratio_list, balance, bench),
        "strengths": strengths(summaries, ratio_list, bench),
    }
