"""11. Forecasting & Scenarios - relative-day volume baselines (backtested), workload scenarios, drift readiness."""
import pandas as pd
import streamlit as st

from bfi9 import charts, forecasting as fc, ui

from . import common


@st.cache_data(show_spinner="Counting raw transactions per relative day…")
def _vol():
    return fc.daily_volume()


def render():
    ui.header("Forecasting & Scenarios", "Relative days only · IEEE-CIS has no calendar dates · volume, not fraud, is forecast")
    if not common.require_v2():
        return
    ui.note("<b>What is supported:</b> 182 relative days of transaction counts (TransactionDT ÷ 86,400). There is no real date, so no weekday names, "
            "holidays or calendar forecasts. Fraud labels are <b>not</b> forecast.", warn=True)
    s = _vol()
    a, b = st.columns(2)
    h = a.slider("Horizon (relative days)", 7, 21, 14)
    bt, _ = fc.backtest(s, h)
    if bt.empty:
        ui.unavailable("Forecast", f"only {len(s)} relative days of history; at least {28 + h} are needed for an honest backtest. No forecast is shown.")
        return
    summ = bt.groupby("method")[["MAE", "MAPE_pct"]].mean().sort_values("MAE")
    method = b.selectbox("Method", list(summ.index), help="Best backtest MAE first")
    f = fc.forecast(s, method, h)
    hist = s.reset_index().rename(columns={"index": "day"})
    hist.columns = ["day", "transactions"]
    fig = charts.lines(hist, "day", ["transactions"], f"Daily transactions · history + {h}-day {method} forecast (80% empirical interval)", "transactions/day")
    fig.add_scatter(x=f["day"], y=f["upper"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=f["day"], y=f["lower"], mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(57,135,229,0.18)", name="80% interval")
    fig.add_scatter(x=f["day"], y=f["forecast"], mode="lines", line=dict(dash="dash", width=2), name="forecast")
    fig.update_xaxes(title="relative day")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(summ.style.format("{:.1f}"), width="stretch")
    st.caption(f"Rolling-origin backtest: {bt['origin_day'].nunique()} origins, each trained only on earlier days (no leakage). "
               "Intervals are empirical residual quantiles and assume future errors look like past ones.")

    st.markdown("##### Review-workload scenario (assumption-driven, not a forecast)")
    d = common.frame()
    rate = float((d["decision"] != "no alert").mean())
    c = st.columns(3)
    alert_rate = c[0].number_input("Alert rate", 0.0, 1.0, round(rate, 4), 0.001, format="%.4f", help=f"Default = measured val+test rate {rate:.4f}")
    mins = c[1].number_input("Minutes per review (assumption)", 1, 120, 10)
    cap = c[2].number_input("Analyst hours per day (assumption)", 1, 2000, 80)
    wl = f.assign(alerts=f["forecast"] * alert_rate, review_hours=lambda x: x["alerts"] * mins / 60, capacity_hours=cap)
    st.plotly_chart(charts.grouped_bar(wl, "day", ["review_hours", "capacity_hours"], "Review hours needed vs capacity (scenario)", "hours"), width="stretch")
    st.caption("Scenario = forecast volume × assumed alert rate × assumed minutes. Change any assumption and the result changes; it is not measured workload.")

    st.markdown("##### Drift readiness (score distribution, no labels)")
    val, test = d.loc[d["split"] == "val", "score"], d.loc[d["split"] == "test", "score"]
    p = fc.psi(val, test)
    st.markdown(f"PSI(validation → test scores) = **{p:.3f}** ({'small' if p < .1 else 'moderate' if p < .25 else 'large'} shift by the common rule of thumb). "
                "A descriptive check on offline data, not production monitoring.")
    dc = d.groupby("day").agg(mean_score=("score", "mean"), missing_inputs=("n_missing_inputs", "mean")).reset_index() if "day" in d else pd.DataFrame()
    if not dc.empty:
        a, b = st.columns(2)
        a.plotly_chart(charts.lines(dc, "day", ["mean_score"], "Mean model score per relative day", "mean score"), width="stretch")
        b.plotly_chart(charts.lines(dc, "day", ["missing_inputs"], "Mean missing inputs per relative day", "missing of 431"), width="stretch")
