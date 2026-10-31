"""14. Data Sources & Audit - phase history, lineage, reproducibility, integrity check, dictionary, demo mode."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from bfi9 import phase8, provenance, ui
from bfi9 import settings as S

LINEAGE = [("Raw data", "ieee-fraud-detection.zip → Phase 8 data/raw/*.csv", S.P8_DIR / 'data' / 'raw' / 'train_transaction.csv'),
           ("v1 cleaning/EDA (separate project)", "archive (2).zip → BFI_Phase3_Cleaned_Sorted_v2.csv", S.V1_CLEAN),
           ("Model features", "BFI_v2_feature_list.txt (431)", S.P4_DIR / 'BFI_v2_feature_list.txt'),
           ("Phase 4 prediction", "BFI_v2_FINAL_test_preds.csv / baseline_val_preds.csv", S.P4_DIR / 'BFI_v2_FINAL_test_preds.csv'),
           ("Phase 7 evaluation", "metrics.json, cost_scenarios.csv", S.P7_DIR / 'outputs' / 'metrics.json'),
           ("Phase 8 explanation", "validated feature store + TreeSHAP", S.P8_DIR / 'data' / 'feature_store' / 'validation.json'),
           ("Phase 9 visualisation", "this dashboard", S.P9_DIR / 'app.py')]


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def render():
    ui.header("Data Sources & Audit", "Phase history · lineage · reproducibility · integrity")
    t = st.tabs(["Phase history", "Lineage", "Reproducibility", "Integrity check", "Data dictionary", "Demo mode (synthetic)", "Dependency provenance"])
    with t[0]:
        p = S.AUDIT_DIR / "phase_history_matrix.csv"
        st.dataframe(pd.read_csv(p), hide_index=True, width="stretch") if p.is_file() else ui.unavailable("Phase history", "Stage 2 output missing")
    with t[1]:
        rows = [{"stage": s, "artefact": a, "present": path.exists()} for s, a, path in LINEAGE]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Only transitions backed by an existing artefact are listed. v1 data is a separate project and never feeds the v2 model.")
    with t[2]:
        if not (S.P4_DIR / "BFI_v2_model_config.json").is_file():  # public clone: private artifact bundle (BFI_ROOT) absent
            ui.unavailable("Reproducibility", "frozen Phase 4 model config not found - the private artifact bundle (BFI_ROOT) is not present")
        else:
            fz, s = S.frozen(), phase8.status()
            cfg = S.P4_DIR / "BFI_v2_model_config.json"
            val = S.P8_DIR / "data" / "feature_store" / "validation.json"
            st.json({"model": "A_frozen_train_only (LightGBM)", "model_config_sha256": _sha(cfg)[:16] + "…", "threshold": fz["threshold"], "threshold_source": fz["threshold_source"],
                     "splits_sha256": _sha(S.P4_DIR / "BFI_v2_splits.csv")[:16] + "…", "phase8_api": s, "phase8_release_is_closed_release": S.P8_ZIP_SHA == S.CLOSED_P8_ZIP_SHA,
                     "feature_store_validation": json.loads(val.read_text()) if val.is_file() else "missing", "mode": S.MODE,
                     "limitations": ["uncalibrated scores", "chargeback-derived labels", "test set spent", "feature availability unverified", "illustrative costs"]})
    with t[3]:
        before = S.AUDIT_DIR / "protected_hashes_before.json"
        if not before.is_file():
            ui.unavailable("Integrity check", "Stage 1 baseline missing")
        elif st.button("Run integrity check (hashes ~300 protected files; ~1 min)"):
            ref = json.loads(before.read_text())
            bad = [p for p, h in ref.items() if not Path(p).exists() or _sha(p) != h]
            (st.success if not bad else st.error)(f"{len(ref) - len(bad)} of {len(ref)} protected files unchanged since the Stage 1 audit." + (f" Changed: {bad[:10]}" if bad else ""))
    with t[4]:
        p = S.AUDIT_DIR / "data_dictionary.csv"
        if p.is_file():
            dd = pd.read_csv(p)
            ds = st.multiselect("Datasets", sorted(dd["dataset"].unique()), default=["train_transaction.csv"] if "train_transaction.csv" in set(dd["dataset"]) else None)
            q = st.text_input("Search column or meaning")
            v = dd[dd["dataset"].isin(ds)] if ds else dd
            if q:
                v = v[v["column_name"].str.contains(q, case=False) | v["semantic_meaning"].astype(str).str.contains(q, case=False)]
            st.dataframe(v, hide_index=True, width="stretch")
    with t[5]:
        ui.note("<b>SYNTHETIC demonstration data</b> from the Phase 6 Workbench. Never mixed with real evaluation data.", warn=True)
        db = next(iter(S.P6_DIR.rglob("*.sqlite")), None)
        if db:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            st.dataframe(pd.read_sql("select case_id, source, score, band, alert, model, scored_at from predictions limit 200", con), hide_index=True, width="stretch")
            con.close()
    with t[6]:
        # Step: reconstructed dependencies, read from the marker files and the S2 reconstruction record (never typed in)
        stt = provenance.status()
        st.dataframe(pd.DataFrame([{**r, "missing_not_recreated": len(r["missing_not_recreated"])} for r in stt]), hide_index=True, width="stretch")
        if any(r["reconstructed"] for r in stt):
            ui.note(f"<b>{provenance.LABEL}.</b> The original Phase 6 v1.1 and Phase 7 release ZIPs were not found. These folders contain only files "
                    "whose SHA-256 equals the hash recorded by the genuine releases. Missing files were <b>not</b> recreated, the original release "
                    "checksums are <b>not</b> reproduced, and the release-validation tests that need the missing files fail.", warn=True)
            st.markdown("**Missing original artefacts (not recreated)**")
            st.dataframe(pd.DataFrame(provenance.missing_artifacts()), hide_index=True, width="stretch")
            with st.expander(f"Recovered files and their verified SHA-256 ({len(provenance.recovered_files())})"):
                st.dataframe(pd.DataFrame(provenance.recovered_files()), hide_index=True, width="stretch")
        st.caption(f"Record folder: {S.REC_DIR}")
