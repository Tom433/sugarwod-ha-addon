"""Tests ohne Home Assistant:  .venv/bin/python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["OPTIONS_FILE"] = os.path.join(os.environ["DATA_DIR"], "missing.json")
sys.path.insert(0, os.path.join(ROOT, "sugarwod_coach", "app"))

import analysis  # noqa: E402
import db  # noqa: E402
import importer  # noqa: E402
import movements  # noqa: E402
from config import OPTIONS  # noqa: E402

TODAY = date(2026, 10, 31)


class RepSchemeTest(unittest.TestCase):
    def test_schemes(self):
        self.assertEqual(importer.parse_rep_scheme("Back Squat 5x5"), [5] * 5)
        self.assertEqual(importer.parse_rep_scheme("5-5-5-3-3-3"), [5, 5, 5, 3, 3, 3])
        self.assertEqual(importer.parse_rep_scheme("Snatch 1RM"), [1])
        self.assertEqual(importer.parse_rep_scheme("Find a 3-RM"), [3])
        self.assertEqual(importer.parse_rep_scheme("Build to a heavy double"), [2])
        self.assertIsNone(importer.parse_rep_scheme("Every 2:00 for 10 min"))


class FormulaTest(unittest.TestCase):
    def test_e1rm(self):
        self.assertEqual(analysis.e1rm(100, 1), 100)
        self.assertAlmostEqual(analysis.e1rm(100, 5, "epley"), 116.67, places=1)
        self.assertAlmostEqual(analysis.e1rm(100, 5, "brzycki"), 112.5, places=1)

    def test_inverse(self):
        for f in ("epley", "brzycki", "mittel"):
            one = analysis.e1rm(100, 5, f)
            self.assertAlmostEqual(analysis.weight_for_reps(one, 5, f), 100, delta=0.6)


class MovementTest(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(movements.canonical_lift("Squat Clean"), "Clean")
        self.assertEqual(movements.canonical_lift("Clean and Jerk"), "Clean & Jerk")
        self.assertEqual(movements.canonical_lift("Shoulder Press"), "Strict Press")
        self.assertEqual(movements.detect_lift_in_text("Hang Power Clean 5x3"), "Hang Power Clean")


class ImportAnalysisTest(unittest.TestCase):
    def setUp(self):
        db.wipe()
        OPTIONS["export_unit"] = "lbs"

    def test_sample_import(self):
        with open(os.path.join(ROOT, "sample_data", "sugarwod_beispiel.csv"), "rb") as f:
            content = f.read()
        res = importer.import_csv(content, "x.csv")
        self.assertGreater(res["neu"], 400)
        again = importer.import_csv(content, "x.csv")
        self.assertEqual(again["neu"], 0)
        a = analysis.full_analysis(today=TODAY)
        names = {r["name"]: r for r in a["ratios"]}
        self.assertEqual(names["Snatch / Clean & Jerk"]["status"], "niedrig")
        self.assertTrue(a["recommendations"])

    def test_lbs_conversion_and_reps(self):
        csv_text = (
            "date,title,description,best_result_raw,best_result_display,score_type,barbell_lift,set_details,notes,rx_or_scaled,pr\n"
            '10/01/2026,Back Squat 3x5,,225,225 lbs,Load,Back Squat,"[{""success"":true,""load"":225},'
            '{""success"":true,""load"":225},{""success"":false,""load"":245}]",,RX,\n'
        )
        importer.import_csv(csv_text)
        sets = db.query("SELECT load_kg, reps, success FROM sets ORDER BY idx")
        self.assertAlmostEqual(sets[0]["load_kg"], 102.06, places=1)
        self.assertEqual(sets[0]["reps"], 5)
        hist = analysis.lift_history("Back Squat")
        self.assertAlmostEqual(hist[0]["top_kg"], 102.06, places=1)  # Fehlversuch zählt nicht

    def test_suggest(self):
        csv_text = (
            "date,title,best_result_raw,score_type,barbell_lift\n"
            "10/20/2026,Deadlift 1RM,400,Load,Deadlift\n"
        )
        importer.import_csv(csv_text)
        r = analysis.suggest("Deadlift", 5, 5, "prozent", percent=70, today=TODAY)
        one = 400 / 2.20462262
        self.assertAlmostEqual(r["one_rm_kg"], one, places=1)
        self.assertEqual(r["weight_kg"] % 2.5, 0)
        self.assertAlmostEqual(r["weight_kg"], one * 0.7, delta=1.3)


if __name__ == "__main__":
    unittest.main()
