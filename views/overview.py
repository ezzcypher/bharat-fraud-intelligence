"""1. Executive Overview - verified KPIs, core charts and an evidence-cited narrative."""
import datetime as dt

import streamlit as st

from bfi9 import charts, filters, phase8, ui
from bfi9 import settings as S

from . import common


def render():
    ui.header("Executive Overview", "BFI v2 · IEEE-CIS · frozen Phase 4 model A · from raw transactions to explainable fraud decisions")
    if not common.require_v2():
        return
    df = common.frame()
    d = common.filter_bar(df)
    fz = S.frozen()
    ev, problem = common.checked_evaluation("test")  # metrics <- ev["metrics"], ranking <- ev["ranking"] only
    m, rk = (ev or {}).get("metrics", {}), (ev or {}).get("ranking", {})
    rel = phase8.reliance()
    st.caption(f"Rendered {dt.datetime.now():%Y-%m-%d %H:%M} · data: Phase 4 stored scores (read-only) · model status: frozen, not retrained · Phase 8 API {common.status().get('api_version')}")

    # Step 1: KPIs that follow filters (no labels needed).
    c = st.columns(5)
    with c[0]: ui.kpi("Transactions in view", len(d), "Validation + test transactions after filters.", "Phase 4 prediction files", "filtered view")
    alerts = int((d["decision"] != "no alert").sum())
    with c[1]: ui.kpi("Predicted alerts", alerts, "score ≥ frozen threshold. A prediction, not a confirmed fraud.", "Phase 4 scores × Phase 4 threshold", "filtered view")
    with c[2]: ui.kpi("Alert rate", alerts / len(d) if len(d) else None, "alerts / transactions", "derived", "filtered view", "derived", "{:.2%}")
    with c[3]: ui.kpi("Frozen threshold", fz["threshold"], fz["threshold_source"], "BFI_v2_model_config.json", "all views", "measured", "{:.4f}")
    with c[4]:
        mi = d["n_missing_inputs"].mean() / fz["n_features"] if "n_missing_inputs" in d and len(d) else None
        ui.kpi("Missing model inputs", mi, "Mean share of the 431 inputs that are empty per transaction.", "Phase 8 feature store", "filtered view", "measured", "{:.1%}")

    # Step 2: label-based KPIs - full test split (published Phase 7 values recomputed via Phase 8).
    st.markdown("##### Model performance · test split (spent holdout), full split")
    if problem:
        ui.unavailable("Model performance KPIs", problem)
    else:
        c = st.columns(4) + st.columns(4)
        scope = "test split, model A, frozen threshold"
        src = "Phase 4 predictions → Phase 7 metrics_engine (via Phase 8)"
        items = [("Label prevalence", m.get("prevalence"), "{:.2%}", "Share of chargeback-derived positive labels (not confirmed crime)."),
                 ("True positives", m.get("TP"), "{:,}", "Alert AND positive label."), ("False positives", m.get("FP"), "{:,}", "Alert AND negative label."),
                 ("False negatives", m.get("FN"), "{:,}", "No alert AND positive label."), ("Precision", m.get("precision"), "{:.3f}", "TP / (TP + FP)"),
                 ("Recall", m.get("recall"), "{:.3f}", "TP / (TP + FN)"), ("Average precision", rk.get("average_precision"), "{:.3f}", "Area under the PR curve (ranking)."),
                 ("ROC-AUC", rk.get("roc_auc"), "{:.3f}", "P(random positive outranks random negative).")]
        for col, (lab, val, fmt, defi) in zip(c, items):
            with col: ui.kpi(lab, val, defi, src, scope, "measured", fmt, foot="test · full split")
        common.label_scope_note(filters.is_filtered(df, common.filter_state(df)))
        ui.note(f"F1 {m.get('f1', float('nan')):.3f} · scores are <b>not calibrated probabilities</b> · "
                f"<b>{rel['share']:.2%}</b> of total mean |SHAP| sits on C/D/M/V/dist features whose decision-time availability is unverified.", warn=True)

    # Step 3: charts.
    a, b = st.columns(2)
    a.plotly_chart(charts.score_hist(d["score"], fz["threshold"], "Model score distribution (filtered view)"), width="stretch")
    b.plotly_chart(charts.band_bar(d["risk_band"].value_counts(), "Risk-band distribution (filtered view)"), width="stretch")
    cv = common.curves("test")
    a, b, c3 = st.columns(3)
    a.plotly_chart(charts.curve(cv["pr_recall"], cv["pr_precision"], "model A", "Precision–recall · test", "recall", "precision",
                                ref=([0, 1], [cv["prevalence"]] * 2), ref_name=f"no-skill (π={cv['prevalence']:.3f})"), width="stretch")
    b.plotly_chart(charts.curve(cv["roc_fpr"], cv["roc_tpr"], "model A", "ROC · test", "false-positive rate", "true-positive rate", ref=([0, 1], [0, 1])), width="stretch")
    if m:
        c3.plotly_chart(charts.confusion(m, "Confusion matrix · test"), width="stretch")

    # Step 4: evidence-cited narrative (deterministic; every number above).
    if problem:
        return
    st.markdown("##### What the evidence says")
    fp_share = m["FP"] / (m["TP"] + m["FP"]) if m else None
    st.markdown(f"""
- **Working:** on the spent test split the frozen model ranks well (ROC-AUC {rk.get('roc_auc', 0):.3f}, AP {rk.get('average_precision', 0):.3f} vs no-skill {m.get('prevalence', 0):.3f}).
- **Main error types:** {m.get('FN', 0):,} positive labels missed (FNR {m.get('fnr', 0):.1%}) and {m.get('FP', 0):,} false alerts ({(fp_share or 0):.1%} of alerts).
- **Data quality:** inputs are on average {(mi or 0):.1%} empty per transaction in this view; Phase 8 reproduced the stored scores before explanations were enabled.
- **Needs human attention:** {int((d['risk_band'] == 'Critical').sum()):,} Critical-band transactions in view (provisional bands).
- **Limits interpretation:** labels are chargeback-derived; scores uncalibrated; {rel['share']:.1%} reliance on unverified-availability features; test set already used.
- **Investigate next:** decision-time availability of C/D/M/V features; calibration on fresh data; real review costs.""")
