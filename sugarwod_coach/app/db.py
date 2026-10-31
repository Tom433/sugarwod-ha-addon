"""SQLite-Speicher unter /data."""
import os
import sqlite3
import threading

from config import DB_PATH

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY,
    hash TEXT UNIQUE NOT NULL,
    date TEXT NOT NULL,
    title TEXT,
    description TEXT,
    score_type TEXT,
    lift TEXT,
    lift_raw TEXT,
    categories TEXT,
    best_raw TEXT,
    best_display TEXT,
    rx TEXT,
    pr INTEGER DEFAULT 0,
    notes TEXT,
    import_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_workouts_lift ON workouts(lift, date);
CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);
CREATE TABLE IF NOT EXISTS sets (
    workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    load_kg REAL,
    reps INTEGER,
    reps_assumed INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_sets_workout ON sets(workout_id);
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY,
    filename TEXT,
    at TEXT,
    rows INTEGER,
    new_rows INTEGER,
    export_unit TEXT
);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


_con = None


def get():
    global _con
    if _con is None:
        _con = connect()
        _con.executescript(SCHEMA)
    return _con


def query(sql, params=()):
    with _lock:
        return [dict(r) for r in get().execute(sql, params).fetchall()]


def transaction():
    """Kontextmanager für Schreibzugriffe."""
    class _Tx:
        def __enter__(self):
            _lock.acquire()
            return get()

        def __exit__(self, exc_type, exc, tb):
            try:
                if exc_type:
                    get().rollback()
                else:
                    get().commit()
            finally:
                _lock.release()
    return _Tx()


def wipe():
    with transaction() as con:
        con.execute("DELETE FROM sets")
        con.execute("DELETE FROM workouts")
        con.execute("DELETE FROM imports")
