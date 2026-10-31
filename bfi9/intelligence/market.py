"""End-of-day prices (Stooq CSV) and exploratory event studies. Association only - never causal, never advice."""
from __future__ import annotations

import io
import time
import urllib.request

import numpy as np
import pandas as pd
from scipy import stats

from .sources import STORE, UA

BENCH = {"US": "^spx", "IN": "^nif"}   # Stooq symbols for S&P 500 / NIFTY (end-of-day)
DATA_NOTE = "Stooq end-of-day historical prices (not real-time); unadjusted for corporate actions unless Stooq adjusts them."


def stooq_symbol(ticker: str, exchange: str = "US") -> str:
    return ticker.lower() if ticker.startswith("^") else f"{ticker.lower()}.{'us' if exchange == 'US' else 'in'}"


def prices(symbol: str, max_age_h: float = 24) -> tuple[pd.DataFrame | None, str]:
    """Cached daily OHLCV. Returns (frame or None, status)."""
    p = STORE / "prices" / f"{symbol.replace('^', '_')}.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and (time.time() - p.stat().st_mtime) < max_age_h * 3600:
        return pd.read_csv(p, parse_dates=["Date"]), "cached"
    try:
        req = urllib.request.Request(f"https://stooq.com/q/d/l/?s={symbol}&i=d", headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=20).read(5_000_000).decode("utf8", "ignore")
        df = pd.read_csv(io.StringIO(raw), parse_dates=["Date"])
        if not {"Date", "Close"} <= set(df.columns) or df.empty:
            raise ValueError("no price data returned")
        df.to_csv(p, index=False)
        return df, "live"
    except Exception as e:
        if p.exists():
            return pd.read_csv(p, parse_dates=["Date"]), f"stale cache ({type(e).__name__})"
        return None, f"unavailable ({type(e).__name__}: {str(e)[:80]})"


def returns(px: pd.DataFrame) -> pd.DataFrame:
    """R_t = P_t/P_{t-1} - 1 and r_t = ln(P_t/P_{t-1}) on consecutive TRADING rows (gaps are not filled)."""
    d = px.sort_values("Date").set_index("Date")
    return pd.DataFrame({"R": d["Close"].pct_change(), "r": np.log(d["Close"]).diff(), "Volume": d.get("Volume")}).dropna(subset=["R"])


def event_study(stock: pd.DataFrame, bench: pd.DataFrame, event_date, est=(-120, -11), windows=((-1, 1), (0, 5)), min_est: int = 60,
                other_events=()) -> dict:
    """Market-model abnormal returns around the first trading day >= event_date."""
    s, m = returns(stock)["R"], returns(bench)["R"]
    j = pd.concat({"Ri": s, "Rm": m}, axis=1, sort=True).dropna()
    ev = pd.Timestamp(event_date).tz_localize(None).normalize()
    after = j.index[j.index >= ev]
    if len(after) == 0:
        return {"status": "Insufficient evidence for event-study analysis", "reason": "no trading data on/after the event date"}
    t0 = j.index.get_loc(after[0])
    e0, e1 = t0 + est[0], t0 + est[1]
    if e0 < 0 or (e1 - e0 + 1) < min_est:
        return {"status": "Insufficient evidence for event-study analysis", "reason": f"needs >= {min_est} estimation days before the event"}
    E = j.iloc[e0:e1 + 1]
    beta, alpha, *_ = stats.linregress(E["Rm"], E["Ri"])
    resid_sd = float(np.std(E["Ri"] - (alpha + beta * E["Rm"]), ddof=2))
    j = j.assign(AR_market_model=j["Ri"] - (alpha + beta * j["Rm"]), AR_benchmark_adjusted=j["Ri"] - j["Rm"], rel_day=np.arange(len(j)) - t0)
    out = {"status": "exploratory", "event_trading_day": str(j.index[t0].date()), "alpha": float(alpha), "beta": float(beta), "estimation_days": int(len(E)),
           "estimation_window": est, "series": j[(j.rel_day >= -10) & (j.rel_day <= 10)].reset_index(names="Date"), "cars": []}
    for a, b in windows:
        w = j[(j.rel_day >= a) & (j.rel_day <= b)]
        if len(w) < (b - a + 1):
            out["cars"].append({"window": f"[{a},{b}]", "CAR": None, "note": "window extends past available data"})
            continue
        car = float(w["AR_market_model"].sum())
        t = car / (resid_sd * np.sqrt(len(w))) if resid_sd else float("nan")
        out["cars"].append({"window": f"[{a},{b}]", "CAR": car, "t_stat": t, "p_value_two_sided": float(2 * stats.t.sf(abs(t), len(E) - 2))})
    conf = [d for d in other_events if abs((pd.Timestamp(d).tz_localize(None) - ev).days) <= 5 and pd.Timestamp(d).tz_localize(None) != ev]
    out["confounded"] = bool(conf)
    out["caveats"] = ["Association, not causation: earnings, macro news, sector moves or other events may explain returns.",
                      "Single-event t-test assumes normal, independent residuals.", DATA_NOTE, "Not investment advice."]
    if conf:
        out["caveats"].insert(0, f"Potentially confounded: {len(conf)} other reported event(s) within ±5 days.")
    return out
