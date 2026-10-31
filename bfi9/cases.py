"""Fraud complaint registration and case management (local SQLite, see store.py).

Registering a complaint here is NOT a report to the police, a bank, the RBI or any government portal; nothing is
forwarded anywhere. Status changes and notes need the reviewer access code (BFI9_REVIEWER_CODE, set at launch):
a single shared code for a single-user Colab demo - not multi-user authentication."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

import pandas as pd

from . import monitor, phase8, store
from . import settings as S

CATEGORIES = ("Unauthorised card transaction", "UPI / payment-app fraud", "Phishing / vishing / smishing", "Account takeover",
              "Online shopping / merchant fraud", "Investment / loan scam", "Identity misuse", "Other")
ALERT_CATEGORY = "Model alert review"
STATUSES = ("Submitted", "Under Review", "Awaiting Information", "Resolved", "Closed")
TRANSITIONS = {"Submitted": {"Under Review", "Closed"}, "Under Review": {"Awaiting Information", "Resolved", "Closed"},
               "Awaiting Information": {"Under Review", "Closed"}, "Resolved": {"Under Review", "Closed"}, "Closed": set()}
EVIDENCE_TYPES = {".pdf": b"%PDF", ".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff", ".txt": None}
MAX_EVIDENCE_BYTES = 5 * 2**20
MAX_EVIDENCE_FILES = 3
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,}$")
PHONE = re.compile(r"^(\+91[- ]?)?[6-9]\d{9}$")
LONG_NUMBER = re.compile(r"(?<!\w)(?:\d[ -]?){9,19}(?!\w)")  # card / account / phone-like digit runs


class CaseError(ValueError):
    """User-facing validation/authorisation error. .errors holds {field: message}."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, dict) else {"form": str(errors)}
        super().__init__("; ".join(f"{k}: {v}" for k, v in self.errors.items()))


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def new_case_id() -> str:
    return f"BFI-{dt.datetime.now(dt.timezone.utc):%Y%m%d}-{secrets.token_hex(3).upper()}"


def mask_ref(ref: str | None) -> str | None:
    """Keep only the last 4 characters of a payment/transaction reference."""
    ref = re.sub(r"[^A-Za-z0-9]", "", ref or "")
    return None if not ref else "••••" + ref[-4:]


def mask_contact(c: str | None) -> str:
    if not c:
        return ""
    if "@" in c:
        user, dom = c.split("@", 1)
        return f"{user[:1]}•••@{dom}"
    return "••••••" + re.sub(r"\D", "", c)[-4:]


def scrub(text: str) -> tuple[str, int]:
    """Remove card/account-like digit runs and credential-looking strings from free text. Returns (text, n_removed)."""
    out, n = LONG_NUMBER.subn("[number removed]", text or "")
    out, k = re.subn(r"(?i)\b(otp|cvv|pin|password|upi pin)\b\s*[:=-]?\s*\S+", r"\1 [removed]", out)
    return out, n + k


def validate_complaint(f: dict) -> dict:
    """Return a clean record or raise CaseError with one message per bad field."""
    e, now = {}, dt.datetime.now(dt.timezone.utc)
    if f.get("category") not in CATEGORIES:
        e["category"] = "Choose a category from the list."
    inc = f.get("incident_utc")
    if not isinstance(inc, dt.datetime):
        e["incident"] = "Enter the incident date and time."
    else:
        inc = inc if inc.tzinfo else inc.replace(tzinfo=dt.timezone.utc)
        if inc > now + dt.timedelta(minutes=5):
            e["incident"] = "The incident time cannot be in the future."
        elif inc < now - dt.timedelta(days=3650):
            e["incident"] = "The incident time is more than 10 years ago."
    amt = f.get("amount")
    if amt not in (None, "") and not (isinstance(amt, (int, float)) and 0 < float(amt) <= 1e9):
        e["amount"] = "Amount must be a positive number up to 1,000,000,000 (or left empty)."
    ref = (f.get("txn_ref") or "").strip()
    if ref and not re.fullmatch(r"[A-Za-z0-9/_ -]{4,40}", ref):
        e["txn_ref"] = "Reference must be 4–40 letters/digits. Do not enter a full card number."
    elif ref and LONG_NUMBER.fullmatch(ref) and len(re.sub(r"\D", "", ref)) >= 13:
        e["txn_ref"] = "That looks like a full card number. Enter only the last 4 digits or the bank's transaction ID."
    contact = (f.get("contact") or "").strip()
    if contact and not (EMAIL.fullmatch(contact) or PHONE.fullmatch(contact.replace(" ", ""))):
        e["contact"] = "Enter a valid e-mail address or 10-digit Indian mobile number (or leave empty)."
    desc, removed = scrub((f.get("description") or "").strip())
    if not 20 <= len(desc) <= 2000:
        e["description"] = "Describe what happened in 20–2000 characters."
    if f.get("consent") is not True:
        e["consent"] = "Please confirm the acknowledgement before submitting."
    if e:
        raise CaseError(e)
    return {"category": f["category"], "incident_utc": inc.isoformat(timespec="minutes"), "amount": None if amt in (None, "") else float(amt),
            "txn_ref_masked": mask_ref(ref), "contact": contact or None, "description": desc, "redactions": removed}


def _check_code(code: str | None) -> None:
    want = os.environ.get("BFI9_REVIEWER_CODE", "")
    if not want:
        raise CaseError({"authorisation": "Reviewer actions are disabled: no reviewer access code is configured (BFI9_REVIEWER_CODE)."})
    if not hmac.compare_digest(str(code or ""), want):
        raise CaseError({"authorisation": "Reviewer access code is incorrect."})


def _safe_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name or "file").name).lstrip(".")[:80]
    return base or "file"


def _check_evidence(name: str, data: bytes) -> str:
    ext = Path(name or "").suffix.lower()
    if ext not in EVIDENCE_TYPES:
        raise CaseError({"evidence": f"{_safe_name(name)}: only PDF, PNG, JPG or TXT files are accepted."})
    if not 0 < len(data) <= MAX_EVIDENCE_BYTES:
        raise CaseError({"evidence": f"{_safe_name(name)}: file must be between 1 byte and 5 MB."})
    magic = EVIDENCE_TYPES[ext]
    if magic and not data.startswith(magic):
        raise CaseError({"evidence": f"{_safe_name(name)}: file content does not match its {ext} extension."})
    if magic is None:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise CaseError({"evidence": f"{_safe_name(name)}: TXT files must be UTF-8 text."})
    return _safe_name(name)


def _save_evidence(con, case_id: str, files) -> None:
    root = (S.RUNTIME / "evidence").resolve()
    for name, data in files:
        safe = _check_evidence(name, data)
        sha = hashlib.sha256(data).hexdigest()
        p = (root / case_id / f"{sha[:12]}_{safe}").resolve()
        if root not in p.parents:  # path-traversal guard
            raise CaseError({"evidence": "invalid file path"})
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        con.execute("INSERT INTO evidence(case_id, utc, filename, bytes, sha256, path) VALUES (?,?,?,?,?,?)",
                    (case_id, _now(), safe, len(data), sha, str(p)))


def create_complaint(form: dict, evidence=()) -> str:
    """Validate and store a complaint (+ optional evidence). Returns the new case ID. Nothing is sent externally."""
    rec = validate_complaint(form)
    evidence = list(evidence or [])
    if len(evidence) > MAX_EVIDENCE_FILES:
        raise CaseError({"evidence": f"Attach at most {MAX_EVIDENCE_FILES} files."})
    for n, d in evidence:  # validate everything before writing anything
        _check_evidence(n, d)
    cid, ts = new_case_id(), _now()
    with store.connect() as con:
        con.execute("INSERT INTO cases(case_id, created_utc, updated_utc, origin, category, incident_utc, amount, txn_ref_masked, contact, "
                    "description, status, consent) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, ts, ts, "complaint", rec["category"], rec["incident_utc"], rec["amount"], rec["txn_ref_masked"], rec["contact"],
                     rec["description"], "Submitted", 1))
        con.execute("INSERT INTO case_audit(case_id, utc, actor, action, to_status) VALUES (?,?,?,?,?)", (cid, ts, "complainant", "created", "Submitted"))
        _save_evidence(con, cid, evidence)
    return cid


def create_from_alert(reviewer: str, code: str, rationale: str, event_id: str | None = None, tid: int | None = None) -> str:
    """Open an investigation case from a model alert. Copies the stored score evidence; never edits it; never labels fraud."""
    _check_code(code)
    reviewer = (reviewer or "").strip()[:60]
    if not reviewer:
        raise CaseError({"reviewer": "Enter the reviewer name."})
    if event_id:
        ev = monitor.event(event_id)
        if not ev:
            raise CaseError({"alert": f"unknown event {event_id}"})
        tid, score, band, decision, demo = ev["transaction_id"], ev["score"], ev["band"], ev["decision"], ev["is_demo"]
    else:
        tx = phase8.transaction(int(tid))
        if tx.get("status") != "found":
            raise CaseError({"alert": f"transaction {tid} not found in the scored validation/test splits"})
        score, band, decision, demo = tx.get("model_score"), tx.get("risk_band"), tx.get("decision"), 0
    text, _ = scrub(rationale or "")
    cid, ts = new_case_id(), _now()
    with store.connect() as con:
        con.execute("INSERT INTO cases(case_id, created_utc, updated_utc, origin, category, description, status, reviewer, linked_tid, "
                    "linked_event_id, score_at_link, band_at_link, decision_at_link, rationale, is_demo, consent) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, ts, ts, "model alert", ALERT_CATEGORY, "Case opened by a reviewer from a model alert. "
                     "A model alert is a ranking signal for review, not confirmed fraud.", "Under Review", reviewer, int(tid), event_id,
                     None if score is None else float(score), band, decision, text[:1000], int(demo), 0))
        con.execute("INSERT INTO case_audit(case_id, utc, actor, action, to_status) VALUES (?,?,?,?,?)", (cid, ts, reviewer, "opened from alert", "Under Review"))
        if event_id:
            con.execute("UPDATE events SET review_status = 'case opened' WHERE event_id = ?", (event_id,))
    return cid


def update_status(case_id: str, new_status: str, actor: str, code: str, note: str = "") -> None:
    _check_code(code)
    actor = (actor or "").strip()[:60]
    if not actor:
        raise CaseError({"reviewer": "Enter the reviewer name."})
    with store.connect() as con:
        r = con.execute("SELECT status FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if not r:
            raise CaseError({"case": f"unknown case {case_id}"})
        if new_status not in TRANSITIONS[r["status"]]:
            raise CaseError({"status": f"cannot move from {r['status']} to {new_status}"})
        ts = _now()
        con.execute("UPDATE cases SET status = ?, updated_utc = ?, reviewer = ? WHERE case_id = ?", (new_status, ts, actor, case_id))
        con.execute("INSERT INTO case_audit(case_id, utc, actor, action, from_status, to_status) VALUES (?,?,?,?,?,?)",
                    (case_id, ts, actor, "status change", r["status"], new_status))
        if note.strip():
            con.execute("INSERT INTO case_notes(case_id, utc, author, note) VALUES (?,?,?,?)", (case_id, ts, actor, scrub(note.strip())[0][:2000]))


def add_note(case_id: str, author: str, code: str, note: str) -> None:
    _check_code(code)
    note, _ = scrub((note or "").strip())
    if not note or not (author or "").strip():
        raise CaseError({"note": "Reviewer name and note text are required."})
    with store.connect() as con:
        if not con.execute("SELECT 1 FROM cases WHERE case_id = ?", (case_id,)).fetchone():
            raise CaseError({"case": f"unknown case {case_id}"})
        ts = _now()
        con.execute("INSERT INTO case_notes(case_id, utc, author, note) VALUES (?,?,?,?)", (case_id, ts, author.strip()[:60], note[:2000]))
        con.execute("UPDATE cases SET updated_utc = ? WHERE case_id = ?", (ts, case_id))
        con.execute("INSERT INTO case_audit(case_id, utc, actor, action) VALUES (?,?,?,?)", (case_id, ts, author.strip()[:60], "note added"))


def get(case_id: str) -> dict | None:
    """One case with notes, audit trail and evidence metadata (contact masked)."""
    with store.connect() as con:
        r = con.execute("SELECT * FROM cases WHERE case_id = ?", ((case_id or "").strip().upper(),)).fetchone()
        if not r:
            return None
        c = dict(r)
        q = lambda t, o: [dict(x) for x in con.execute(f"SELECT * FROM {t} WHERE case_id = ? ORDER BY {o}", (c["case_id"],))]
        c["notes"], c["audit"], c["evidence"] = q("case_notes", "id"), q("case_audit", "id"), q("evidence", "id")
    c["contact"] = mask_contact(c["contact"])
    for ev in c["evidence"]:
        ev.pop("path")
    return c


def search(text: str = "", statuses=None, categories=None, date_from: dt.date | None = None, date_to: dt.date | None = None) -> pd.DataFrame:
    """Case list (no contact, no description) for tables, charts and exports."""
    q = ("SELECT case_id, created_utc, updated_utc, origin, category, status, reviewer, amount, txn_ref_masked, linked_tid, "
         "score_at_link, band_at_link, decision_at_link, is_demo FROM cases WHERE 1=1")
    a = []
    if text.strip():
        q += " AND (case_id LIKE ? OR CAST(linked_tid AS TEXT) = ?)"; a += [f"%{text.strip().upper()}%", text.strip()]
    if statuses:
        q += f" AND status IN ({','.join('?' * len(statuses))})"; a += list(statuses)
    if categories:
        q += f" AND category IN ({','.join('?' * len(categories))})"; a += list(categories)
    if date_from:
        q += " AND created_utc >= ?"; a.append(date_from.isoformat())
    if date_to:
        q += " AND created_utc < ?"; a.append((date_to + dt.timedelta(days=1)).isoformat())
    with store.connect() as con:
        return pd.read_sql_query(q + " ORDER BY created_utc DESC", con, params=a)


def export_redacted(df: pd.DataFrame) -> bytes:
    """CSV for sharing: no contact details, no free text, references already masked."""
    keep = [c for c in df.columns if c not in ("contact", "description", "rationale")]
    return df[keep].to_csv(index=False).encode("utf-8")
