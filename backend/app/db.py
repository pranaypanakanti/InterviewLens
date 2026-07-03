"""SQLite cache: research runs keyed by (company, role, mode) + entity cache by input hash."""
import json
import os
import sqlite3
import threading
import time

from .config import settings

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _lock, _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS runs (
                company_key TEXT NOT NULL,
                role_key    TEXT NOT NULL,
                mode        TEXT NOT NULL,
                created_at  REAL NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (company_key, role_key, mode)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS entity_cache (
                input_hash  TEXT PRIMARY KEY,
                created_at  REAL NOT NULL,
                payload_json TEXT NOT NULL
            )"""
        )


def _keys(company: str, role: str) -> tuple[str, str]:
    return company.strip().lower(), role.strip().lower()


def get_cached_run(company: str, role: str, mode: str) -> dict | None:
    ck, rk = _keys(company, role)
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM runs WHERE company_key=? AND role_key=? AND mode=?",
            (ck, rk, mode),
        ).fetchone()
    return json.loads(row[0]) if row else None


def save_run(company: str, role: str, mode: str, result: dict):
    ck, rk = _keys(company, role)
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?)",
            (ck, rk, mode, time.time(), json.dumps(result)),
        )


def get_cached_entities(input_hash: str) -> dict | None:
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT payload_json FROM entity_cache WHERE input_hash=?", (input_hash,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def save_entities(input_hash: str, payload: dict):
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO entity_cache VALUES (?, ?, ?)",
            (input_hash, time.time(), json.dumps(payload)),
        )
