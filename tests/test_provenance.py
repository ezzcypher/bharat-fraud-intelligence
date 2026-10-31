"""Reconstructed-dependency labelling: driven by the marker file + reconstruction record, never hard-coded."""
import csv

import pytest
from streamlit.testing.v1 import AppTest

from bfi9 import provenance
from bfi9 import settings as S
from conftest import REAL


def _fake(tmp_path, monkeypatch, marked: bool):
    # Step 1: two dependency folders (+ marker in one case) and a record with one recovered and one missing file
    p6, p7, rec = tmp_path / "BFI_v2_Phase6_Investigation_Workbench_v1.1", tmp_path / "BFI_v2_Phase7_Fraud_Evaluation_Cost_Engine", tmp_path / "rec"
    for d in (p6, p7, rec):
        d.mkdir()
    if marked:
        (p6 / provenance.MARK).write_text("x")
    with open(rec / "missing_artifacts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["package", "path"]); w.writeheader(); w.writerow({"package": p6.name, "path": "TEST_REPORT.md"})
    with open(rec / "recovered_files_verification.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["package", "path"]); w.writeheader(); w.writerow({"package": p6.name, "path": "src/workbench.py"})
    monkeypatch.setattr(S, "P6_DIR", p6); monkeypatch.setattr(S, "P7_DIR", p7); monkeypatch.setattr(S, "REC_DIR", rec)


def test_p01_marker_drives_status(tmp_path, monkeypatch):
    _fake(tmp_path, monkeypatch, marked=True)
    r = {x["folder"]: x for x in provenance.status()}
    p6 = r["BFI_v2_Phase6_Investigation_Workbench_v1.1"]
    assert p6["reconstructed"] and p6["label"] == provenance.LABEL == "RECONSTRUCTED — NOT ORIGINAL RELEASE"
    assert p6["missing_not_recreated"] == ["TEST_REPORT.md"] and p6["recovered_files_verified"] == 1
    assert not r["BFI_v2_Phase7_Fraud_Evaluation_Cost_Engine"]["reconstructed"] and provenance.any_reconstructed()


def test_p02_no_marker_no_label(tmp_path, monkeypatch):
    _fake(tmp_path, monkeypatch, marked=False)
    assert not provenance.any_reconstructed()


def test_p03_banner_renders_label_when_reconstructed():
    # Step 2: the real banner function, rendered headless; in Colab the real marker files decide
    def page():
        from bfi9 import ui
        ui.provenance_banner()
    at = AppTest.from_function(page).run(timeout=60)
    shown = " ".join(w.value for w in at.warning)
    if provenance.any_reconstructed():
        assert provenance.LABEL in shown and "release validation is incomplete" in shown
    else:
        assert provenance.LABEL not in shown


def test_p04_real_runtime_record_consistent():
    # Step 3: in Colab, every missing artefact listed in the record is really absent from the reconstructed folder
    if not (REAL and S.REC_DIR.is_dir()):
        pytest.skip("reconstruction record not present in this environment")
    for r in provenance.status():
        if r["reconstructed"]:
            folder = getattr(S, provenance.PHASES[r["dependency"]])
            present = [m for m in r["missing_not_recreated"] if not m.endswith(".zip") and "(" not in m and (folder / m).exists()]
            assert present == [], f"listed as missing but present: {present}"
            assert r["recovered_files_verified"] > 0
