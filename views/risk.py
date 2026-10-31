"""2. Fraud & Risk Analytics - alert patterns over real fields; label analyses only in evaluation mode."""
import pandas as pd
import streamlit as st
from scipy import stats

from bfi9 import charts, phase8, ui
from bfi9 import settings as S

from . import common


def _rate_table(d: pd.DataFrame, col: str) -> pd.DataFrame:
    g = d.assign(alert=d["decision"] != "no alert", **{col: d[col].astype("object").fillna("(missing)")}).groupby(col)
    t = pd.DataFrame({"transactions": g.size(), "alerts": g["alert"].sum(), "mean_score": g["score"].mean()})
    t["alert_rate"] = t["alerts"] / t["transactions"]
    t["small_group"] = t["transactions"] < S.MIN_GROUP_N
    return t.sort_values("transactions", ascending=False).head(15).reset_index()


def render():
    ui.header("Fraud & Risk Analytics", "Where alerts concentrate · predicted positives are not confirmed fraud")
    if not common.require_v2():
        return
    d = common.filter_bar(common.frame())
    if d.empty:
        ui.unavailable("Analysis", "No rows match the filters.")
        return
    cats = [c for c in ("ProductCD", "card4", "card6", "P_emaildomain", "identity_present", "risk_band") if c in d]
    col = st.segmented_control("Break down by", cats, default=cats[0], help="Masked IEEE-CIS attributes; they are not customers or payment methods")
    t = _rate_table(d, col)
    a, b = st.columns([3, 2])
    a.plotly_chart(charts.bar(t[col].astype(str), t["alert_rate"], f"Alert rate by {col} (filtered view)", col, "alert rate"), width="stretch")
    with b:
        st.dataframe(t.style.format({"alert_rate": "{:.2%}", "mean_score": "{:.4f}"}), hide_index=True, width="stretch", height=330)
        if t["small_group"].any():
            ui.note(f"Groups under {S.MIN_GROUP_N} transactions are flagged <b>small_group</b>: their rates are statistically unreliable.", warn=True)

    a, b = st.columns(2)
    smp = d.sample(min(len(d), 20000), random_state=0)
    a.plotly_chart(charts.box(smp.assign(**{col: smp[col].astype("object").fillna("(missing)").astype(str)}), "score", col,
                              f"Model score by {col} (sample ≤ 20k, seed 0)"), width="stretch")
    if "n_missing_inputs" in d:
        mb = d.assign(bin=pd.cut(d["n_missing_inputs"], 10)).groupby("bin", observed=True)["score"].agg(["mean", "size"]).reset_index()
        b.plotly_chart(charts.bar(mb["bin"].astype(str), mb["mean"], "Mean score by number of missing inputs", "missing inputs (of 431)", "mean score"), width="stretch")

    st.markdown("##### Association with the model score")
    num = [c for c in ("amount_usd", "n_missing_inputs", "day") if c in d]
    x = st.selectbox("Numeric field", num)
    ok = d[[x, "score"]].dropna()
    if len(ok) >= 30:
        rho, p = stats.spearmanr(ok[x], ok["score"])
        st.markdown(f"Spearman ρ = **{rho:.3f}** (n = {len(ok):,}, p = {p:.2g}). Association with the *score* only; not causation. "
                    "p-values assume independent rows, which clustered transactions violate.")
    else:
        ui.unavailable("Association", "fewer than 30 non-missing rows.")

    st.markdown("##### Label-based breakdowns")
    if S.MODE != "evaluation":
        ui.restricted("Score-by-label distributions, FP/FN breakdowns and label prevalence by group need evaluation mode (set at launch). "
                      "Full-split metrics are on Executive Overview and Model Performance.")
        return
    full = phase8.predictions()
    a, b = st.columns(2)
    sub = d.join(full[["isFraud"]], how="left", rsuffix="_") if "isFraud" not in d else d
    a.plotly_chart(charts.grouped_hist(sub, "score", "isFraud", "Score by evaluation label (filtered)", log_y=True), width="stretch")
    b.dataframe(phase8.error_patterns("test"), hide_index=True, width="stretch")
    sm = phase8.subset_metrics(d.index)
    st.json(sm) if sm["status"] != "measured" else st.dataframe(pd.DataFrame([sm["metrics"]]), hide_index=True)
