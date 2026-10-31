"""Phase 9 paths and frozen facts. Frozen values are READ from Phase 4/5 files, never typed in here."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

# Step 1: roots (env overrides exist only for the test sandbox).
ROOT = Path(os.environ.get("BFI_ROOT", "/content"))
P9_DIR = Path(os.environ.get("BFI_P9_DIR", Path(__file__).resolve().parents[1]))
P8_DIR = Path(os.environ.get("BFI_P8_DIR", ROOT / "BFI_v2_Phase8_AI_Fraud_Analyst"))
P8_ZIP = ROOT / "BFI_v2_Phase8_AI_Fraud_Analyst.zip"
CLOSED_P8_ZIP_SHA = "c407b719a3ff34fded386334edb4edb8f4269d2fef61703d831f7d1b7f43c4d6"  # CLOSED Phase 8 release (Stage 1 re-verified)
P8_ZIP_SHA = os.environ.get("BFI_P8_ZIP_SHA_TESTONLY", CLOSED_P8_ZIP_SHA)  # override exists for the dev sandbox only; UI flags any mismatch
P4_DIR = ROOT / "ieee_data" / "BFI_v2_Phase4_Final"
P5_ZIP = ROOT / "BFI_v2_Phase5_Explainability.zip"
P6_DIR = ROOT / "BFI_v2_Phase6_Investigation_Workbench_v1.1"
P7_DIR = ROOT / "BFI_v2_Phase7_Fraud_Evaluation_Cost_Engine"
REC_DIR = Path(os.environ.get("BFI_REC_DIR", ROOT / "BFI_v2_Phase6_7_Reconstruction_Record"))  # S2 reconstruction evidence

# Step 2: BFI v1 sources (separate project; never joined with v2).
V1_RAW_ZIP = ROOT / "archive (2).zip"
V1_RAW_MEMBER = "indian_banking_transactions.csv"
V1_CLEAN = ROOT / "BFI_Phase3_Cleaned_Sorted_v2.csv"
V1_SYNTH_ZIP = ROOT / "archive (3).zip"           # SYNTHETIC monitoring data (demo/drift section only)
V1_REPORT = ROOT / "BFI_Phase2_Fraud_Formulation_Baseline_Report_and_Interview_Guide.docx"
V1_SUMMARY = ROOT / "BFI_Phase2_Summary.csv"
V1_NOTEBOOK = ROOT / "Bharat_Fraud_Intelligence.ipynb"
V1_CASE_STUDY = ROOT / "BFI_Case_Study.docx"

# Step 3: Phase 9 writable folders (everything Phase 9 writes stays inside P9_DIR).
OUTPUTS = P9_DIR / "outputs"
AUDIT_DIR = OUTPUTS / "phase9_audit"
RUNTIME = OUTPUTS / "runtime"                     # Phase 8 audit log/registry redirected here; excluded from release
CACHE = OUTPUTS / "cache"                         # derived caches; excluded from release
INTEL = OUTPUTS / "intelligence"
FEEDBACK = RUNTIME / "analyst_feedback.jsonl"

# Step 4: mode is fixed at launch (env), never by a widget or question text.
MODE = os.environ.get("BFI9_MODE", "investigation")
if MODE not in ("investigation", "evaluation"):
    raise ValueError("BFI9_MODE must be 'investigation' or 'evaluation'")

# Step 5: small-group rule for label-derived aggregates (investigation mode only shows unfiltered splits).
MIN_GROUP_N = 200
MIN_GROUP_POS = 10


@lru_cache(maxsize=1)
def frozen() -> dict:
    """Threshold and bands read from the Phase 4 config and Phase 5 band file (single source of truth)."""
    cfg = json.loads((P4_DIR / "BFI_v2_model_config.json").read_text())
    thr = cfg["threshold"]["value"] if isinstance(cfg["threshold"], dict) else float(cfg["threshold"])
    return {"threshold": float(thr), "threshold_source": cfg["threshold"].get("source", "") if isinstance(cfg["threshold"], dict) else "",
            "algorithm": cfg.get("algorithm"), "n_features": len(cfg.get("features", [])), "n_categorical": len(cfg.get("categorical_features", [])),
            "config_file": str(P4_DIR / "BFI_v2_model_config.json")}
