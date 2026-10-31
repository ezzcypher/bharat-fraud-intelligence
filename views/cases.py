"""Case Management - lookup, search and filters, status workflow with audit trail, notes, analytics, redacted export."""
import datetime as dt

import pandas as pd
import streamlit as st

from bfi9 import cases, charts, ui

from . import common


def _detail(cid: str):
    c = cases.get(cid)
    if not c:
        st.warning(f"No case with ID **{cid}**.")
        return
    with st.container(border=True):
        a, b = st.columns([3, 1])
        a.markdown(f"#### {c['case_id']}")
        a.caption(f"{c['origin']} · {c['category']} · created {c['created_utc']} UTC · last updated {c['updated_utc']} UTC"
                  + (" · reviewer " + c["reviewer"] if c["reviewer"] else ""))
        b.markdown(ui.status_pill(c["status"]), unsafe_allow_html=True)
        if c["is_demo"]:
            ui.badge("DEMO DATA", "demo", "Linked to a replayed historical event, not a real-time transaction.")
        k = st.columns(4)
        with k[0]: ui.kpi("Incident (UTC)", c["incident_utc"] or "—", "Reported by the complainant.", "complaint form", "this case", "measured")
        with k[1]: ui.kpi("Amount", c["amount"], "Approximate amount reported.", "complaint form", "this case", "measured", "{:,.2f}")
        with k[2]: ui.kpi("Payment reference", c["txn_ref_masked"] or "—", "Only the last 4 characters are stored.", "complaint form", "this case", "measured")
        with k[3]: ui.kpi("Contact", c["contact"] or "—", "Masked; never exported.", "complaint form", "this case", "measured")
        if c["linked_tid"] is not None:
            st.markdown(f"**Linked transaction** {c['linked_tid']} · risk score {c['score_at_link']:.4f} (uncalibrated) · band {ui.band_label(c['band_at_link'])} · "
                        f"decision *{c['decision_at_link']}* · copied at case creation, model output unchanged", unsafe_allow_html=True)
            if c["rationale"]:
                st.caption(f"Reviewer rationale: {c['rationale']}")
        st.markdown("**Description**")
        st.text(c["description"])
        if c["evidence"]:
            st.dataframe(pd.DataFrame(c["evidence"])[["utc", "filename", "bytes", "sha256"]], hide_index=True)
        a, b = st.columns(2)
        a.markdown("**Notes**")
        for n in c["notes"] or [{"utc": "", "author": "", "note": "No notes yet."}]:
            a.markdown(f"<div class='bfi-note' style='margin-bottom:6px'><span class='bfi-k-foot'>{n['utc']} {n['author']}</span><br>"
                       f"{ui.esc(n['note'])}</div>", unsafe_allow_html=True)
        b.markdown("**Audit trail**")
        b.dataframe(pd.DataFrame(c["audit"])[["utc", "actor", "action", "from_status", "to_status"]], hide_index=True)
    with st.form(f"act_{cid}"):
        st.markdown("**Reviewer actions**")
        x = st.columns(3)
        who = x[0].text_input("Reviewer name", max_chars=60)
        code = x[1].text_input("Reviewer access code", type="password", help="Set by the operator at launch (BFI9_REVIEWER_CODE)")
        nxt = x[2].selectbox("Move to status", ["(no change)"] + sorted(cases.TRANSITIONS[c["status"]]))
        note = st.text_area("Investigation note (timestamped; no card numbers or personal data)", max_chars=2000)
        go = st.form_submit_button("Save", type="primary")
    if go:
        try:
            if nxt != "(no change)":
                cases.update_status(cid, nxt, who, code, note)
            elif note.strip():
                cases.add_note(cid, who, code, note)
            else:
                st.info("Nothing to save.")
                return
            st.success("Saved.")
            st.rerun()
        except cases.CaseError as e:
            for k, v in e.errors.items():
                st.error(f"**{k}:** {v}")


def render():
    ui.header("Case Management", "Complaints and alert-driven investigations · status workflow · audit trail")
    st.caption("Cases live in a local SQLite file in this Colab runtime (outputs/runtime). A case here is not an official complaint and is never forwarded.")
    try:
        allc = cases.search()
    except Exception as e:
        ui.unavailable("Case store", f"The local database could not be opened. Reference {common.log_issue('cases_open', e)}.")
        return
    look = st.text_input("Look up case ID", placeholder="BFI-20261031-ABC123", max_chars=24)
    if look.strip():
        _detail(look.strip().upper())
        st.divider()
    with st.expander("Search and filters", expanded=True):
        c = st.columns([2, 2, 2, 1.4, 1.4])
        q = c[0].text_input("Case ID or transaction ID contains")
        sts = c[1].multiselect("Status", cases.STATUSES)
        cats = c[2].multiselect("Category", cases.CATEGORIES + (cases.ALERT_CATEGORY,))
        d0 = c[3].date_input("From", value=None)
        d1 = c[4].date_input("To", value=None)
    df = cases.search(q, sts, cats, d0, d1)
    k = st.columns(4)
    with k[0]: ui.kpi("Cases in view", len(df), "Cases matching the filters.", "cases table", "filtered view")
    with k[1]: ui.kpi("Open", int(df["status"].isin(["Submitted", "Under Review", "Awaiting Information"]).sum()), "Submitted, Under Review or Awaiting Information.", "cases table", "filtered view")
    with k[2]: ui.kpi("From model alerts", int(df["origin"].eq("model alert").sum()), "Opened by a reviewer from an alert.", "cases table", "filtered view")
    with k[3]: ui.kpi("Total stored", len(allc), "All cases in this runtime.", "cases table", "all")
    if df.empty:
        st.info("**No cases match.** Register a complaint or open a case from an alert in *Live Monitoring*.", icon="🗂️")
        return
    a, b = st.columns(2)
    sc = df["status"].value_counts().reindex(cases.STATUSES).fillna(0)
    a.plotly_chart(charts.bar(sc.index, sc.values, "Cases by status", "status", "cases"), width="stretch")
    per = df.assign(day=pd.to_datetime(df["created_utc"]).dt.date).groupby("day").size().rename("cases").reset_index()
    b.plotly_chart(charts.bar(per["day"].astype(str), per["cases"], "Cases registered per day (UTC)", "day", "cases", color_idx=1), width="stretch")
    view = df.assign(data=df["is_demo"].map({1: "DEMO DATA", 0: ""}))
    ev = st.dataframe(view, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                      column_config={"score_at_link": st.column_config.NumberColumn("risk score at link", format="%.4f"),
                                     "amount": st.column_config.NumberColumn("amount", format="%.2f")})
    st.download_button("Export redacted case list (CSV)", cases.export_redacted(df), f"bfi_cases_redacted_{dt.date.today()}.csv", "text/csv",
                       help="No contact details, descriptions or notes; references masked to the last 4 characters.")
    sel = ev.selection.rows if ev and hasattr(ev, "selection") else []
    if sel:
        _detail(view.iloc[sel[0]]["case_id"])
