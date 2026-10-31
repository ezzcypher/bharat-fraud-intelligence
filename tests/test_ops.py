"""Operations modules: complaint workflow, case management, live-event ingestion, graceful metric failures.

Uses a throwaway SQLite file and evidence folder; real Phase 4/8 artifacts for scoring (read-only)."""
import datetime as dt
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="bfi_ops_test_"))
os.environ["BFI9_OPS_DB"] = str(TMP / "ops.sqlite")
os.environ["BFI9_REVIEWER_CODE"] = "test-code-123"

from bfi9 import cases, monitor, phase8, store  # noqa: E402
from bfi9 import settings as S  # noqa: E402

NOW = dt.datetime.now(dt.timezone.utc)
GOOD = {"category": cases.CATEGORIES[1], "incident_utc": NOW - dt.timedelta(days=1), "amount": 2500.0, "txn_ref": "UPI 4123 9988 7712",
        "contact": "riya@example.com", "description": "Received a call claiming KYC update; paid via UPI collect request.", "consent": True}


def test_validation_errors_are_per_field():
    bad = dict(GOOD, category="x", incident_utc=NOW + dt.timedelta(days=2), amount=-1, contact="nope", description="short", consent=False)
    with pytest.raises(cases.CaseError) as e:
        cases.validate_complaint(bad)
    assert set(e.value.errors) == {"category", "incident", "amount", "contact", "description", "consent"}


def test_full_card_number_rejected_and_scrubbed():
    with pytest.raises(cases.CaseError) as e:
        cases.validate_complaint(dict(GOOD, txn_ref="4111 1111 1111 1111"))
    assert "txn_ref" in e.value.errors
    rec = cases.validate_complaint(dict(GOOD, description="Card 4111 1111 1111 1111 was charged, OTP 482913 shared by mistake."))
    assert "4111" not in rec["description"] and "482913" not in rec["description"] and rec["redactions"] >= 2


def test_complaint_persists_and_is_retrievable_from_a_new_connection():
    cid = cases.create_complaint(GOOD)
    assert cid.startswith("BFI-")
    raw = sqlite3.connect(store.db_path()).execute("SELECT status, txn_ref_masked, contact FROM cases WHERE case_id = ?", (cid,)).fetchone()
    assert raw == ("Submitted", "••••7712", "riya@example.com")      # stored; only last 4 of the reference
    c = cases.get(cid.lower())
    assert c["status"] == "Submitted" and c["contact"] == "r•••@example.com" and c["audit"][0]["action"] == "created"
    assert cid in set(cases.search(cid[-6:])["case_id"])
    assert cid in set(cases.search(statuses=["Submitted"], categories=[GOOD["category"]], date_from=NOW.date())["case_id"])


def test_status_workflow_requires_code_follows_transitions_and_is_audited():
    cid = cases.create_complaint(GOOD)
    with pytest.raises(cases.CaseError):
        cases.update_status(cid, "Under Review", "Asha", "wrong")
    with pytest.raises(cases.CaseError):
        cases.update_status(cid, "Resolved", "Asha", "test-code-123")         # Submitted -> Resolved not allowed
    cases.update_status(cid, "Under Review", "Asha", "test-code-123", "Called complainant")
    cases.add_note(cid, "Asha", "test-code-123", "Bank confirmed reversal pending; account 123456789012 noted")
    c = cases.get(cid)
    assert c["status"] == "Under Review" and len(c["notes"]) == 2 and "123456789012" not in c["notes"][1]["note"]
    assert [a["to_status"] for a in c["audit"] if a["action"] == "status change"] == ["Under Review"]
    os.environ.pop("BFI9_REVIEWER_CODE")
    try:
        with pytest.raises(cases.CaseError):
            cases.update_status(cid, "Closed", "Asha", "")                    # disabled when no code configured
    finally:
        os.environ["BFI9_REVIEWER_CODE"] = "test-code-123"


def test_evidence_limits_and_safe_storage():
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    cid = cases.create_complaint(GOOD, [("../../etc/passwd screenshot.png", png)])
    ev = cases.get(cid)["evidence"]
    assert ev[0]["filename"] == "passwd_screenshot.png" and "path" not in ev[0]
    stored = list((S.RUNTIME / "evidence" / cid).iterdir())
    assert len(stored) == 1 and stored[0].resolve().is_relative_to((S.RUNTIME / "evidence").resolve())
    for name, data in [("a.exe", b"MZ"), ("a.png", b"not a png"), ("a.pdf", b"%PDF" + b"0" * (5 * 2**20))]:
        with pytest.raises(cases.CaseError):
            cases.create_complaint(GOOD, [(name, data)])


def test_redacted_export_has_no_personal_fields():
    cases.create_complaint(GOOD)
    csv = cases.export_redacted(cases.search()).decode()
    head = csv.splitlines()[0].split(",")
    assert "contact" not in head and "description" not in head and "case_id" in head
    assert "riya@example.com" not in csv and "9988" not in csv


def _real_rows(n=5):
    import pyarrow.parquet as pq
    from bfi9 import data_v2
    ids = list(monitor._test_ids()[:n])
    return pq.read_table(data_v2._store_path(), filters=[("TransactionID", "in", ids)]).to_pandas()


def test_ingest_scores_with_frozen_model_reconciles_and_dedupes():
    rows = _real_rows()
    rep = monitor.ingest(rows, monitor.DEMO_SOURCE, is_demo=True)
    assert rep["accepted"] == len(rows) and not rep["rejected"]
    ev = monitor.events(demo="demo")
    assert (ev["source"].str.startswith("DEMO DATA")).all() and ev["is_demo"].eq(1).all()
    assert ((ev["score"] - ev["stored_score"]).abs() < 1e-6).all()        # same pipeline as Phase 4 stored scores
    thr = S.frozen()["threshold"]
    assert ((ev["score"] >= thr) == ev["decision"].eq("alert for review")).all()
    again = monitor.ingest(rows, monitor.DEMO_SOURCE, is_demo=True)
    assert again["accepted"] == 0 and again["duplicates"] == len(rows)


def test_ingest_rejects_bad_schema_and_bad_rows():
    rows = _real_rows(3)
    rep = monitor.ingest(rows.drop(columns=["card1"]), "unit-test")
    assert rep["accepted"] == 0 and rep["rejected"][0]["row"] == "all"
    bad = rows.copy()
    bad.loc[bad.index[0], "TransactionID"] = "1; DROP TABLE events"
    bad.loc[bad.index[1], "TransactionAmt"] = -5
    rep = monitor.ingest(bad, "unit-test")
    assert len(rep["rejected"]) == 2 and rep["accepted"] == 1
    assert monitor.events(demo="real")["source"].eq("unit-test").all()


def test_case_from_alert_preserves_scoring_evidence():
    ev = monitor.events(demo="demo").iloc[0]
    before = monitor.event(ev["event_id"])
    with pytest.raises(cases.CaseError):
        cases.create_from_alert("Asha", "wrong", "x", event_id=ev["event_id"])
    cid = cases.create_from_alert("Asha", "test-code-123", "High score; check device history", event_id=ev["event_id"])
    c, after = cases.get(cid), monitor.event(ev["event_id"])
    assert (c["linked_tid"], c["score_at_link"], c["band_at_link"], c["decision_at_link"]) == (before["transaction_id"], before["score"], before["band"], before["decision"])
    assert after["score"] == before["score"] and after["review_status"] == "case opened"
    assert c["category"] == cases.ALERT_CATEGORY and "not confirmed fraud" in c["description"] and c["is_demo"] == 1


def test_case_from_stored_transaction():
    tid = int(phase8.predictions().query("split == 'test'").index[0])
    cid = cases.create_from_alert("Asha", "test-code-123", "", tid=tid)
    assert cases.get(cid)["score_at_link"] == pytest.approx(phase8.transaction(tid)["model_score"])


def test_checked_evaluation_complete_and_incomplete(monkeypatch):
    from views import common
    ev, problem = common.checked_evaluation("test")
    assert problem is None and ev["metrics"]["TP"] == 1713 and ev["ranking"]["roc_auc"] > 0.9
    monkeypatch.setattr(common, "evaluation", lambda *a, **k: {"status": "measured", "metrics": {"TP": 1}, "ranking": {}})
    ev, problem = common.checked_evaluation("test")
    assert ev is None and "ranking.roc_auc" in problem and "Reference" in problem
    monkeypatch.setattr(common, "evaluation", lambda *a, **k: {"status": "error", "error": "simulated outage"})
    assert "simulated outage" in common.checked_evaluation("test")[1]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("page,patch", [("monitor", ""), ("complaints", ""), ("cases", ""), ("overview", ""), ("performance", ""),
                                        ("overview", "common.evaluation = lambda *a, **k: {'status': 'error', 'error': 'simulated outage'}"),
                                        ("performance", "common.evaluation = lambda *a, **k: {'status': 'measured', 'metrics': {}, 'ranking': {}}")])
def test_pages_render_without_exceptions(page, patch, theme):
    from streamlit.testing.v1 import AppTest
    app = Path(__file__).resolve().parents[1]
    f = TMP / f"run_{page}_{theme}_{abs(hash(patch))}.py"
    f.write_text(f"import sys; sys.path.insert(0, {str(app)!r})\nimport streamlit as st\nfrom bfi9 import ui\n"
                 f"st.session_state.setdefault('theme', {theme!r}); ui.inject_css()\nfrom views import common, {page}\n{patch}\n{page}.render()\n")
    at = AppTest.from_file(str(f), default_timeout=600).run()
    assert not at.exception, [e.value for e in at.exception]
    if patch:  # incomplete payload: clear unavailable message, no blank/zero KPIs
        assert any("did not return a complete result" in i.value for i in at.info)
