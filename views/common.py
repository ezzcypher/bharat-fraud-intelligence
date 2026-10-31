"""Shared, cached loaders and the global filter bar used by every BFI v2 page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from bfi9 import data_v2, filters, phase8, ui
from bfi9 import settings as S


@st.cache_resource(show_spinner="Loading verified Phase 4–8 data…")
def frame() -> pd.DataFrame:
    return data_v2.eval_frame()


@st.cache_data(show_spinner=False)
def evaluation(split="test", group="all", model="A") -> dict:
    return phase8.evaluation(split, group, model)


@st.cache_data(show_spinner=False)
def curves(split="test") -> dict:
    return phase8.curves(split)


@st.cache_data(show_spinner=False)
def status() -> dict:
    return phase8.status()


def require_v2() -> bool:
    s = status()
    if s["status"] != "ok":
        ui.unavailable("This page", f"The verified Phase 8 bridge could not load: {s.get('error')}")
        return False
    return True


def filter_state(df: pd.DataFrame) -> dict:
    if "filters" not in st.session_state:
        st.session_state["filters"] = filters.defaults(df)
    return st.session_state["filters"]


def filter_bar(df: pd.DataFrame) -> pd.DataFrame:
    """Compact global filters (only real columns). Returns the filtered frame; state persists across pages."""
    f = filter_state(df)
    cols = data_v2.available_filters(df)
    with st.expander("Filters", expanded=False):
        c = st.columns(4)
        if "split" in cols:
            f["split"] = c[0].multiselect("Split", sorted(df["split"].unique()), f.get("split"), help="Phase 4 day-based split (val = validation, test = spent holdout)")
        f["score"] = c[1].slider("Model score", 0.0, 1.0, tuple(f.get("score", (0.0, 1.0))), 0.01, help="Uncalibrated ranking score, not a probability")
        if "risk_band" in cols:
            f["risk_band"] = c[2].multiselect("Risk band", list(ui.BAND), f.get("risk_band", []), help="Provisional Phase 5 bands")
        if "decision" in cols:
            f["decision"] = c[3].multiselect("Decision", sorted(df["decision"].unique()), f.get("decision", []))
        c = st.columns(4)
        if "day" in cols:
            lo, hi = int(df["day"].min()), int(df["day"].max())
            f["day"] = c[0].slider("Relative day (no calendar)", lo, hi, tuple(f.get("day", (lo, hi))), help="TransactionDT // 86400 from an undisclosed reference")
        if "amount_usd" in cols:
            lo, hi = float(df["amount_usd"].min()), float(df["amount_usd"].max())
            f["amount_usd"] = c[1].slider("Amount (USD)", lo, hi, tuple(f.get("amount_usd", (lo, hi))))
        if "identity_present" in cols:
            f["identity_present"] = c[2].radio("Identity record", ["any", "yes", "no"], ["any", "yes", "no"].index(f.get("identity_present", "any")), horizontal=True)
        f["tid"] = c[3].text_input("TransactionID", f.get("tid", ""))
        c = st.columns(6)
        helps = {"ProductCD": "Masked product code (closest to 'transaction type')", "card4": "Card network", "card6": "Card type (debit/credit)",
                 "P_emaildomain": "Purchaser e-mail domain", "addr1": "Masked billing region code (geography)", "addr2": "Masked billing country code (geography)"}
        for i, col in enumerate(["ProductCD", "card4", "card6", "P_emaildomain", "addr1", "addr2"]):
            if col in cols:
                opts = sorted(df[col].dropna().astype(str).unique(), key=lambda x: (len(x), x)) + (["(missing)"] if df[col].isna().any() else [])
                f[col] = c[i].multiselect(col, opts, f.get(col, []), help=helps[col] + " - masked IEEE-CIS attribute, not a customer identifier")
        with st.popover("Which business fields exist?"):
            st.dataframe(pd.DataFrame(data_v2.FIELD_AVAILABILITY, columns=["requested field", "status", "dataset field", "note"]), hide_index=True)
        if S.MODE == "evaluation" and "isFraud" in cols:
            f["isFraud"] = st.radio("Evaluation label (evaluation mode)", ["any", "0", "1"], ["any", "0", "1"].index(f.get("isFraud", "any")), horizontal=True)
        if st.button("Reset filters", type="secondary"):
            st.session_state["filters"] = filters.defaults(df)
            st.rerun()
    m = filters.mask(df, f)
    a, b = st.columns([5, 1])
    with a:
        ui.chips(filters.chips(df, f))
    b.markdown(f"**{int(m.sum()):,}** of {len(df):,} rows")
    if not m.any():   # fields exist, but nothing matches: say so and stop (distinct from 'field not in dataset')
        st.info("**No matching records.** Every filter field exists in the data, but no transaction satisfies all active filters. "
                "Widen or reset the filters.", icon="🔍")
        st.stop()
    return df[m]


def label_scope_note(filtered: bool) -> None:
    if filtered and S.MODE != "evaluation":
        ui.note("Label-based metrics (precision, recall, confusion matrix) are shown for the <b>full test split only</b>. "
                "They do not follow filters in investigation mode, so no label can be inferred from a small filtered group.")


# ----------------------------------------------------------------- graceful failures (shared by every page)
REQUIRED_METRICS = ("prevalence", "TP", "FP", "TN", "FN", "precision", "recall", "f1")  # from evaluation["metrics"]
REQUIRED_RANKING = ("average_precision", "roc_auc")                                   # from evaluation["ranking"]


def log_issue(kind: str, detail) -> str:
    """Append a redacted diagnostic line to outputs/runtime/diagnostics.jsonl; return a short reference for the UI."""
    import datetime as _dt
    import json as _json
    import secrets as _secrets
    import traceback as _tb
    from bfi9 import exporters
    ref = _secrets.token_hex(4)
    text = f"{type(detail).__name__}: {detail}" if isinstance(detail, BaseException) else str(detail)
    rec = {"utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "ref": ref, "kind": kind,
           "detail": exporters.redact(text)[:500],
           "trace": exporters.redact("".join(_tb.format_exception(detail)))[-2000:] if isinstance(detail, BaseException) else ""}
    try:
        S.RUNTIME.mkdir(parents=True, exist_ok=True)
        with open(S.RUNTIME / "diagnostics.jsonl", "a") as f:
            f.write(_json.dumps(rec) + "\n")
    except OSError:
        pass  # logging must never break the page
    return ref


def checked_evaluation(split="test", group="all", model="A"):
    """(evaluation, None) when every required metric is present, else (None, user-facing reason).

    Evaluation metrics come only from evaluation['metrics'] and ranking metrics only from evaluation['ranking'];
    dataset/split counts (rows, alerts, alert rate, threshold) are computed by the pages and never validated here."""
    ev = evaluation(split, group, model)
    m, rk = ev.get("metrics") or {}, ev.get("ranking") or {}
    miss = [k for k in REQUIRED_METRICS if m.get(k) is None] + [f"ranking.{k}" for k in REQUIRED_RANKING if rk.get(k) is None]
    if ev.get("status") == "measured" and not miss:
        return ev, None
    why = ev.get("error") or ("missing " + ", ".join(miss))
    ref = log_issue("evaluation_unavailable", f"split={split} group={group} model={model} status={ev.get('status')} {why}")
    return None, f"The Phase 8 evaluation did not return a complete result (status '{ev.get('status')}', {why[:160]}). Reference {ref}."
