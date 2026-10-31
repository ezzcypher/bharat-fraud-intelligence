"""Local SQLite store for live-monitoring events and fraud cases.

Colab demo persistence: the file lives in outputs/runtime/ and survives page refreshes and app restarts,
but NOT a Colab runtime reset (unless BFI9_OPS_DB points at durable storage such as a mounted Drive).
Every query is parameterised. Swap connect() for a production database driver later; callers only use SQL."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import settings as S

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  event_id TEXT PRIMARY KEY, transaction_id INTEGER NOT NULL, source TEXT NOT NULL, is_demo INTEGER NOT NULL,
  received_utc TEXT NOT NULL, event_dt INTEGER, amount REAL, product_cd TEXT,
  score REAL NOT NULL, band TEXT NOT NULL, decision TEXT NOT NULL, stored_score REAL,
  review_status TEXT NOT NULL DEFAULT 'new');
CREATE INDEX IF NOT EXISTS ix_events_received ON events(received_utc);
CREATE TABLE IF NOT EXISTS ingest_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, utc TEXT NOT NULL, source TEXT NOT NULL, is_demo INTEGER NOT NULL,
  received INTEGER, accepted INTEGER, duplicates INTEGER, rejected INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS cases(
  case_id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL, origin TEXT NOT NULL,
  category TEXT NOT NULL, incident_utc TEXT, amount REAL, txn_ref_masked TEXT, contact TEXT,
  description TEXT NOT NULL, status TEXT NOT NULL, reviewer TEXT,
  linked_tid INTEGER, linked_event_id TEXT, score_at_link REAL, band_at_link TEXT, decision_at_link TEXT,
  rationale TEXT, is_demo INTEGER NOT NULL DEFAULT 0, consent INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS case_notes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(case_id),
  utc TEXT NOT NULL, author TEXT NOT NULL, note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS case_audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(case_id),
  utc TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, from_status TEXT, to_status TEXT);
CREATE TABLE IF NOT EXISTS evidence(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(case_id),
  utc TEXT NOT NULL, filename TEXT NOT NULL, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, path TEXT NOT NULL);
"""


def db_path() -> Path:
    # Step 1: read at call time so tests (and a Drive-backed setup) can point elsewhere.
    return Path(os.environ.get("BFI9_OPS_DB", S.RUNTIME / "bfi_ops.sqlite"))


def connect() -> sqlite3.Connection:
    # Step 2: one short-lived connection per operation (Streamlit reruns on many threads).
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con
