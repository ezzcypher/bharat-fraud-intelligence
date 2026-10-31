"""Dependency provenance: which earlier-phase folders are RECONSTRUCTED (not the original release), read from the
marker file inside each folder and the reconstruction record. Nothing here is typed in by hand."""
from __future__ import annotations

import csv
from pathlib import Path

from bfi9 import settings as S

LABEL = "RECONSTRUCTED — NOT ORIGINAL RELEASE"
MARK = "RECONSTRUCTED_NOT_ORIGINAL_RELEASE.md"
PHASES = {"Phase 6 v1.1 Investigation Workbench": "P6_DIR", "Phase 7 Evaluation & Cost Engine": "P7_DIR"}


def _rows(name: str) -> list[dict]:
    # Step: read one CSV of the reconstruction record (empty list when the record is absent)
    p = S.REC_DIR / name
    return list(csv.DictReader(open(p, newline=""))) if p.is_file() else []


def status() -> list[dict]:
    """One row per dependency: reconstructed?, recovered file count, missing files (from the record, not guessed)."""
    rec, miss = _rows("recovered_files_verification.csv"), _rows("missing_artifacts.csv")
    out = []
    for name, attr in PHASES.items():
        d: Path = getattr(S, attr)
        recon = (d / MARK).is_file()
        out.append({"dependency": name, "folder": d.name, "present": d.is_dir(), "reconstructed": recon,
                    "label": LABEL if recon else ("original release folder" if d.is_dir() else "missing"),
                    "recovered_files_verified": sum(r["package"] == d.name for r in rec),
                    "missing_not_recreated": [m["path"] for m in miss if m["package"] == d.name]})
    return out


def any_reconstructed() -> bool:
    return any(r["reconstructed"] for r in status())


def missing_artifacts() -> list[dict]:
    return _rows("missing_artifacts.csv")


def recovered_files() -> list[dict]:
    return _rows("recovered_files_verification.csv")


# Release-validation tests that CANNOT pass while original files are missing (observed in S2; still reported as FAIL).
EXPECTED_FAILURES = {
    "phase6": {"test_manifest_matches_files": "MANIFEST lists TEST_REPORT.md and REMEDIATION_LOG.md, which are missing (not recreated)"},
    "phase7": {"test_manifest_and_sha256sums_match": "manifest lists 17 missing files (notebook, 13 figures, 3 reports); SHA256SUMS.txt missing",
               "test_protected_snapshot_unchanged": "its recorded snapshot includes the original v1.1 ZIP / v1.0 folder, absent from this runtime"},
}


def expected_reason(suite: str, test_name: str) -> str:
    return next((why for t, why in EXPECTED_FAILURES.get(suite, {}).items() if test_name.endswith(t)), "")
