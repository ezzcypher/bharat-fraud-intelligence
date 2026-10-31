"""The ONLY bridge from Phase 9 to Phase 8 (and, through Phase 8's verified phase_links, to Phases 4-7).

Why a bridge: Phase 8 modules import each other by bare name (`settings`, `data_access`, ...). We verify
every Phase 8 source file against the CLOSED release ZIP before importing it, then redirect Phase 8's
runtime writes (audit log, registry, plots) into Phase 9's own outputs/runtime folder.
Mode is taken from bfi9.settings.MODE (fixed at launch) - callers cannot pass a mode."""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import sys
import zipfile
from functools import lru_cache
from types import SimpleNamespace

import numpy as np
import pandas as pd

from . import settings as S

MODULES = ["settings", "security", "phase_links", "prep_raw", "data_access", "metrics_adapter", "cost_adapter",
           "explanation_adapter", "stats_teaching", "plots", "analyst_tools", "assistant_engine", "report_generator", "phase9_api"]


class Phase8Unavailable(RuntimeError):
    """Raised when the Phase 8 release cannot be verified or imported."""


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@lru_cache(maxsize=1)
def load() -> SimpleNamespace:
    # Step 1: the release ZIP must be the CLOSED Phase 8 release.
    if not S.P8_ZIP.is_file() or _sha(S.P8_ZIP.read_bytes()) != S.P8_ZIP_SHA:
        raise Phase8Unavailable("Phase 8 release ZIP missing or checksum differs from the closed release")
    # Step 2: every src/*.py in the working folder must equal its copy inside the release ZIP.
    zf = zipfile.ZipFile(S.P8_ZIP)
    src = S.P8_DIR / "src"
    for f in sorted(src.glob("*.py")):
        member = f"BFI_v2_Phase8_AI_Fraud_Analyst/src/{f.name}"
        if _sha(f.read_bytes()) != _sha(zf.read(member)):
            raise Phase8Unavailable(f"Phase 8 source {f.name} differs from the release")
    # Step 3: import with Phase 8 src first on sys.path, then confirm each module really came from there.
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    mods = {m: importlib.import_module(m) for m in MODULES}
    for m, mod in mods.items():
        if not str(getattr(mod, "__file__", "")).startswith(str(src)):
            raise Phase8Unavailable(f"module {m} resolved outside Phase 8 src: {mod.__file__}")
    # Step 4: keep Phase 8's folder untouched - its runtime files go to Phase 9 outputs/runtime.
    S.RUNTIME.mkdir(parents=True, exist_ok=True)
    mods["settings"].AUDIT_LOG = S.RUNTIME / "phase8_audit_events.jsonl"
    mods["settings"].REGISTRY_FILE = S.RUNTIME / "phase8_project_registry.json"
    mods["plots"].PLOT_DIR = S.RUNTIME / "phase8_plots"
    # Step 5: the frozen threshold Phase 8 uses must equal Phase 4's config.
    if abs(mods["settings"].FROZEN_THRESHOLD - S.frozen()["threshold"]) > 0:
        raise Phase8Unavailable("Phase 8 threshold differs from Phase 4 config")
    return SimpleNamespace(**mods)


def status() -> dict:
    """Health check used by the Data Sources & Audit page."""
    try:
        p = load()
        return {"status": "ok", "api_version": p.phase9_api.API_VERSION, "release_sha256": S.P8_ZIP_SHA, "mode": S.MODE,
                "explanations": p.prep_raw.store_status().get("explanations_enabled", False)}
    except Exception as e:  # shown to the user, never hidden
        return {"status": "unavailable", "error": f"{type(e).__name__}: {e}"[:300]}


def safe(fn_name: str, *a, **k) -> dict:
    """Call a phase9_api function; failures come back as status='error' (never invented results)."""
    try:
        return getattr(load().phase9_api, fn_name)(*a, **k)
    except Exception as e:
        return {"status": "error", "function": fn_name, "error": f"{type(e).__name__}: {e}"[:300]}


# ----------------------------------------------------------------- API (mode fixed)
def transaction(tid) -> dict: return safe("transaction", tid, mode=S.MODE)
def explanation(tid) -> dict: return safe("explanation", tid, mode=S.MODE)
def ask(question: str) -> dict: return safe("ask", question, mode=S.MODE)
def report(subject: str, tid=None) -> dict: return safe("report", subject, tid, mode=S.MODE)
def evaluation(split="test", group="all", model="A") -> dict: return safe("evaluation", split=split, group=group, model=model)
def cost_scenario(base="illustrative_baseline", **ov) -> dict: return safe("cost_scenario", base, **ov)
def project_summary() -> dict: return safe("project_summary")
def data_quality() -> dict: return safe("data_quality")
def risk_bands() -> dict: return safe("risk_bands")
def tool_catalog(): return safe("tool_catalog")


# ----------------------------------------------------------------- data
@lru_cache(maxsize=1)
def _predictions_all() -> pd.DataFrame:
    return load().data_access.predictions()


def predictions() -> pd.DataFrame:
    """Phase 4 stored scores + Phase 5 band + frozen decision. isFraud only in evaluation mode."""
    p = _predictions_all().copy()
    return p if S.MODE == "evaluation" else p.drop(columns=["isFraud"])


def _labelled(split: str):
    d = _predictions_all()
    d = d[d["split"] == split]
    return d["isFraud"].to_numpy(), d["score_A"].to_numpy()


def p7():
    return load().phase_links.phase7()


def curves(split: str = "test", max_points: int = 1500) -> dict:
    """PR/ROC points from Phase 7 metrics_engine.curves on a FULL split (aggregate; no row-level labels)."""
    y, s = _labelled(split)
    c = p7()["metrics_engine"].curves(y, s)
    thin = lambda a, n: a[np.unique(np.linspace(0, len(a) - 1, min(n, len(a))).astype(int))]  # keep curve shape, cap points
    return {"status": "measured", "split": split, "pr_recall": thin(c["pr_recall"], max_points), "pr_precision": thin(c["pr_precision"], max_points),
            "roc_fpr": thin(c["roc_fpr"], max_points), "roc_tpr": thin(c["roc_tpr"], max_points),
            "prevalence": float(y.mean()), "source": "Phase 7 metrics_engine.curves on Phase 4 stored scores"}


def sandbox(threshold: float) -> dict:
    """EXPLORATORY: a hypothetical threshold on VALIDATION only (never the spent test set); frozen view untouched."""
    if not 0.0 < float(threshold) < 1.0:
        return {"status": "invalid", "error": "threshold must be in (0, 1)"}
    me = p7()["metrics_engine"]
    y, s = _labelled("val")
    clean = lambda m: {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in m.items()}
    return {"status": "exploratory", "split": "val", "threshold": float(threshold),
            "hypothetical": clean(me.evaluate_threshold(y, s, float(threshold))),
            "frozen": clean(me.evaluate_threshold(y, s, S.frozen()["threshold"])),
            "caveats": ["Validation split was used to choose the frozen threshold: in-sample and optimistic.",
                        "Sensitivity analysis only; the frozen Phase 4 threshold is unchanged."]}


def subset_metrics(index) -> dict:
    """Label-based metrics for a filtered subset: evaluation mode only, with small-group protection."""
    if S.MODE != "evaluation":
        return {"status": "restricted", "reason": "Label-based metrics for filtered subsets require evaluation mode (launch setting)."}
    d = _predictions_all().loc[index]
    y, s = d["isFraud"].to_numpy(), d["score_A"].to_numpy()
    if len(y) < S.MIN_GROUP_N or y.sum() < S.MIN_GROUP_POS or y.sum() == len(y):
        return {"status": "insufficient", "n": int(len(y)), "positives": int(y.sum()),
                "reason": f"needs >= {S.MIN_GROUP_N} rows, >= {S.MIN_GROUP_POS} positive and >= 1 negative labels"}
    me = p7()["metrics_engine"]
    out = {"status": "measured", "n": int(len(y)), "metrics": me.evaluate_threshold(y, s, S.frozen()["threshold"]), "ranking": me.ranking_metrics(y, s)}
    out["metrics"] = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in out["metrics"].items()}
    return out


# ----------------------------------------------------------------- explainability + cost
def global_importance() -> pd.DataFrame: return load().explanation_adapter.global_importance()
def availability_audit() -> pd.DataFrame: return load().explanation_adapter.availability_audit()
def unverified_families() -> set: return set(load().phase_links.unverified_families())
def cost_scenarios() -> list: return load().cost_adapter.scenarios()
def cost_one_way(param, values, base="illustrative_baseline") -> pd.DataFrame: return load().cost_adapter.one_way(param, values, base)
def break_even(base="illustrative_baseline") -> dict: return load().cost_adapter.break_even(base)
def p7_output(name: str) -> pd.DataFrame: return load().cost_adapter.stored_output(name)


def reliance() -> dict:
    """Share of total mean|SHAP| on families whose decision-time availability is unverified (Phase 6 rule)."""
    g, fam = global_importance(), unverified_families()
    share = float(g.loc[g["family"].isin(fam), "mean_abs_shap"].sum() / g["mean_abs_shap"].sum())
    return {"status": "derived", "share": share, "families": sorted(fam), "n_features": int(len(g)),
            "source": "Phase 5 global_feature_importance.csv x Phase 6 UNVERIFIED_FAMILIES"}


def to_json_safe(x):
    return json.loads(json.dumps(x, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


def explain_full(tid, top_k: int = 12) -> dict:
    """Same Phase 8 explain() the API uses, with more factors shown; mode still fixed by launch setting."""
    try:
        return to_json_safe(load().explanation_adapter.explain(tid, S.MODE, top_k=top_k))
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"[:300]}


def error_patterns(split: str = "test") -> pd.DataFrame:
    """Aggregate TP/FP/FN/TN by user group x band on a FULL split (Phase 8 stats_teaching)."""
    return load().stats_teaching.error_patterns(split)


def band_table(split: str = "test") -> pd.DataFrame:
    return load().stats_teaching.band_table(split, S.MODE)


def feature_association(feature: str, split: str = "test") -> dict:
    try:
        return to_json_safe(load().stats_teaching.feature_association(feature, split, S.MODE))
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"[:200]}
