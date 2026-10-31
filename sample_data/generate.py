"""Erzeugt einen synthetischen SugarWOD-Export (Gewichte in lbs) zum Testen.

Eingebaute "Befunde": Snatch schwach gegenüber Clean & Jerk, Strict Press stagniert,
Gymnastics kommt zu kurz, Back Squat und Deadlift steigen.

    python3 sample_data/generate.py > sample_data/sugarwod_beispiel.csv
"""
import csv
import json
import random
import sys
from datetime import date, timedelta

random.seed(42)
LBS = 2.20462262
START, END = date(2025, 1, 6), date(2026, 10, 30)
TOTAL_DAYS = (END - START).days

# Übung -> (1RM kg am Start, 1RM kg am Ende)
PROGRESS = {
    "Back Squat": (120, 142),
    "Front Squat": (100, 120),
    "Deadlift": (150, 175),
    "Strict Press": (55, 56),
    "Push Press": (75, 80),
    "Bench Press": (85, 90),
    "Clean": (90, 102),
    "Power Clean": (80, 88),
    "Clean & Jerk": (85, 96),
    "Snatch": (60, 66),
    "Power Snatch": (52, 57),
    "Overhead Squat": (75, 82),
}
SCHEMES = [("5x5", [5] * 5), ("5-5-5-3-3-3", [5, 5, 5, 3, 3, 3]), ("3x3", [3] * 3),
           ("Build to a heavy single", [1, 1, 1, 1, 1]), ("3RM", [3, 3, 3, 3]), ("5-3-1", [5, 3, 1])]
METCONS = [
    ("Fran", "21-15-9 Thrusters (95/65 lb), Pull-ups", "Time"),
    ("Helen", "3 RFT: 400m Run, 21 KB Swings, 12 Pull-ups", "Time"),
    ("Cindy", "AMRAP 20: 5 Pull-ups, 10 Push-ups, 15 Air Squats", "Rounds + Reps"),
    ("Grace", "30 Clean & Jerks for time (135/95 lb)", "Time"),
    ("Row 2k", "2000m Row for time", "Time"),
    ("Engine Builder", "5 RFT: 15 Cal Bike, 10 Burpees, 200m Run", "Time"),
    ("Max Pull-ups", "Max unbroken Pull-ups", "Reps"),
    ("Chipper", "50 Wall Balls, 40 Box Jumps, 30 Deadlifts, 20 Double Unders", "Time"),
    ("Sprint Intervals", "8x 250m Row / 1:00 rest", "Time"),
    ("AMRAP Mix", "AMRAP 12: 10 Wall Balls, 10 Cal Row, 10 Burpees", "Rounds + Reps"),
]


def one_rm(lift, d):
    a, b = PROGRESS[lift]
    t = (d - START).days / TOTAL_DAYS
    return a + (b - a) * t + random.uniform(-2, 2)


def weight_for(one, reps):
    return one / (1 + reps / 30) * random.uniform(0.92, 0.99) if reps > 1 else one * random.uniform(0.93, 1.0)


def fmt_time(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def main():
    w = csv.writer(sys.stdout)
    w.writerow(["date", "title", "description", "best_result_raw", "best_result_display", "score_type",
                "barbell_lift", "set_details", "notes", "rx_or_scaled", "pr"])
    best = {}
    bench_state = {"Fran": 330, "Helen": 690, "Cindy": 16, "Grace": 240, "Row 2k": 470,
                   "Engine Builder": 900, "Max Pull-ups": 14, "Chipper": 780,
                   "Sprint Intervals": 400, "AMRAP Mix": 6}
    d = START
    lifts = list(PROGRESS)
    weights = [5, 4, 4, 3, 1, 1, 3, 2, 3, 2, 2, 1]
    while d <= END:
        if d.weekday() in (0, 1, 3, 4) and random.random() < 0.85:
            if random.random() < 0.7:
                lift = random.choices(lifts, weights)[0]
                name, scheme = random.choice(SCHEMES)
                one = one_rm(lift, d)
                sets = []
                for i, reps in enumerate(scheme):
                    ramp = 0.85 + 0.15 * (i + 1) / len(scheme) if name.startswith("Build") or "RM" in name else 1
                    kg = weight_for(one, reps) * ramp
                    lbs = round(kg * LBS / 5) * 5
                    sets.append({"success": random.random() > 0.05, "load": lbs})
                top = max(s["load"] for s in sets if s["success"]) if any(s["success"] for s in sets) else sets[0]["load"]
                key = (lift, max(scheme))
                pr = top > best.get(key, 0)
                best[key] = max(best.get(key, 0), top)
                w.writerow([d.strftime("%m/%d/%Y"), f"{lift} {name}", f"{lift}: {name}", top, f"{top} lbs",
                            "Load", lift, json.dumps(sets), "", "RX", "PR" if pr else ""])
            mc = random.choices(METCONS, [2, 1, 1, 1, 2, 3, 0.5, 2, 2, 3])[0]
            title, desc, st = mc
            prev = bench_state[title]
            if st == "Time":
                val = prev * random.uniform(0.95, 1.04)
                bench_state[title] = prev * 0.995
                w.writerow([d.strftime("%m/%d/%Y"), title, desc, round(val), fmt_time(val), st, "", "", "",
                            "RX", ""])
            else:
                val = max(1, round(prev * random.uniform(0.95, 1.06)))
                bench_state[title] = prev * 1.004
                disp = f"{val} rounds" if st.startswith("Rounds") else f"{val} reps"
                w.writerow([d.strftime("%m/%d/%Y"), title, desc, val, disp, st, "", "", "", "RX", ""])
        d += timedelta(days=1)


if __name__ == "__main__":
    main()
