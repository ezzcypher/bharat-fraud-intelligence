"""9. AI Fraud Analyst - Phase 8 deterministic assistant (LLM disabled). Mode fixed at launch; questions cannot change it."""
import re

import streamlit as st

from bfi9 import phase8, reports, ui
from bfi9 import settings as S

from . import common

SUGGESTED = ["Explain the current model's false positives.", "Show me the distribution of model scores.", "Why was this transaction flagged?",
             "Compare the two reports.", "What changed between raw and cleaned data?", "Which limitations should an analyst consider?",
             "How sensitive is the cost estimate to false negatives?", "Which features contribute most to the model output?",
             "What evidence is available for this transaction?", "What should be validated before production deployment?"]


def _phase9_answer(q: str) -> dict | None:
    """Two topics Phase 8 does not index (v1 reports, v1 cleaning) are answered by Phase 9's own deterministic modules."""
    if re.search(r"\breports?\b", q, re.I) and re.search(r"compar|differ|change", q, re.I):
        cmp = reports.compare()
        same = cmp[cmp.status == "unchanged"]["item"].tolist()
        return {"status": "answered", "answer": f"Both v1 reports agree on: {', '.join(same)}. The EDA report adds data-quality checks; the first report adds modelling results.",
                "evidence": [{"source": "Report Comparison table (parsed .docx + notebook outputs)"}],
                "interpretation": "Agreement shows the two artefacts describe the same 550,000-row v1 dataset.",
                "limitations": ["v1 labels were later found near-random (Case Study); v1 findings do not transfer to v2."], "next_steps": ["Open Report Comparison for the full table."]}
    if re.search(r"raw", q, re.I) and re.search(r"clean", q, re.I):
        return {"status": "answered", "answer": "Cleaning kept all 550,000 rows, filled loan_type for rows without a loan ('No Loan') and added 8 engineered columns (20 → 28).",
                "evidence": [{"source": "notebook cells 15 and 21; EDA & Data Quality › Compare Both"}],
                "interpretation": "The cleaned table is the raw table plus derived columns; no records were dropped.",
                "limitations": ["Outlier-flag bounds were computed on the full dataset (possible look-ahead)."], "next_steps": ["See the cleaning transparency table."]}
    return None


def render():
    ui.header("AI Fraud Analyst", "Deterministic Phase 8 assistant · every answer: answer, evidence, interpretation, limitations, next steps")
    if not common.require_v2():
        return
    st.caption(f"LLM: **disabled** (Phase 8 decision; no API key requested, no data leaves this runtime) · mode: **{S.MODE}** (launch setting; questions cannot change it)")
    tid = st.session_state.get("selected_tid")
    cols = st.columns(5)
    clicked = None
    for i, q in enumerate(SUGGESTED):
        if cols[i % 5].button(q, key=f"sq{i}", width="stretch"):
            clicked = q
    q = st.chat_input("Ask about the model, metrics, costs, a transaction ID, or limitations") or clicked
    hist = st.session_state.setdefault("chat", [])
    if q:
        if tid and re.search(r"this transaction", q, re.I):
            q = q.replace("this transaction", f"transaction {tid}")
        ans = _phase9_answer(q) or phase8.ask(q)
        hist.append((q, ans))
    for q, a in reversed(hist[-8:]):
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            if a.get("status") == "error":
                st.error(f"The tool failed: {a.get('error')}. No answer was invented. Try the relevant dashboard page instead.")
                continue
            st.markdown(a.get("answer", ""))
            with st.expander("Evidence · interpretation · limitations · next steps"):
                st.json(a.get("evidence", []), expanded=False)
                st.markdown(f"**Interpretation:** {a.get('interpretation', '—')}")
                st.markdown("**Limitations:**\n" + "\n".join(f"- {x}" for x in a.get("limitations", []) or ["—"]))
                st.markdown("**Next steps:**\n" + "\n".join(f"- {x}" for x in a.get("next_steps", []) or ["—"]))
