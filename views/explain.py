"""10. Feature Explainability - Phase 5 global importance, availability audit, local vs global."""
import pandas as pd
import streamlit as st

from bfi9 import charts, exporters, phase8, ui

from . import common


def render():
    ui.header("Feature Explainability", "Phase 5 TreeSHAP artefacts · log-odds scale · model behaviour, not causation")
    if not common.require_v2():
        return
    g, av, rel = phase8.global_importance(), phase8.availability_audit(), phase8.reliance()
    ui.note(f"<b>{rel['share']:.2%}</b> of total mean |SHAP| sits on the {', '.join(rel['families'])} families, whose availability at decision time "
            "is <b>unverified</b>. If those inputs are only known after the transaction, real-world performance could be lower than measured.", warn=True)
    n = st.slider("Top features", 5, 40, 15)
    top = g.sort_values("mean_abs_shap", ascending=False).head(n)
    a, b = st.columns([3, 2])
    a.plotly_chart(charts.hbar(top["feature"], top["mean_abs_shap"], f"Top {n} features by mean |SHAP|", "mean |SHAP| (log-odds)"), width="stretch")
    fam = g.groupby("family")["mean_abs_shap"].sum().sort_values(ascending=False)
    b.plotly_chart(charts.hbar(fam.index, fam.values / fam.sum(), "Share of mean |SHAP| by family", "share", text_fmt="{:.1%}"), width="stretch")

    st.markdown("##### Feature-availability audit (Phase 5)")
    m = g.merge(av[["feature", "likely_available_at_decision", "timing_known", "confidence"]], on="feature", how="left")
    share = (m.groupby(m["likely_available_at_decision"].astype(str))["mean_abs_shap"].sum() / m["mean_abs_shap"].sum()).sort_values(ascending=False)
    a, b = st.columns([2, 3])
    a.plotly_chart(charts.hbar(share.index, share.values, "Importance share by availability status", "share of mean |SHAP|", text_fmt="{:.1%}"), width="stretch")
    b.dataframe(av, hide_index=True, width="stretch", height=360)
    st.download_button("Download availability × importance (CSV)", exporters.csv_bytes(m), "feature_importance_availability.csv", "text/csv")

    st.markdown("##### Local vs global for one transaction")
    tid = st.session_state.get("selected_tid") or int(common.frame()["score"].idxmax())
    e = phase8.explain_full(int(tid))
    if e.get("status") != "available":
        ui.unavailable(f"Explanation for {tid}", e.get("reason") or e.get("error") or e.get("status"))
        return
    loc = pd.DataFrame([{"feature": x["feature"], "local_contribution": x["contribution_log_odds"]} for x in e["top_increasing"] + e["top_decreasing"]])
    loc = loc.merge(g[["feature", "shap_rank", "mean_abs_shap"]], on="feature", how="left")
    st.dataframe(loc.rename(columns={"shap_rank": "global_rank"}), hide_index=True, width="stretch")
    st.caption(f"Transaction {tid}: features that matter locally can rank low globally (and vice versa). Correlated features share credit, so single contributions can mislead.")
