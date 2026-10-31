"""Live Monitoring - ingestion health, scored event stream, review queue and the documented ingestion interface.

No external live source is connected in this build. Events come from (a) files/API calls handed to bfi9.monitor.ingest
(user-supplied, unverified source) or (b) DEMO DATA: historical IEEE-CIS test rows replayed with a simulated arrival time."""
import datetime as dt
import json

import pandas as pd
import streamlit as st

from bfi9 import cases, charts, exporters, monitor, ui
from bfi9 import settings as S

from . import common

WINDOWS = {"Last 15 min": 15, "Last hour": 60, "Last 24 h": 1440, "All stored": None}


def _health():
    h = monitor.health()
    c = st.columns(4)
    with c[0]:
        ui.kpi("External live stream", "Not connected", h["external_stream"], "deployment configuration", "this runtime", "measured", foot="no authorised source configured")
    with c[1]:
        ui.kpi("Event store", h["db"].upper() if h["db"] == "ok" else "ERROR", f"Local SQLite at outputs/runtime (lost on Colab runtime reset).",
               "bfi9/store.py", "this runtime", "measured", foot=f"last event {h.get('last_event_utc') or '—'} UTC")
    with c[2]:
        ui.kpi("Events stored (real · demo)", f"{h.get('events_real', 0):,} · {h.get('events_demo', 0):,}",
               "Real = ingested through the interface from a user-named source (unverified). Demo = DATA REPLAY, not live.", "events table", "this runtime", "measured")
    with c[3]:
        ui.kpi("Scoring model", "Frozen A" if h["model"].startswith("ok") else "Unavailable", h["model"], "Phase 4 model file via Phase 8 links", "all events",
               "measured", foot=f"threshold {S.frozen()['threshold']:.4f}")
    li = h.get("last_ingest")
    if li:
        st.caption(f"Last ingestion {li['utc']} UTC · source: {li['source']} · received {li['received']} · accepted {li['accepted']} · "
                   f"duplicates {li['duplicates']} · rejected {li['rejected']}")


def _feed(window, bands, statuses, demo):
    since = None if WINDOWS[window] is None else (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=WINDOWS[window])).isoformat(timespec="seconds")
    ev = monitor.events(since, bands, statuses, demo)
    if ev.empty:
        st.info("**No events in this view.** Nothing has been ingested for these filters yet. Use *Replay DEMO DATA* or the *Ingest* tab.", icon="📭")
        return
    alerts = ev["decision"].eq("alert for review")
    c = st.columns(4)
    with c[0]: ui.kpi("Events processed", len(ev), "Scored events in the selected window and filters.", "events table", "filtered view")
    with c[1]: ui.kpi("Alerts for review", int(alerts.sum()), "score ≥ frozen threshold. A review signal, not confirmed fraud.", "frozen threshold", "filtered view")
    with c[2]: ui.kpi("Awaiting review", int((alerts & ev["review_status"].eq("new")).sum()), "Alerts with review status 'new'.", "events table", "filtered view")
    with c[3]: ui.kpi("Demo share", ev["is_demo"].mean(), "Share of events in view that are DEMO DATA replay.", "events table", "filtered view", "measured", "{:.0%}")
    if ev["is_demo"].any():
        ui.badge("DEMO DATA", "demo", "Historical IEEE-CIS rows replayed with a simulated arrival time - not real-time transactions or live detections.")
    a, b = st.columns(2)
    a.plotly_chart(charts.score_hist(ev["score"], S.frozen()["threshold"], "Risk-score distribution (events in view)"), width="stretch")
    t = ev.assign(minute=pd.to_datetime(ev["received_utc"]).dt.floor("min")).groupby("minute").agg(events=("score", "size"), alerts=("decision", lambda s: int((s == "alert for review").sum())))
    b.plotly_chart(charts.lines(t.reset_index(), "minute", ["events", "alerts"], "Events and alerts per minute (arrival time, UTC)", "count"), width="stretch")
    ok = ev["stored_score"].notna()
    if ok.any():
        diff = (ev.loc[ok, "score"] - ev.loc[ok, "stored_score"]).abs().max()
        st.caption(f"Score reconciliation: {int(ok.sum()):,} events have a stored Phase 4 score; max |live − stored| = {diff:.2e} "
                   f"({'✅ identical scoring pipeline' if diff < 1e-6 else '⚠️ differs - investigate'}).")
    st.markdown("##### Recent activity")
    view = ev.head(200).assign(data=ev["is_demo"].map({1: "DEMO DATA", 0: "unverified source"}))
    st.dataframe(view[["received_utc", "transaction_id", "data", "source", "amount", "product_cd", "score", "band", "decision", "review_status"]],
                 hide_index=True, width="stretch",
                 column_config={"score": st.column_config.ProgressColumn("risk score", min_value=0, max_value=1, format="%.4f",
                                                                         help="Uncalibrated model risk score, not a probability"),
                                "amount": st.column_config.NumberColumn("amount (USD)", format="%.2f"),
                                "received_utc": st.column_config.TextColumn("received (UTC)")})
    st.download_button("Download events in view (CSV)", exporters.csv_bytes(view), "bfi_monitoring_events.csv", "text/csv")


def _queue():
    q = monitor.events(statuses=["new", "in review"])
    q = q[q["decision"].eq("alert for review")]
    st.caption("Alerts are ranked review signals from the frozen model. Opening a case does not mark anyone or anything as fraud.")
    if q.empty:
        st.info("**Review queue is empty.** No unreviewed alerts are stored.", icon="✅")
        return
    q = q.sort_values("score", ascending=False)
    pick = st.selectbox("Alert", q["event_id"], format_func=lambda e: (lambda r: f"{r.transaction_id} · score {r.score:.4f} · {r.band}"
                        f"{' · DEMO DATA' if r.is_demo else ''} · {r.review_status}")(q.set_index("event_id").loc[e]))
    r = q.set_index("event_id").loc[pick]
    st.markdown(f"Transaction **{r.transaction_id}** · source *{r.source}* · received {r.received_utc} UTC · amount {r.amount:,.2f} USD · "
                f"band {ui.band_label(r.band)} · rationale: score {r.score:.4f} ≥ frozen threshold {S.frozen()['threshold']:.4f}", unsafe_allow_html=True)
    with st.form("review"):
        c = st.columns(2)
        who = c[0].text_input("Reviewer name", max_chars=60)
        code = c[1].text_input("Reviewer access code", type="password", help="Set by the operator at launch (BFI9_REVIEWER_CODE)")
        why = st.text_area("Rationale / note (no card numbers or personal data)", max_chars=1000)
        c = st.columns(3)
        start, dismiss, case = c[0].form_submit_button("Mark in review"), c[1].form_submit_button("Dismiss"), c[2].form_submit_button("Open case", type="primary")
    try:
        if case:
            cid = cases.create_from_alert(who, code, why, event_id=pick)
            st.success(f"Case **{cid}** opened (status Under Review). Find it in *Case Management*.")
        elif start or dismiss:
            cases._check_code(code)  # same reviewer authorisation as cases
            monitor.set_review(pick, "in review" if start else "dismissed")
            st.success("Review status updated.")
    except cases.CaseError as e:
        for k, v in e.errors.items():
            st.error(f"**{k}:** {v}")


def _ingest():
    st.markdown("Hand events to the scoring pipeline. Each row must carry the frozen model's full raw input schema "
                f"({len(monitor.model()[1]['features'])} model columns + `TransactionID`, `TransactionDT`, `TransactionAmt`). "
                "Rows are validated, de-duplicated by TransactionID and scored with the frozen Phase 4 model. "
                "Ingested files are labelled **unverified source** - BFI cannot confirm where they came from.")
    with st.expander("Programmatic interface (Python)"):
        st.code("from bfi9 import monitor\nreport = monitor.ingest(rows_dataframe_or_list_of_dicts, source=\"my-bank-export-2026-10-31\")\nprint(report)  # received / accepted / duplicates / rejected[...]", language="python")
        st.download_button("Required column list (JSON)", json.dumps(list(monitor.REQUIRED) + monitor.model()[1]["features"]).encode(), "bfi_ingest_schema.json", "application/json")
    with st.form("upload"):
        src = st.text_input("Source label", max_chars=120, placeholder="e.g. partner-bank-export-2026-10-31")
        f = st.file_uploader("Events file (CSV or JSON array, max 20 MB)", type=["csv", "json"])
        go = st.form_submit_button("Ingest", type="primary")
    if go:
        if not f or not src.strip():
            st.error("Choose a file and enter a source label.")
            return
        if f.size > 20 * 2**20:
            st.error("File larger than 20 MB.")
            return
        try:
            df = pd.read_json(f) if f.name.lower().endswith(".json") else pd.read_csv(f)
            rep = monitor.ingest(df, src.strip())
        except Exception as e:
            ref = common.log_issue("ingest_failed", e)
            st.error(f"Ingestion failed: {type(e).__name__}. Reference {ref}.")
            return
        (st.success if rep["accepted"] else st.warning)(f"Received {rep['received']} · accepted {rep['accepted']} · duplicates {rep['duplicates']} · rejected {len(rep['rejected'])}")
        if rep["rejected"]:
            st.dataframe(pd.DataFrame(rep["rejected"]).head(50), hide_index=True)


def render():
    ui.header("Live Monitoring", "Scored transaction events · ingestion health · alert review queue")
    if not common.require_v2():
        return
    try:
        _health()
    except Exception as e:
        ui.unavailable("Monitoring", f"The event store or model could not load. Reference {common.log_issue('monitor_health', e)}.")
        return
    ui.note("No bank, UPI, card-network or government feed is connected. Events shown here are either <b>DEMO DATA</b> "
            "(historical IEEE-CIS rows replayed now) or rows a user ingested from a named, <b>unverified</b> source.")
    a, b = st.columns([3, 1])
    n = a.select_slider("Replay batch size", [10, 25, 50, 100, 250], 50)
    if b.button("Replay DEMO DATA", type="secondary", width="stretch"):
        rep = monitor.demo_replay(n)
        st.toast(f"DEMO DATA: {rep['accepted']} events scored ({rep['duplicates']} duplicates)")
    t1, t2, t3 = st.tabs(["Monitor", "Review queue", "Ingest"])
    with t1:
        c = st.columns([1.2, 2, 2, 1.2, 1])
        window = c[0].selectbox("Time range", list(WINDOWS), 3)
        bands = c[1].multiselect("Risk band", list(ui.BAND))
        statuses = c[2].multiselect("Review status", list(monitor.REVIEW))
        demo = c[3].selectbox("Data", ["all", "demo", "real"], format_func={"all": "All", "demo": "DEMO DATA only", "real": "Ingested (unverified) only"}.get)
        auto = c[4].toggle("Auto-refresh", False, help="Re-reads the event store every 10 s")

        @st.fragment(run_every="10s" if auto else None)
        def feed():
            _feed(window, bands, statuses, demo)
        feed()
    with t2:
        _queue()
    with t3:
        _ingest()
