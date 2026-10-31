# BFI v2 — Operations modules (Live Monitoring, Complaints, Cases)

## What is real and what is not

| Item | Status in this build |
|---|---|
| External live transaction stream (bank, UPI, card network, gateway, government) | **Not connected.** No authorised source exists in this project. |
| Ingestion interface | `bfi9.monitor.ingest(rows, source)` and the *Ingest* tab (CSV/JSON upload). Rows are labelled **unverified source**. |
| Demo mode | `bfi9.monitor.demo_replay(n)` / *Replay DEMO DATA* button. Replays **historical** IEEE-CIS test-split rows from the validated Phase 8 feature store with arrival time = now. Every such event carries `is_demo = 1`, source `DEMO DATA · …`, and a visible **DEMO DATA** badge. They are not real-time transactions or live detections. |
| Scoring | Frozen Phase 4 model A via `bfi_phase5.build_features` + `predict_proba` (hash-verified through Phase 8 `phase_links`). Threshold read from `BFI_v2_model_config.json` (0.12379763346033115). Replayed scores are reconciled with stored Phase 4 scores (shown on the page). |
| Complaint registration | Local only. **Not** an official police, bank, RBI or government complaint; nothing is forwarded. |
| Persistence | SQLite at `outputs/runtime/bfi_ops.sqlite` (override: `BFI9_OPS_DB`). Survives page refresh and app restart; **lost on a Colab runtime reset** unless pointed at durable storage you configure and test yourself. |
| Authorisation | One shared reviewer access code from `BFI9_REVIEWER_CODE` (launch environment). Gates status changes, notes, alert review and case creation from alerts. Not multi-user authentication. Without the variable, reviewer actions are disabled. |

## Ingestion contract

Each event row must contain `TransactionID` (1–9 digits), `TransactionDT` (non-negative integer seconds from the IEEE-CIS reference), `TransactionAmt` (non-negative number) **and every one of the frozen model's input columns** (download the list from the *Ingest* tab). Absent columns reject the whole batch — they are never filled silently. Values may be empty (NaN) exactly as in the training data.

Pipeline: schema check → per-row validation (reasons returned) → in-batch de-duplication → frozen-model scoring → `INSERT OR IGNORE` keyed by `live:<TransactionID>` / `demo:<TransactionID>` (re-sent events are counted as duplicates) → ingestion log row (counts only).

## Complaint data handled

Category, incident time (entered in IST, stored UTC), optional amount, optional reference (**only the last 4 characters are stored**), optional contact (stored, shown masked, never exported), description (card/account-like digit runs and OTP/CVV/PIN values are removed before storage), acknowledgement, up to 3 evidence files (PDF/PNG/JPG/TXT, ≤ 5 MB each, extension + magic-byte check, sanitised filename, stored under `outputs/runtime/evidence/<case>/`).

Statuses: Submitted → Under Review → Awaiting Information / Resolved → Closed (allowed transitions enforced, every change in `case_audit`). Exports (`Export redacted case list`) contain no contact details, descriptions or notes.

## Switching to a production database

All SQL goes through `bfi9/store.py:connect()` with parameterised queries. Replace it with a driver for your database, keep the schema, and add real user authentication before multi-user use.
