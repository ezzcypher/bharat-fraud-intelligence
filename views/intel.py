"""12. Global Fraud Intelligence - official feeds only, cached with freshness, isolated from the BFI v2 model."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bfi9 import charts, exporters, ui
from bfi9.intelligence import analysis, incidents as I, market as M, sources as SRC

REL_STYLE = {"victim": ("circle", 0), "origin": ("diamond", 1), "infrastructure": ("square", 2), "jurisdiction": ("triangle-up", 6),
             "mentioned (relation unverified)": ("circle-open", 7)}


def render():
    ui.header("Global Fraud Intelligence", "Official regulator / enforcement feeds · deduplicated incidents · separate from the frozen BFI v2 model")
    a, b, c = st.columns([1, 1, 2])
    max_age = a.selectbox("Refresh interval (hours)", [6, 12, 24, 72], 2)
    if b.button("Refresh now", type="primary"):
        with st.spinner("Fetching official feeds (one request per source)…"):
            st.session_state["intel_log"] = SRC.refresh()
    h = pd.DataFrame(SRC.health(max_age))
    fetched = {r["source_id"] for r in st.session_state.get("intel_log", []) if r["status"] == "live"}
    h.loc[h["source"].isin([s["name"] for s in SRC.SOURCES if s["id"] in fetched]), "status"] = "live (this session)"
    c.caption("Status: **live** = fetched this session · **cached** = last success within interval · **stale** = older · **unavailable/disabled** = shown with error. "
              "Nothing is shown as live unless it was fetched now.")
    with st.expander("Provider health & source registry", expanded=h["last_success"].isna().all()):
        st.dataframe(h, hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame(SRC.NOT_CONNECTED, columns=["provider", "why not connected"]), hide_index=True, width="stretch")
    items = SRC.items()
    if not items:
        ui.unavailable("Incident data", "No feed has been fetched yet (offline mode shows nothing rather than invented news). Press **Refresh now**.")
        return
    inc, geo = I.build(items)

    # Filters (one row) - all applied consistently to every tab.
    f = st.columns(5)
    kw = f[0].text_input("Keyword")
    cats = f[1].multiselect("Category", sorted(inc["category"].unique()))
    orgs = f[2].multiselect("Source", sorted(inc["source_org"].unique()))
    legal = f[3].multiselect("Legal status", sorted(inc["legal_status"].unique()))
    tick = f[4].selectbox("Market linkage", ["any", "verified ticker in source", "none"])
    m = pd.Series(True, index=inc.index)
    if kw: m &= inc["title"].str.contains(kw, case=False) | inc["summary"].str.contains(kw, case=False)
    if cats: m &= inc["category"].isin(cats)
    if orgs: m &= inc["source_org"].isin(orgs)
    if legal: m &= inc["legal_status"].isin(legal)
    if tick != "any": m &= inc["tickers"].str.len().gt(0) == (tick != "none")
    d = inc[m].sort_values("published", ascending=False, na_position="last")
    g = geo[geo["incident_id"].isin(d["incident_id"])]
    ui.chips([x for x in [kw and f"keyword: {kw}", *[f"category: {x}" for x in cats], *[f"source: {x}" for x in orgs], *[f"legal: {x}" for x in legal],
              tick != "any" and f"linkage: {tick}"] if x])
    st.markdown(f"**{len(d)}** deduplicated incidents from **{len(items)}** retrieved items · counts reflect official reporting, not true fraud volume")

    t = st.tabs(["Live Scam & Fraud News", "Global Fraud Map", "Scam Pattern Intelligence", "AI Prevention & Response", "Stock-Market Impact",
                 "Global Threat Trends", "Intelligence Reports"])
    with t[0]:
        st.dataframe(d[["published", "title", "source_org", "category", "legal_status", "reported_loss", "loss_currency", "source_urls"]], hide_index=True,
                     width="stretch", column_config={"source_urls": st.column_config.ListColumn("source links")})
    with t[1]:
        rel = st.multiselect("Layers", list(REL_STYLE), default=["victim", "origin", "infrastructure", "jurisdiction"])
        gg = g[g["relation"].isin(rel)].groupby(["country", "relation"]).size().rename("incidents").reset_index()
        if gg.empty:
            ui.unavailable("Map", "no explicit country relations in the filtered incidents")
        else:
            fig = go.Figure()
            for r_, grp in gg.groupby("relation"):
                sym, ci = REL_STYLE[r_]
                fig.add_trace(go.Scattergeo(locations=grp["country"], locationmode="country names", mode="markers", name=r_,
                                            marker=dict(symbol=sym, size=8 + 4 * grp["incidents"] ** 0.5, color=charts.CAT[ui.theme()][ci], line=dict(width=1)),
                                            text=grp["incidents"], hovertemplate="%{location}<br>" + r_ + ": %{text} incident(s)<extra></extra>"))
            fig.update_geos(showcountries=True, countrycolor=ui.TOKENS[ui.theme()]["border"], bgcolor=ui.TOKENS[ui.theme()]["surface"],
                            landcolor=ui.TOKENS[ui.theme()]["surface2"], showocean=False, projection_type="natural earth")
            st.plotly_chart(charts._fin(fig, "Incident geography by relation (points, not a heatmap)", h=460), width="stretch")
        ui.note("Counts depend on which agencies publish feeds, reporting rates and enforcement activity. A country with more reports is <b>not</b> more fraudulent. "
                "Countries are linked only through explicit phrases; plain mentions are marked 'relation unverified'. No flow lines are drawn.")
        st.dataframe(g, hide_index=True, width="stretch")
    with t[2]:
        a, b = st.columns(2)
        vc = d["category"].value_counts()
        a.plotly_chart(charts.hbar(vc.index, vc.values, "Deduplicated incidents by category", "incidents", text_fmt="{:,.0f}"), width="stretch")
        lc = d.dropna(subset=["reported_loss"]).groupby(["category", "loss_currency"])["reported_loss"].sum().reset_index()
        b.dataframe(lc, hide_index=True, width="stretch")
        b.caption("Reported losses are summed per ORIGINAL currency; no conversion without a recorded exchange rate. Losses, penalties and market moves are never added together.")
        st.markdown(f"**Emerging (≥3 incidents from ≥2 organisations):** {', '.join(I.emerging(d)) or 'none meet the rule'}")
    with t[3]:
        if d.empty:
            ui.unavailable("Analysis", "no incident selected")
        else:
            pick = st.selectbox("Incident", d["incident_id"], format_func=lambda i: d.set_index("incident_id").loc[i, "title"][:110])
            an = analysis.analyse(d.set_index("incident_id").loc[pick].to_dict() | {"incident_id": pick})
            ui.note(an["label"])
            for k in ("A_what_happened", "B_how_it_worked", "C_vulnerability", "D_prevention", "E_ai_help"):
                st.markdown(f"**{k[0]} · {k[2:].replace('_', ' ').capitalize()}** {an[k]}")
            st.markdown("**F · Do now:**\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(an["F_actions_now"])))
            with st.container(border=True):
                st.markdown("**What this incident teaches us about BFI v2**")
                st.write(an["bfi_v2"])
    with t[4]:
        linked = d[d["tickers"].str.len() > 0]
        if linked.empty:
            ui.unavailable("Market impact", "No verified public-market linkage: no filtered incident prints an exchange:ticker in its source text.")
        else:
            row = linked.set_index("incident_id").loc[st.selectbox("Incident with verified ticker", linked["incident_id"],
                                                                    format_func=lambda i: linked.set_index("incident_id").loc[i, "title"][:100])]
            tk = st.selectbox("Ticker (as printed in source)", row["tickers"])
            exch = "IN" if row["jurisdiction"] == "India" else "US"
            px, s1 = M.prices(M.stooq_symbol(tk, exch))
            bx, s2 = M.prices(M.BENCH[exch])
            st.caption(f"{M.DATA_NOTE} · stock: {s1} · benchmark {M.BENCH[exch]}: {s2} · event date = source publication date (an assumption).")
            if px is None or bx is None or not row["published"]:
                ui.unavailable("Event study", "price data or a defensible event date is missing.")
            else:
                es = M.event_study(px, bx, row["published"], other_events=[p for p in inc.loc[inc["tickers"].apply(lambda x: tk in x), "published"] if p])
                if es["status"] != "exploratory":
                    ui.unavailable("Event study", es["reason"])
                else:
                    s = es["series"]
                    st.plotly_chart(charts.lines(s, "rel_day", ["Ri", "Rm", "AR_market_model"], f"{tk}: daily return vs benchmark and abnormal return (±10 trading days)", "return"),
                                    width="stretch")
                    st.dataframe(pd.DataFrame(es["cars"]), hide_index=True)
                    st.markdown(f"α = {es['alpha']:.5f}, β = {es['beta']:.3f} on {es['estimation_days']} estimation days · event trading day {es['event_trading_day']}")
                    for cv in es["caveats"]:
                        st.caption("• " + cv)
    with t[5]:
        tr = I.trends(d)
        if tr.empty:
            ui.unavailable("Trends", "no dated incidents")
        else:
            pv = tr.pivot_table(index="period", columns="category", values="incidents", fill_value=0).reset_index()
            top = list(d["category"].value_counts().index[:4])
            st.plotly_chart(charts.lines(pv, "period", [c for c in top if c in pv], "Weekly deduplicated incidents (top 4 categories)", "incidents"), width="stretch")
            st.dataframe(tr, hide_index=True, width="stretch")
            st.caption("Rises in published reports may reflect agency publishing activity, not more fraud. % change is blank from a zero baseline.")
    with t[6]:
        md = analysis.brief(d.head(50).to_dict("records"), SRC.health(max_age))
        a, b = st.columns(2)
        a.download_button("Intelligence brief (Markdown)", md.encode(), "fraud_intelligence_brief.md", "text/markdown")
        b.download_button("Intelligence brief (HTML → PDF)", exporters.html_report(md, "Fraud intelligence brief").encode(), "fraud_intelligence_brief.html", "text/html")
        st.download_button("Incidents (CSV)", d.to_csv(index=False).encode(), "incidents.csv", "text/csv")
        st.markdown(md[:3000])
