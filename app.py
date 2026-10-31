"""BFI v2 | Fraud Intelligence - dashboard entry point.

Run (Colab, private kernel proxy only - never a public tunnel):
    streamlit run app.py --server.port 8501 --server.headless true
Mode is fixed at launch with BFI9_MODE (default investigation); no widget or question can change it.
Reviewer actions (case status, notes, alert review) need BFI9_REVIEWER_CODE set in the launch environment."""
import sys
from pathlib import Path

import streamlit as st

# Step 1: make the Phase 9 package importable regardless of the working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="BFI v2 | Fraud Intelligence", page_icon=":material/shield:", layout="wide", initial_sidebar_state="expanded")

from bfi9 import settings as S  # noqa: E402
from bfi9 import ui  # noqa: E402
from views import (analyst, audit, cases, common, complaints, costs, eda, explain, explorer, forecasting, formulas, intel,  # noqa: E402
                   investigation, monitor, overview, performance, reports_page, risk)

# Step 2: theme - session value (persists across pages), synced to native widgets, CSS and Plotly.
st.session_state.setdefault("theme", "light")
ui.sync_native_theme()
ui.inject_css()

# Step 3: sidebar identity, theme toggle, mode badge, environment notice.
with st.sidebar:
    st.markdown("**BFI v2 · Fraud Intelligence**")
    st.caption("Explainable fraud review on the frozen Phase 4 model")
    dark = st.toggle("Dark theme", value=ui.theme() == "dark", key="theme_toggle")
    if dark != (ui.theme() == "dark"):
        st.session_state["theme"] = "dark" if dark else "light"
        st.rerun()
    st.caption(f"Mode: **{S.MODE}** · " + ("labels hidden" if S.MODE == "investigation" else "labels visible (evaluation)"))
    st.caption("Development / demo environment on Google Colab · not a production system · data may be lost on runtime reset")

# Step 4: navigation (existing routes kept; three operations pages added).
P = lambda fn, title, icon, url: st.Page(fn, title=title, icon=f":material/{icon}:", url_path=url)
nav = st.navigation({
    "Overview": [P(overview.render, "Executive Overview", "dashboard", "overview"), P(monitor.render, "Live Monitoring", "monitor_heart", "monitoring"),
                 P(risk.render, "Fraud & Risk Analytics", "insights", "risk")],
    "Investigate": [P(explorer.render, "Transaction Explorer", "search", "explorer"), P(investigation.render, "Transaction Investigation", "receipt_long", "investigation"),
                    P(explain.render, "Feature Explainability", "account_tree", "explainability")],
    "Cases": [P(complaints.render, "Register Complaint", "edit_note", "complaints"), P(cases.render, "Case Management", "folder_shared", "cases")],
    "Model": [P(performance.render, "Model Performance", "target", "performance"), P(costs.render, "Cost & Decision Simulator", "balance", "costs"),
              P(forecasting.render, "Forecasting & Scenarios", "show_chart", "forecasting")],
    "Data & Reports": [P(eda.render, "EDA & Data Quality", "dataset", "eda"), P(reports_page.render, "Report Comparison", "compare", "reports")],
    "Intelligence": [P(analyst.render, "AI Fraud Analyst", "chat", "analyst"), P(intel.render, "Global Fraud Intelligence", "public", "global"),
                     P(formulas.render, "Formula & Solution Explorer", "functions", "formulas")],
    "System": [P(audit.render, "Data Sources, Status & Audit", "verified", "audit")],
}, expanded=True)
ui.provenance_banner()  # Step 5: reconstructed-dependency notice on every page (read from the marker files)

# Step 6: one error boundary for every page - friendly message + reference; details go to the local diagnostics log.
try:
    nav.run()
except Exception as e:
    if type(e).__module__.startswith("streamlit"):  # st.stop / st.rerun / st.switch_page control flow
        raise
    st.error(f"**This page could not be displayed.** Reference `{common.log_issue('page_error', e)}` "
             "(details are in outputs/runtime/diagnostics.jsonl). Other pages keep working.", icon=":material/error:")
