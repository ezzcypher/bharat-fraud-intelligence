"""Live-monitoring ingestion: validate -> de-duplicate -> score with the FROZEN Phase 4 model -> store.

Sources in this build (no external stream is connected):
  * ingest(events, source)  - the ingestion interface. Any producer (file upload in the UI, a notebook cell, a future
    webhook/queue consumer) hands over raw IEEE-CIS-schema rows. Marked "unverified source" in the UI.
  * demo_replay(n)          - DEMO DATA: real IEEE-CIS test-split rows read from the Phase 8 feature store and
    "arriving" now. Historical rows with a simulated arrival time - never real-time fraud detections.
Scoring = Phase 5/6 bfi_phase5.build_features + predict_proba on the Phase 4 model file (no substitute model).
Every replayed score is reconciled with the stored Phase 4 score."""
from __future__ import annotations

import datetime as dt
import json
import math
from functools import lru_cache

import numpy as np
import pandas as pd

from . import phase8, store
from . import settings as S

REQUIRED = ("TransactionID", "TransactionDT", "TransactionAmt")
DEMO_SOURCE = "DEMO DATA · IEEE-CIS test-split replay (historical rows, simulated arrival)"
MAX_BATCH = 5000
REVIEW = ("new", "in review", "case opened", "dismissed")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@lru_cache(maxsize=1)
def model():
    """(bfi_phase5 module, frozen bundle, band config) - loaded through Phase 8's hash-verified links."""
    p = phase8.load()
    bp = p.phase_links.phase6_bfi()
    bundle = bp.load_bundle(S.P4_DIR)  # default = A_frozen_train_only, read-only
    if bundle["threshold"] != S.frozen()["threshold"]:
        raise RuntimeError("model bundle threshold differs from the frozen Phase 4 config")
    return bp, bundle, p.phase_links.band_config()


def _stored_scores() -> pd.Series:
    return phase8._predictions_all()["score_A"]


def _row_errors(r) -> str | None:
    # Step 1: per-row validation; reasons are shown to the user, rows are never silently coerced.
    try:
        phase8.load().security.validate_transaction_id(r["TransactionID"])
    except Exception as e:
        return f"TransactionID: {e}"
    amt = pd.to_numeric(r["TransactionAmt"], errors="coerce")
    if pd.isna(amt) or not math.isfinite(amt) or amt < 0:
        return "TransactionAmt must be a non-negative number"
    t = pd.to_numeric(r["TransactionDT"], errors="coerce")
    if pd.isna(t) or t < 0 or t != int(t):
        return "TransactionDT must be a non-negative integer (seconds from the dataset reference)"
    return None


def ingest(events, source: str, is_demo: bool = False) -> dict:
    """Validate, de-duplicate, score and store a batch. Returns a report; nothing is half-written."""
    source = (source or "").strip()
    if not source or len(source) > 120:
        raise ValueError("source label is required (max 120 characters)")
    df = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame(list(events))
    rep = {"source": source, "is_demo": bool(is_demo), "received": int(len(df)), "accepted": 0, "duplicates": 0, "rejected": []}
    if len(df) > MAX_BATCH:
        raise ValueError(f"batch larger than {MAX_BATCH} events")
    bp, bundle, bands = model()

    # Step 2: schema - the frozen model's full input schema is required (no silent NaN filling of absent columns).
    missing = [c for c in REQUIRED if c not in df] + [c for c in bundle["features"] if c not in df and c not in REQUIRED]
    if missing:
        rep["rejected"].append({"row": "all", "reason": f"missing {len(missing)} required columns, e.g. {missing[:5]}"})
    else:
        errs = df.apply(_row_errors, axis=1) if len(df) else pd.Series(dtype=object)
        for i, e in errs[errs.notna()].items():
            rep["rejected"].append({"row": int(i), "reason": e})
        df = df[errs.isna()] if len(df) else df
        df = df.assign(TransactionID=df["TransactionID"].astype(int))
        dup_in_batch = df["TransactionID"].duplicated()
        rep["duplicates"] += int(dup_in_batch.sum())
        df = df[~dup_in_batch]

    # Step 3: score with the frozen model, reconcile with stored Phase 4 scores where the ID is known.
    if not missing and len(df):
        X = bp.build_features(df, bundle)
        s = np.asarray(bp.predict_proba(bundle, X), dtype=float)
        stored = _stored_scores().reindex(df["TransactionID"]).to_numpy()
        thr, ts = bundle["threshold"], now()
        prefix = "demo" if is_demo else "live"
        rows = [(f"{prefix}:{tid}", int(tid), source, int(bool(is_demo)), ts, int(edt), float(a), None if pd.isna(pc) else str(pc),
                 float(sc), bp.risk_band(float(sc), bands), "alert for review" if sc >= thr else "no alert",
                 None if np.isnan(st_) else float(st_))
                for tid, edt, a, pc, sc, st_ in zip(df["TransactionID"], df["TransactionDT"], df["TransactionAmt"],
                                                    df.get("ProductCD", pd.Series([None] * len(df))), s, stored)]
        with store.connect() as con:
            before = con.total_changes
            con.executemany("INSERT OR IGNORE INTO events(event_id, transaction_id, source, is_demo, received_utc, event_dt, amount, "
                            "product_cd, score, band, decision, stored_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            rep["accepted"] = con.total_changes - before
        rep["duplicates"] += len(rows) - rep["accepted"]
    with store.connect() as con:  # Step 4: health/audit trail of every ingestion attempt (metadata only)
        con.execute("INSERT INTO ingest_log(utc, source, is_demo, received, accepted, duplicates, rejected, detail) VALUES (?,?,?,?,?,?,?,?)",
                    (now(), source, int(bool(is_demo)), rep["received"], rep["accepted"], rep["duplicates"], len(rep["rejected"]),
                     json.dumps(rep["rejected"][:20])))
    return rep


@lru_cache(maxsize=1)
def _test_ids() -> tuple:
    p = phase8._predictions_all()
    return tuple(sorted(p.index[p["split"] == "test"]))


def demo_replay(n: int = 50) -> dict:
    """DEMO DATA: the next n test-split rows (TransactionID order) from the validated Phase 8 feature store."""
    import pyarrow.parquet as pq
    from . import data_v2
    f = data_v2._store_path()
    if f is None:
        raise RuntimeError("Phase 8 feature store unavailable - build it with prep_raw.build_feature_store()")
    with store.connect() as con:
        done = con.execute("SELECT COUNT(*) FROM events WHERE is_demo = 1").fetchone()[0]
    ids = list(_test_ids()[done: done + max(1, min(int(n), 500))])
    if not ids:
        return {"source": DEMO_SOURCE, "received": 0, "accepted": 0, "duplicates": 0, "rejected": [], "note": "test split fully replayed"}
    rows = pq.read_table(f, filters=[("TransactionID", "in", ids)]).to_pandas()
    return ingest(rows, DEMO_SOURCE, is_demo=True)


def events(since: str | None = None, bands=None, statuses=None, demo: str = "all", limit: int = 20000) -> pd.DataFrame:
    """Stored events, newest first. demo: 'all' | 'demo' | 'real'."""
    q, a = "SELECT * FROM events WHERE 1=1", []
    if since:
        q += " AND received_utc >= ?"; a.append(since)
    if bands:
        q += f" AND band IN ({','.join('?' * len(bands))})"; a += list(bands)
    if statuses:
        q += f" AND review_status IN ({','.join('?' * len(statuses))})"; a += list(statuses)
    if demo in ("demo", "real"):
        q += " AND is_demo = ?"; a.append(1 if demo == "demo" else 0)
    q += " ORDER BY received_utc DESC, transaction_id DESC LIMIT ?"; a.append(int(limit))
    with store.connect() as con:
        return pd.read_sql_query(q, con, params=a)


def event(event_id: str) -> dict | None:
    with store.connect() as con:
        r = con.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    return dict(r) if r else None


def set_review(event_id: str, status: str) -> None:
    if status not in REVIEW:
        raise ValueError(f"review status must be one of {REVIEW}")
    with store.connect() as con:
        if con.execute("UPDATE events SET review_status = ? WHERE event_id = ?", (status, event_id)).rowcount != 1:
            raise ValueError(f"unknown event {event_id}")


def health() -> dict:
    """Connection/ingestion health for the status strip. Failures are reported, never hidden."""
    h = {"external_stream": "not connected - no authorised live source is configured in this build"}
    try:
        with store.connect() as con:
            h["db"] = "ok"
            h["events_real"], h["events_demo"] = (con.execute("SELECT COALESCE(SUM(is_demo=0),0), COALESCE(SUM(is_demo=1),0) FROM events").fetchone())
            h["last_event_utc"] = con.execute("SELECT MAX(received_utc) FROM events").fetchone()[0]
            last = con.execute("SELECT * FROM ingest_log ORDER BY id DESC LIMIT 1").fetchone()
            h["last_ingest"] = dict(last) if last else None
    except Exception as e:
        h["db"] = f"error: {type(e).__name__}"
    try:
        _, b, _ = model()
        h["model"] = f"ok - frozen {b['name']}, threshold {b['threshold']}"
    except Exception as e:
        h["model"] = f"unavailable: {type(e).__name__}: {str(e)[:120]}"
    return h
