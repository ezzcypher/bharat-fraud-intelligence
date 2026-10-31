"""8. Cost & Decision Simulator - Phase 7 cost engine via Phase 8; every value labelled by evidence class."""
import pandas as pd
import streamlit as st

from bfi9 import charts, exporters, phase8, ui

from . import common

BASE = "illustrative_baseline"
KEYS = ("c_fp", "c_fn", "c_review", "review_rate")


def render():
    ui.header("Cost & Decision Simulator", "Phase 7 formula · Total = FP·C_FP + FN·C_FN + N_reviewed·C_review + TP_stopped·C_intervention")
    if not common.require_v2():
        return
    sc = {s["name"]: s for s in phase8.cost_scenarios()}
    base = sc[BASE]
    if st.button("Reset to baseline"):
        for k in KEYS:
            st.session_state.pop(f"cost_{k}", None)
    c = st.columns(4)
    vals = {"c_fp": c[0].slider("C_FP · cost per false positive (CU)", 0.0, 50.0, float(base["c_fp"]), 0.5, key="cost_c_fp"),
            "c_fn": c[1].slider("C_FN · cost per missed fraud (CU)", 0.0, 1000.0, float(base["c_fn"]), 5.0, key="cost_c_fn"),
            "c_review": c[2].slider("C_review · cost per review (CU)", 0.0, 20.0, float(base["c_review"]), 0.5, key="cost_c_review"),
            "review_rate": c[3].slider("Share of alerts reviewed", 0.0, 1.0, float(base["review_rate"]), 0.05, key="cost_review_rate")}
    ov = {k: v for k, v in vals.items() if abs(v - float(base[k])) > 1e-12}
    r = phase8.cost_scenario(BASE, **ov)
    if r.get("status") != "modeled":
        ui.unavailable("Cost scenario", r.get("error") or str(r))
        return
    ev = "illustrative" if not ov else "assumed"
    ui.note(f"<b>{'Baseline illustrative scenario' if not ov else 'User-adjusted assumptions'}</b> · unit {r['unit']} (abstract cost units, not currency). "
            "Counts are measured on the test split; costs are modelled from assumptions, never measured business losses.", warn=bool(ov))
    mc, mo = r["measured_counts"], r["modeled_costs"]
    c = st.columns(5)
    with c[0]: ui.kpi("True positives stopped", mc["frauds_stopped"], "Alerted, reviewed, positive label", "Phase 7 policy_outcomes", "test split")
    with c[1]: ui.kpi("False positives actioned", mc["legit_actioned"], "Alerted, reviewed, negative label", "Phase 7 policy_outcomes", "test split")
    with c[2]: ui.kpi("Missed (FN + unreviewed)", mc["frauds_missed"], "Positive labels not stopped", "Phase 7 policy_outcomes", "test split")
    with c[3]: ui.kpi("Reviews", mc["reviewed"], "Alerts sent to review", "Phase 7 policy_outcomes", "test split")
    with c[4]: ui.kpi("Total cost", mo["total_cost"], "Phase 7 cost_from_outcomes", "Phase 7 cost_engine", "test split", ev, "{:,.0f}", foot=r["unit"])
    parts = pd.Series({"False positives": mo["fp_cost"], "Missed fraud": mo["fn_cost"], "Reviews": mo["review_cost"], "Interventions": mo["intervention_cost"]})
    a, b = st.columns(2)
    a.plotly_chart(charts.hbar(parts.index, parts.values, "Cost by category", r["unit"], text_fmt="{:,.0f}"), width="stretch")
    rows = []
    for name in sc:
        s = phase8.cost_scenario(name)
        rows.append({"scenario": name, "status": s.get("assumption_status"), **{k: s["inputs"][k] for k in ("c_fp", "c_fn", "c_review")}, "total_cost": s["modeled_costs"]["total_cost"]})
    rows.append({"scenario": "current sliders", "status": ev, **{k: vals[k] for k in ("c_fp", "c_fn", "c_review")}, "total_cost": mo["total_cost"]})
    comp = pd.DataFrame(rows)
    b.plotly_chart(charts.bar(comp["scenario"], comp["total_cost"], "Scenario comparison (total cost, CU)", "scenario", "CU"), width="stretch")
    st.dataframe(comp, hide_index=True, width="stretch")

    st.markdown("##### Sensitivity (one-way, Phase 7 sensitivity_analysis)")
    a, b = st.columns(2)
    for col, (p, grid) in zip((a, b), (("c_fn", [10, 25, 50, 100, 200, 400, 800]), ("c_fp", [0, 1, 2, 5, 10, 20, 40]))):
        ow = phase8.cost_one_way(p, grid, BASE)
        y = "total_cost" if "total_cost" in ow else ow.columns[-1]
        col.plotly_chart(charts.lines(ow.rename(columns={"value": p}), p, [y], f"Total cost vs {p} (illustrative)", "CU"), width="stretch")
    be = phase8.break_even(BASE)
    st.markdown(f"- **Break-even C_FN** vs no screening: **{be['break_even_c_fn']:.2f} CU** (other costs at baseline).\n"
                f"- **Implied C_FN/C_FP** if scores were calibrated: {be['implied_c_fn_over_c_fp_if_calibrated']:.2f}. *Calibration is not established.*")
    st.dataframe(phase8.p7_output("cost_scenarios.csv"), hide_index=True, width="stretch")
    st.caption("Above: Phase 7 released cost_scenarios.csv (read-only, unchanged).")
    md = exporters.markdown_report("Cost scenario summary", [("Scenarios", exporters.table_md(comp)), ("Break-even", str(be))],
                                   ["Phase 7 cost_engine via Phase 8 cost_adapter"], "test split, model A, frozen threshold; illustrative units")
    st.download_button("Download scenario summary (Markdown)", md.encode(), "cost_scenarios_summary.md", "text/markdown")
