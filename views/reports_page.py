"""7. Report Comparison - First/Baseline report vs EDA report (v1), parsed from the real artefacts."""
import pandas as pd
import streamlit as st

from bfi9 import charts, data_v1, exporters, quality, reports, ui


def render():
    ui.header("Report Comparison", "First / Baseline report (Phase 2 .docx) vs EDA report (notebook outputs) · BFI v1")
    F, E = reports.first_report(), reports.eda_report()
    c = st.columns(2)
    c[0].markdown(f"**First / Baseline:** `{F.get('path')}` · {F.get('status')} · sha256 {F.get('sha256_12', '—')}…")
    c[1].markdown(f"**EDA:** `{E.get('path')}` · {E.get('status')} · sha256 {E.get('sha256_12', '—')}… · _{E.get('derived', '')}_")
    for w in reports.warnings():
        ui.note(w, warn=True)
    view = st.segmented_control("View", ["First / Baseline Report", "EDA Report", "Side-by-Side Comparison"], default="Side-by-Side Comparison")
    if view == "First / Baseline Report":
        if F["status"] != "ok":
            return ui.unavailable("First report", F["path"])
        st.dataframe(F["summary_table"], hide_index=True, width="stretch")
        for s in F["sections"]:
            with st.expander(s["heading"]):
                st.write(s["text"][:4000])
        return
    if view == "EDA Report":
        if E["status"] != "ok":
            return ui.unavailable("EDA report", E["path"])
        a, b = st.columns(2)
        a.markdown("**Phase 1 audit summary (notebook output)**"); a.code(E["phase1_summary"][:2000] or "not found")
        b.markdown("**Phase 3 technical summary (notebook output)**"); b.code(E["phase3_summary"][:2500] or "not found")
        st.markdown("**IQR outlier analysis (notebook output)**"); st.code(E["outlier_table"][:2000] or "not found")
        st.dataframe(pd.DataFrame(E["cells"])[["cell", "type", "first_line", "images"]], hide_index=True, width="stretch")
        return
    recomputed = None
    if st.toggle("Recompute from the current CSVs (loads 550k rows)", False):
        r, cl = data_v1.raw(), data_v1.cleaned()
        kr, kc = quality.kpis(r, data_v1.LABEL, data_v1.ID), quality.kpis(cl, data_v1.LABEL, data_v1.ID)
        recomputed = {"rows": kr["rows"], "columns_raw": kr["columns"], "columns": kc["columns"], "positives": kr.get("positives"),
                      "prevalence_pct": round(kr.get("prevalence_pct"), 3), "duplicate_rows": kr["duplicate_rows"], "duplicate_ids": kr.get("duplicate_ids"),
                      "missing_loan_type": int(r["loan_type"].isna().sum()) if "loan_type" in r else None}
    cmp = reports.compare(recomputed)
    st.dataframe(cmp, hide_index=True, width="stretch",
                 column_config={"pct_change": st.column_config.NumberColumn(format="%.2f%%")})
    st.caption("pct_change is shown only when both values are numeric, comparable and the first value is non-zero. "
               "'recomputed_now' is calculated from today's files and kept separate from historical report values.")
    num = cmp[cmp["status"] == "unchanged"].copy()
    num = num[pd.to_numeric(num["first_report"], errors="coerce").notna()]
    if not num.empty:
        num["first_report"], num["eda_report"] = pd.to_numeric(num["first_report"]), pd.to_numeric(num["eda_report"])
        st.plotly_chart(charts.grouped_bar(num.assign(item=num["item"]), "item", ["first_report", "eda_report"],
                                           "Values reported by both (log scale)", "value").update_yaxes(type="log"), width="stretch")
    st.markdown("##### Deterministic narrative (no LLM; every answer cites its evidence)")
    nar = reports.narrative(cmp)
    for n in nar:
        st.markdown(f"**{n['q']}** {n['a']}  \n<span style='color:var(--muted);font-size:.8rem'>Evidence: {n['evidence']}</span>", unsafe_allow_html=True)
    md = exporters.markdown_report("First vs EDA report comparison", [("Comparison", exporters.table_md(cmp)), ("Warnings", "\n".join(f"- {w}" for w in reports.warnings())),
                                   ("Narrative", "\n".join(f"- **{n['q']}** {n['a']} (evidence: {n['evidence']})" for n in nar))],
                                   [F.get("path", ""), E.get("path", "")], "BFI v1 reports")
    a, b = st.columns(2)
    a.download_button("Download comparison (CSV)", exporters.csv_bytes(cmp), "report_comparison.csv", "text/csv")
    b.download_button("Download comparison (Markdown)", md.encode(), "report_comparison.md", "text/markdown")
