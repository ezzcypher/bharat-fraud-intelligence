"""4. Transaction Investigation - Phase 8 transaction + explanation, evidence, report builder, feedback."""
import datetime as dt
import json

import pandas as pd
import streamlit as st

from bfi9 import cases, charts, exporters, phase8, ui
from bfi9 import settings as S

from . import common


def _sigmoid(x):
    import math
    return 1 / (1 + math.exp(-x))


def render():
    ui.header("Transaction Investigation", "One transaction · score, decision, band, explanation and evidence (Phase 8 API)")
    if not common.require_v2():
        return
    df = common.frame()
    default = st.session_state.get("selected_tid") or int(df.sort_values("score").index[-1])
    raw = st.text_input("TransactionID", str(default), help="Select a row in Transaction Explorer or type an ID from the validation/test splits")
    try:
        tid = int(raw)
    except ValueError:
        st.error("TransactionID must be an integer.")
        return
    tx = phase8.transaction(tid)
    if tx.get("status") != "found":
        ui.unavailable(f"Transaction {tid}", f"Phase 8 returned status '{tx.get('status')}'. {tx.get('error', '')}")
        return
    row = df.loc[tid] if tid in df.index else None

    # Step 1: summary strip (only fields that exist).
    c = st.columns(5)
    with c[0]: ui.kpi("Model score", tx.get("model_score"), tx.get("score_meaning", ""), "Phase 4 stored score", tx.get("split", ""), "measured", "{:.4f}")
    with c[1]: ui.kpi("Decision", tx.get("decision"), f"score ≥ {tx.get('threshold'):.4f} → alert", "frozen threshold", "this transaction", "derived")
    with c[2]:
        st.markdown(f'<div class="bfi-card"><div class="bfi-k-label">Risk band</div><div class="bfi-k-value">{ui.band_label(tx.get("risk_band"))}</div>'
                    f'<div class="bfi-k-foot">{tx.get("risk_band_status", "")}</div></div>', unsafe_allow_html=True)
    with c[3]: ui.kpi("Split", tx.get("split"), "Phase 4 day-based split", "BFI_v2_splits.csv", "this transaction")
    with c[4]: ui.kpi("Amount (USD)", None if row is None else row.get("amount_usd"), "TransactionAmt", "feature store", "this transaction", "measured", "{:,.2f}")
    if row is not None:
        st.caption(" · ".join(f"{k}: {row[k]}" for k in ("day", "ProductCD", "card4", "card6", "P_emaildomain", "identity_present", "n_missing_inputs") if k in row.index)
                   + " · Customer, merchant, payment status and timeline: **Unknown / Not available** in IEEE-CIS.")

    # Step 2: explanation.
    st.markdown("##### Why the model scored it this way")
    e = phase8.explain_full(tid)
    if e.get("status") != "available":
        ui.unavailable("Explanation", e.get("reason") or e.get("error") or e.get("status"))
    else:
        unv = phase8.unverified_families()   # same Phase 6 rule Phase 8 applies to live explanations
        rows = [dict(feature=f"{x['feature']} = {x['value']}", contribution=x["contribution_log_odds"], family=x["family"],
                     availability=x.get("decision_time_availability") or ("UNVERIFIED" if x["family"] in unv else "plausible (not verified)"))
                for x in e["top_increasing"] + e["top_decreasing"]]
        cf = pd.DataFrame(rows)
        a, b = st.columns([3, 2])
        a.plotly_chart(charts.contributions(cf), width="stretch")
        with b:
            add_ok = abs(_sigmoid(e["raw_log_odds"]) - e["fraud_score"]) < 1e-6
            st.markdown(f"- **Output explained:** model log-odds {e['raw_log_odds']:+.4f} → score σ(·) = {e['fraud_score']:.4f}\n"
                        f"- **Baseline (expected log-odds):** {e['base_log_odds']:+.4f}\n"
                        f"- **Additivity:** σ(base + Σφ) = score → {'✅ verified' if add_ok else '⚠️ not verified'}; matches stored Phase 4 score: "
                        f"{'✅' if e.get('consistent_with_stored_score') else '⚠️'}\n- **Source:** {e.get('source')}")
            st.dataframe(cf[["feature", "family", "availability"]], hide_index=True, width="stretch")
        for w in e.get("warnings", []) + e.get("caveats", []):
            st.caption("• " + w)
        ui.note("SHAP contributions describe <b>this model's behaviour</b>, not causes of fraud, and do not show a feature was available at decision time.")

    # Step 3: next steps + report builder + feedback.
    with st.expander("Open an investigation case for this transaction (reviewer)"):
        st.caption("Copies the stored score, band and decision into a new case. The model output is not changed, and opening a case "
                   "does not mark the transaction or any person as fraudulent.")
        with st.form("open_case"):
            x = st.columns(2)
            who = x[0].text_input("Reviewer name", max_chars=60)
            code = x[1].text_input("Reviewer access code", type="password", help="Set by the operator at launch (BFI9_REVIEWER_CODE)")
            why = st.text_area("Alert rationale / note (no card numbers or personal data)", max_chars=1000)
            go = st.form_submit_button("Open case", type="primary")
        if go:
            try:
                st.success(f"Case **{cases.create_from_alert(who, code, why, tid=tid)}** opened (Under Review) - see Case Management.")
            except cases.CaseError as err:
                for k, v in err.errors.items():
                    st.error(f"**{k}:** {v}")
    st.markdown("##### Suggested next steps")
    st.markdown("1. Check the top contributing inputs against source systems (C/D/M/V meanings are masked).\n"
                "2. Treat the band as provisional; review priority follows the score, not a probability.\n"
                "3. Record the outcome in the case system; the model label is not an investigation result.")
    secs = [("Transaction", json.dumps({k: v for k, v in tx.items() if k not in ("caveats",)}, indent=1, default=str)),
            ("Explanation", json.dumps({k: e.get(k) for k in ("status", "method", "base_log_odds", "raw_log_odds", "fraud_score", "top_increasing", "top_decreasing")}, indent=1, default=str)),
            ("Limitations", "Uncalibrated score; chargeback-derived labels; feature availability unverified for C/D/M/V/dist; offline research model.")]
    md = exporters.markdown_report(f"Investigation report · transaction {tid}", secs, ["Phase 8 phase9_api.transaction", "Phase 8 explanation_adapter.explain"],
                                   f"{tx.get('split')} split, model A, frozen threshold")
    a, b = st.columns(2)
    a.download_button("Download report (Markdown)", md.encode(), f"investigation_{tid}.md", "text/markdown")
    b.download_button("Download report (HTML → print to PDF)", exporters.html_report(md, f"Investigation {tid}").encode(), f"investigation_{tid}.html", "text/html")
    with st.expander("Analyst feedback (stored locally; never used as a label or for retraining)"):
        useful = st.radio("Was the explanation useful?", ["yes", "partly", "no"], horizontal=True)
        step = st.selectbox("Next step needed", ["none", "verify feature meaning", "escalate for review", "data-quality issue"])
        note = st.text_area("Note (no personal data)", max_chars=500)
        if st.button("Save feedback"):
            S.FEEDBACK.parent.mkdir(parents=True, exist_ok=True)
            with open(S.FEEDBACK, "a") as f:
                f.write(json.dumps({"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "transaction_id": tid, "useful": useful, "next_step": step,
                                    "note": exporters.redact(note)[:500], "is_label": False}) + "\n")
            st.success("Saved to outputs/runtime/analyst_feedback.jsonl")
