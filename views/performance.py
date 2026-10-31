"""5. Model Performance - Phase 7 engine via Phase 8 (frozen view) + validation-only threshold sandbox."""
import json

import pandas as pd
import streamlit as st

from bfi9 import charts, exporters, phase8, ui
from bfi9 import settings as S

from . import common

DEFS = {"precision": "TP/(TP+FP)", "recall": "TP/(TP+FN)", "specificity": "TN/(TN+FP)", "f1": "2PR/(P+R)", "balanced_accuracy": "(TPR+TNR)/2",
        "accuracy": "(TP+TN)/N", "fpr": "FP/(FP+TN)", "fnr": "FN/(FN+TP)", "alert_rate": "(TP+FP)/N", "prevalence": "(TP+FN)/N"}


def render():
    ui.header("Model Performance", "Frozen Phase 4 model · Phase 7 metrics engine (reused, not re-implemented)")
    if not common.require_v2():
        return
    c = st.columns(3)
    split = c[0].segmented_control("Split", ["test", "val"], default="test", help="test = spent holdout; val = used to pick the threshold (optimistic)")
    group = c[1].segmented_control("User group", ["all", "new_user", "seen_user"], default="all", help="Phase 4 groups (seen_A)")
    model = c[2].segmented_control("Model", ["A", "B"], default="A", help="B: refit on train+val, test only, approximate at A's threshold")
    ev, _problem = common.checked_evaluation(split or "test", group or "all", model or "A")
    if _problem:
        ui.unavailable("Model performance", _problem)
        return
    if ev.get("status") != "measured":
        ui.unavailable("Evaluation", ev.get("error") or ev.get("reason") or str(ev))
        return
    m, rk = ev["metrics"], ev["ranking"]
    for cv in ev.get("caveats", []):
        st.caption("• " + cv)
    rows = [{"metric": k, "value": m.get(k), "formula": f, "wilson_95": (lambda w: f"{w[0]:.4f} – {w[1]:.4f}" if w else "—")(ev.get("wilson_95", {}).get(k))} for k, f in DEFS.items()]
    rows += [{"metric": "average_precision", "value": rk.get("average_precision"), "formula": "Σ(Rₖ−Rₖ₋₁)·Pₖ (sklearn convention)", "wilson_95": "—"},
             {"metric": "roc_auc", "value": rk.get("roc_auc"), "formula": "P(s₊ > s₋)", "wilson_95": "—"}]
    t = pd.DataFrame(rows)
    a, b = st.columns([3, 2])
    a.dataframe(t, hide_index=True, width="stretch", column_config={"value": st.column_config.NumberColumn(format="%.4f")})
    b.plotly_chart(charts.confusion(m, f"Confusion matrix · {split} · {group} · model {model}"), width="stretch")
    if (model or "A") == "A" and (group or "all") == "all":
        cv = common.curves(split or "test")
        a, b = st.columns(2)
        a.plotly_chart(charts.curve(cv["pr_recall"], cv["pr_precision"], "model A", f"Precision–recall · {split}", "recall", "precision",
                                    ref=([0, 1], [cv["prevalence"]] * 2), ref_name="no-skill"), width="stretch")
        b.plotly_chart(charts.curve(cv["roc_fpr"], cv["roc_tpr"], "model A", f"ROC · {split}", "FPR", "TPR", ref=([0, 1], [0, 1])), width="stretch")
    p7m = json.loads((S.P7_DIR / "outputs" / "metrics.json").read_text())
    ui.note(f"<b>Calibration status:</b> not established. Phase 7 Brier (test, A) = {p7m.get('brier', {}).get('test_A', 'n/a')}; "
            "scores rank transactions but are not probabilities. Wilson intervals assume independent transactions.", warn=True)
    st.download_button("Download performance summary (CSV)", exporters.csv_bytes(t), f"performance_{split}_{group}_{model}.csv", "text/csv")

    st.markdown("##### Threshold sandbox · exploratory · validation split only")
    thr = st.slider("Hypothetical threshold", 0.01, 0.99, float(round(S.frozen()["threshold"], 2)), 0.01,
                    help="Sensitivity analysis on validation. The frozen threshold and test results never change.")
    sb = phase8.sandbox(thr)
    if sb["status"] == "exploratory":
        h, f = sb["hypothetical"], sb["frozen"]
        cmp = pd.DataFrame({"frozen (val)": f, f"hypothetical {thr:.2f} (val)": h}).reindex(["TP", "FP", "FN", "TN", "alerts", "precision", "recall", "f1", "alert_rate"])
        st.dataframe(cmp, width="stretch")
        for cv in sb["caveats"]:
            st.caption("• " + cv)
