"""Übungsnamen vereinheitlichen und Kategorien zuordnen."""
import re

SQUAT = "Squat"
PULL = "Zug"
PRESS = "Drücken"
OLY = "Olympisches Gewichtheben"
GYM = "Gymnastics"
ENGINE = "Engine"

CATEGORIES = [SQUAT, PULL, PRESS, OLY, GYM, ENGINE]

# Kanonischer Name -> (Kategorie, Aliase in Kleinbuchstaben)
LIFTS = {
    "Back Squat": (SQUAT, ["back squat", "squat", "high bar back squat", "low bar back squat"]),
    "Front Squat": (SQUAT, ["front squat"]),
    "Overhead Squat": (SQUAT, ["overhead squat", "ohs"]),
    "Thruster": (SQUAT, ["thruster"]),
    "Deadlift": (PULL, ["deadlift", "conventional deadlift", "dl"]),
    "Sumo Deadlift": (PULL, ["sumo deadlift"]),
    "Romanian Deadlift": (PULL, ["romanian deadlift", "rdl"]),
    "Strict Press": (PRESS, ["strict press", "shoulder press", "press", "overhead press", "military press"]),
    "Push Press": (PRESS, ["push press"]),
    "Push Jerk": (PRESS, ["push jerk"]),
    "Split Jerk": (PRESS, ["split jerk", "jerk"]),
    "Bench Press": (PRESS, ["bench press", "bench"]),
    "Snatch": (OLY, ["snatch", "squat snatch", "full snatch"]),
    "Power Snatch": (OLY, ["power snatch"]),
    "Hang Snatch": (OLY, ["hang snatch", "hang squat snatch"]),
    "Hang Power Snatch": (OLY, ["hang power snatch"]),
    "Clean": (OLY, ["clean", "squat clean", "full clean"]),
    "Power Clean": (OLY, ["power clean"]),
    "Hang Clean": (OLY, ["hang clean", "hang squat clean"]),
    "Hang Power Clean": (OLY, ["hang power clean"]),
    "Clean & Jerk": (OLY, ["clean & jerk", "clean and jerk", "clean & jerk (squat)", "c&j", "squat clean & jerk"]),
}

_ALIAS = {}
for _name, (_cat, _aliases) in LIFTS.items():
    _ALIAS[_name.lower()] = _name
    for _a in _aliases:
        _ALIAS[_a] = _name


def _norm(text):
    text = (text or "").lower().replace("+", "&").replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .-:")


def canonical_lift(name):
    """Liefert den kanonischen Übungsnamen oder None."""
    n = _norm(name)
    if not n:
        return None
    if n in _ALIAS:
        return _ALIAS[n]
    # Zusätze wie "(from floor)" oder "1RM" abschneiden
    n2 = re.sub(r"\(.*?\)", "", n)
    n2 = re.sub(r"\b\d+\s*-?\s*rm\b", "", n2).strip(" .-:")
    return _ALIAS.get(n2)


def detect_lift_in_text(text):
    """Längster passender Übungsname in einem Titel wie 'Back Squat 5x5'."""
    n = _norm(text)
    best = None
    for alias, name in _ALIAS.items():
        if len(alias) < 4:
            continue
        if re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", n):
            if best is None or len(alias) > len(best[0]):
                best = (alias, name)
    return best[1] if best else None


def lift_category(name):
    return LIFTS[name][0] if name in LIFTS else None


GYM_WORDS = [
    "pull-up", "pull up", "pullup", "chest to bar", "c2b", "muscle-up", "muscle up",
    "handstand", "hspu", "toes-to-bar", "toes to bar", "t2b", "ring dip", "dip",
    "pistol", "rope climb", "push-up", "push up", "pushup", "l-sit", "knees to elbow",
]
ENGINE_WORDS = [
    "row", "run", "bike", "ski", "cal ", "cals", "calorie", "echo", "assault",
    "burpee", "double under", "double-under", " du ", "meter", " km", "mile", "swim",
]
OLY_WORDS = ["snatch", "clean", "jerk"]
SQUAT_WORDS = ["squat", "thruster", "wall ball", "wall-ball", "lunge", "box jump", "step-up"]
PULL_WORDS = ["deadlift", "kettlebell swing", "kb swing", "sdhp", "high pull"]
PRESS_WORDS = ["press", "push jerk"]

BENCHMARKS = {
    "fran", "grace", "helen", "diane", "elizabeth", "isabel", "annie", "cindy", "karen",
    "jackie", "nancy", "kelly", "murph", "dt", "amanda", "christine", "eva", "linda",
    "mary", "angie", "barbara", "chelsea", "lynne", "nicole", "jt", "randy", "kalsu",
}


def metcon_categories(title, description):
    """Kategorien, die ein Workout ohne Langhantel-Hauptübung trainiert."""
    text = " " + _norm(f"{title} {description}") + " "
    cats = []
    for cat, words in ((GYM, GYM_WORDS), (ENGINE, ENGINE_WORDS), (OLY, OLY_WORDS),
                       (SQUAT, SQUAT_WORDS), (PULL, PULL_WORDS), (PRESS, PRESS_WORDS)):
        if any(w in text for w in words):
            cats.append(cat)
    return cats


def is_benchmark(title):
    return _norm(title) in BENCHMARKS
