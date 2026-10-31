"""Tests für die Web-API (Ingress-Sperre, Header, Eingabeprüfung).

Ausführen:  .venv/bin/python -m unittest discover tests
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("OPTIONS_FILE", os.path.join(os.environ["DATA_DIR"], "missing.json"))
sys.path.insert(0, os.path.join(ROOT, "sugarwod_coach", "app"))

import db  # noqa: E402
import server  # noqa: E402

CSV = (
    "date,title,best_result_raw,score_type,barbell_lift\n"
    "10/20/2026,Deadlift 1RM,400,Load,Deadlift\n"
    "10/21/2026,Back Squat 1RM,300,Load,Back Squat\n"
)


class IngressRestrictionTest(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self._old = server.RESTRICT_TO_INGRESS
        server.RESTRICT_TO_INGRESS = True

    def tearDown(self):
        server.RESTRICT_TO_INGRESS = self._old

    def test_ingress_gateway_allowed(self):
        r = self.client.get("/api/status", environ_base={"REMOTE_ADDR": server.INGRESS_GATEWAY})
        self.assertEqual(r.status_code, 200)

    def test_other_container_blocked(self):
        for path, method in (("/api/status", "get"), ("/api/data", "delete"), ("/", "get")):
            r = getattr(self.client, method)(path, environ_base={"REMOTE_ADDR": "172.30.33.5"})
            self.assertEqual(r.status_code, 403, f"{method.upper()} {path}")

    def test_delete_blocked_keeps_data(self):
        db.wipe()
        self.client.post("/api/import", data={"file": (__import__("io").BytesIO(CSV.encode()), "x.csv")},
                         environ_base={"REMOTE_ADDR": server.INGRESS_GATEWAY})
        self.client.delete("/api/data", environ_base={"REMOTE_ADDR": "172.30.33.5"})
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM workouts")[0]["n"], 2)


class ApiTest(unittest.TestCase):
    def setUp(self):
        server.RESTRICT_TO_INGRESS = False
        self.client = server.app.test_client()
        db.wipe()
        import importer
        importer.import_csv(CSV)

    def test_security_headers(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")

    def test_limit_negative_is_clamped(self):
        r = self.client.get("/api/workouts?limit=-1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()), 1)

    def test_limit_invalid(self):
        self.assertEqual(self.client.get("/api/workouts?limit=abc").status_code, 400)

    def test_upload_too_large(self):
        import io
        big = io.BytesIO(b"date\n" + b"x" * (6 * 1024 * 1024))
        r = self.client.post("/api/import", data={"file": (big, "big.csv")})
        self.assertEqual(r.status_code, 413)

    def test_static_path_traversal(self):
        for p in ("/static/../server.py", "/static/..%2fserver.py", "/static/%2e%2e/config.py"):
            self.assertEqual(self.client.get(p).status_code, 404, p)


class WatchFolderTest(unittest.TestCase):
    def test_symlink_ignored(self):
        folder = tempfile.mkdtemp()
        secret = os.path.join(tempfile.mkdtemp(), "geheim.csv")
        with open(secret, "w") as f:
            f.write(CSV)
        os.symlink(secret, os.path.join(folder, "link.csv"))
        server.OPTIONS["watch_folder"] = folder
        db.wipe()
        # Eine Runde der Schleife ausführen, dann über time.sleep abbrechen.
        orig_sleep = server.time.sleep

        def stop(_):
            raise KeyboardInterrupt
        server.time.sleep = stop
        try:
            with self.assertRaises(KeyboardInterrupt):
                server.watch_folder_loop()
        finally:
            server.time.sleep = orig_sleep
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM workouts")[0]["n"], 0)
        self.assertTrue(os.path.islink(os.path.join(folder, "link.csv")))


if __name__ == "__main__":
    unittest.main()
