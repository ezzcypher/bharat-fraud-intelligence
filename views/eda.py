"""6. EDA & Data Quality - BFI v1 Raw / Cleaned-Sorted / Compare, and the BFI v2 raw profile (Stage 1 audit)."""
import pandas as pd
import streamlit as st

from bfi9 import charts, data_v1, exporters, quality, ui
from bfi9 import settings as S

CLEANING = pd.DataFrame([
    {"transformation": "loan_type missing → 'No Loan'", "what_changed": "377,134 structural nulls filled", "why": "loan_type is blank exactly when has_loan = 0",
     "affected": "rows with has_loan = 0; column loan_type", "historical": "yes (notebook cell 15)", "safe_to_reproduce": "yes", "leakage_risk": "none (uses has_loan only)",
     "valid_for_future": "yes, if has_loan is known at decision time"},
    {"transformation": "8 engineered columns", "what_changed": "hour_sin/cos, is_weekend, balance_txn_ratio, 2 outlier flags, 2 log transforms",
     "why": "cyclic time, skew reduction, outlier indicators", "affected": "new columns only", "historical": "yes (notebook cell 21)", "safe_to_reproduce": "yes",
     "leakage_risk": "outlier flags use IQR bounds computed on the FULL dataset (incl. later test rows)", "valid_for_future": "only with bounds fixed on training data"},
    {"transformation": "sort by transaction_date", "what_changed": "row order", "why": "chronological splits", "affected": "row order only",
     "historical": "file is date-sorted (verified Stage 1)", "safe_to_reproduce": "yes", "leakage_risk": "none", "valid_for_future": "yes"}])


@st.cache_resource(show_spinner="Loading BFI v1 data (550,000 rows)…")
def _v1(name):
    return data_v1.get(name)


V1_FILTERS = ["transaction_type", "channel", "state", "account_type", "merchant_category"]   # real BFI v1 columns


def _v1_filters(raw: pd.DataFrame) -> dict:
    """Filters on fields that genuinely exist in BFI v1; applied identically to raw and cleaned tables."""
    out = {}
    with st.expander("BFI v1 filters (transaction type, channel, geography, account)", expanded=False):
        cols = st.columns(len(V1_FILTERS))
        for c, name in zip(cols, V1_FILTERS):
            if name in raw:
                out[name] = c.multiselect(name.replace("_", " "), sorted(raw[name].dropna().astype(str).unique()), key=f"v1f_{name}")
            else:
                c.caption(f"{name}: not in dataset")
    act = {k: v for k, v in out.items() if v}
    ui.chips([f"{k}: {', '.join(v)}" for k, v in act.items()])
    return act


def _apply(df: pd.DataFrame, flt: dict) -> pd.DataFrame:
    for k, v in flt.items():
        if k in df:
            df = df[df[k].astype(str).isin(v)]
    if df.empty:
        st.info("**No matching records** for these BFI v1 filters (the fields exist). Widen or clear the filters.", icon="🔍")
        st.stop()
    return df


def _profile(df: pd.DataFrame, title: str, n: int):
    k = quality.kpis(df, data_v1.LABEL, data_v1.ID)
    c = st.columns(6)
    for col, (lab, key, fmt) in zip(c, [("Rows", "rows", "{:,}"), ("Columns", "columns", "{:,}"), ("Duplicate rows", "duplicate_rows", "{:,}"),
                                        ("Duplicate IDs", "duplicate_ids", "{:,}"), ("Missing cells", "missing_pct", "{:.3f}%"), ("Label prevalence", "prevalence_pct", "{:.3f}%")]):
        with col: ui.kpi(lab, k.get(key), f"{lab} in {title}", title, "BFI v1 (Indian banking)", "measured", fmt)
    smp = data_v1.sample(df, n)
    a, b = st.columns(2)
    mb = quality.missing_by_column(df).head(15)
    a.plotly_chart(charts.hbar(mb["column"], mb["missing_pct"], "Missing values by column (%)", "% missing", text_fmt="{:.2f}"), width="stretch")
    vc = df[data_v1.LABEL].value_counts().sort_index()
    b.plotly_chart(charts.bar([f"is_fraud={i}" for i in vc.index], vc.values, "Class distribution (v1 label, generation undocumented)", "", "rows"), width="stretch")
    num = [c for c in df.select_dtypes("number").columns if c != data_v1.LABEL]
    cat = [c for c in df.columns if c not in num and c not in (data_v1.LABEL, data_v1.ID, "customer_id", data_v1.DATE, "transaction_time")]
    a, b = st.columns(2)
    x = a.selectbox("Numeric column", num, key=f"num_{title}")
    kind = a.segmented_control("Chart", ["histogram", "box", "violin"], default="histogram", key=f"kind_{title}")
    if kind == "histogram":
        a.plotly_chart(charts.grouped_hist(smp, x, data_v1.LABEL, f"{x} by label (sample {len(smp):,})", log_y=True), width="stretch")
    else:
        a.plotly_chart(charts.box(smp, x, data_v1.LABEL, f"{x} by label (sample {len(smp):,})", kind or "box"), width="stretch")
    if cat:
        y = b.selectbox("Categorical column", cat, key=f"cat_{title}")
        vc = df[y].astype("object").fillna("(missing)").value_counts().head(12)
        b.plotly_chart(charts.hbar(vc.index.astype(str), vc.values, f"{y} frequency (top 12)", "rows", text_fmt="{:,.0f}"), width="stretch")
    cols = st.multiselect("Correlation columns", num, default=num[:8], key=f"corr_{title}")
    if len(cols) >= 2:
        st.plotly_chart(charts.heatmap(quality.correlations(smp, cols + [data_v1.LABEL]), "Pearson correlation (sample) · association ≠ causation"), width="stretch")
    st.markdown(f"**Outliers** · {quality.OUTLIER_RULE}")
    st.dataframe(quality.outliers(df, label=data_v1.LABEL), hide_index=True, width="stretch")
    st.download_button(f"Download {title} quality summary (CSV)", exporters.csv_bytes(pd.DataFrame([k])), f"quality_{title}.csv", "text/csv", key=f"dl_{title}")


def render():
    ui.header("EDA & Data Quality", "Raw vs cleaned data · each project version analysed on its own")
    ds = st.segmented_control("Dataset", ["BFI v1 · Indian banking", "BFI v2 · IEEE-CIS raw profile"], default="BFI v1 · Indian banking")
    if ds and ds.startswith("BFI v2"):
        p = S.AUDIT_DIR / "column_profiles.csv"
        if not p.is_file():
            ui.unavailable("IEEE-CIS profile", "Run the Stage 1 audit first.")
            return
        prof = pd.read_csv(p)
        prof = prof[prof["dataset"].isin(["train_transaction.csv", "train_identity.csv"])]
        ui.note("IEEE-CIS has <b>no cleaned/sorted version</b>: the model used the raw columns directly (Phase 4). "
                "This view is the full-file column profile computed in the Stage 1 audit (590,540 + 144,233 rows).")
        f = st.selectbox("File", ["train_transaction.csv", "train_identity.csv"])
        q = prof[prof["dataset"] == f].sort_values("missing_percentage", ascending=False)
        st.plotly_chart(charts.hbar(q["column_name"].head(25), q["missing_percentage"].head(25), "Most-missing columns (%)", "% missing", text_fmt="{:.1f}"), width="stretch")
        st.dataframe(q, hide_index=True, width="stretch")
        return
    st_ = data_v1.status()
    if not (st_["raw"] or st_["cleaned"]):
        ui.unavailable("BFI v1 data", "Neither archive (2).zip nor the cleaned CSV is present.")
        return
    view = st.segmented_control("View", ["Raw Data", "Cleaned / Sorted Data", "Compare Both"], default="Compare Both")
    n = st.select_slider("Plot sample size", [5000, 20000, 50000, 100000], 20000, help="Charts use a seeded random sample; KPIs use all rows")
    flt = _v1_filters(_v1("raw"))
    if view == "Raw Data":
        _profile(_apply(_v1("raw"), flt), "raw", n)
    elif view == "Cleaned / Sorted Data":
        _profile(_apply(_v1("cleaned"), flt), "cleaned", n)
    else:
        r, c = _apply(_v1("raw"), flt), _apply(_v1("cleaned"), flt)
        kr, kc = quality.kpis(r, data_v1.LABEL, data_v1.ID), quality.kpis(c, data_v1.LABEL, data_v1.ID)
        t = pd.DataFrame({"raw": kr, "cleaned/sorted": kc})
        t["difference"] = pd.to_numeric(t["cleaned/sorted"], errors="coerce") - pd.to_numeric(t["raw"], errors="coerce")
        a, b = st.columns([2, 3])
        a.dataframe(t, width="stretch")
        sc = quality.schema_compare(r, c)
        b.markdown(f"- **Rows removed by cleaning:** {kr['rows'] - kc['rows']:,}\n- **Columns added:** {', '.join(sc['only_in_second']) or 'none'}\n"
                   f"- **Columns removed:** {', '.join(sc['only_in_first']) or 'none'}\n- **dtype changes:** {sc['dtype_changes'] or 'none'}")
        ch = quality.column_changes(r, c)
        st.dataframe(ch, hide_index=True, width="stretch")
        st.plotly_chart(charts.grouped_bar(ch, "column", ["missing_raw", "missing_clean"], "Missing values before vs after cleaning", "missing cells"), width="stretch")
        st.markdown("##### Cleaning transparency")
        st.dataframe(CLEANING, hide_index=True, width="stretch")
        st.download_button("Download before/after table (CSV)", exporters.csv_bytes(ch), "v1_raw_vs_cleaned.csv", "text/csv")
