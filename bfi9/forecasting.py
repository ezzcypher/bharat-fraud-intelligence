"""Relative-day volume baselines with rolling-origin backtests, plus PSI drift check. NEW Phase 9 methods.

IEEE-CIS TransactionDT has no calendar origin, so only 'relative day' series exist. Forecast target: daily
transaction COUNT (no labels). Fraud labels are never forecast."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from . import phase8

METHODS = ("naive", "seasonal_naive_7", "rolling_mean_7")


@lru_cache(maxsize=1)
def daily_volume() -> pd.Series:
    """All 590,540 raw transactions counted per relative day (reads one column)."""
    f = phase8.load().settings.RAW_DIR / "train_transaction.csv"
    dtv = pd.read_csv(f, usecols=["TransactionDT"])["TransactionDT"]
    s = (dtv // 86400).value_counts().sort_index()
    full = pd.RangeIndex(int(s.index.min()), int(s.index.max()) + 1)
    return s.reindex(full, fill_value=0).rename("transactions")  # explicit zeros for any empty day (none expected)


def predict(history: np.ndarray, method: str, h: int) -> np.ndarray:
    if len(history) < 7:
        raise ValueError("need at least 7 days of history")
    if method == "naive":
        return np.repeat(history[-1], h).astype(float)
    if method == "seasonal_naive_7":
        return np.array([history[-7 + (i % 7)] for i in range(h)], dtype=float)
    if method == "rolling_mean_7":
        return np.repeat(history[-7:].mean(), h)
    raise ValueError(f"unknown method {method}")


def backtest(series: pd.Series, h: int = 14, folds: int = 6) -> tuple[pd.DataFrame, dict]:
    """Rolling origin: each fold trains on everything before the origin and forecasts the next h days."""
    y = series.to_numpy(dtype=float)
    origins = [len(y) - h * (k + 1) for k in range(folds)][::-1]
    rows, resid = [], {m: [] for m in METHODS}
    for o in origins:
        if o < 28:
            continue
        actual = y[o:o + h]
        for m in METHODS:
            p = predict(y[:o], m, h)
            err = actual - p
            resid[m].append(err)
            rows.append({"origin_day": int(series.index[o]), "method": m, "MAE": float(np.mean(np.abs(err))),
                         "MAPE_pct": float(np.mean(np.abs(err) / np.maximum(actual, 1)) * 100)})
    res = pd.DataFrame(rows)
    return res, {m: np.vstack(v) for m, v in resid.items() if v}


def forecast(series: pd.Series, method: str, h: int = 14, level: float = 0.8) -> pd.DataFrame:
    """Point forecast + empirical interval from backtest residual quantiles at each horizon step."""
    _, R = backtest(series, h)
    p = predict(series.to_numpy(dtype=float), method, h)
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    lo = p + np.quantile(R[method], lo_q, axis=0) if method in R else p * np.nan
    hi = p + np.quantile(R[method], hi_q, axis=0) if method in R else p * np.nan
    days = np.arange(int(series.index[-1]) + 1, int(series.index[-1]) + 1 + h)
    return pd.DataFrame({"day": days, "forecast": p, "lower": np.maximum(lo, 0), "upper": hi})


def psi(expected, actual, bins: int = 10) -> float:
    """Population Stability Index with quantile bins of the reference: Σ (a−e)·ln(a/e). ~0.1 small, >0.25 large (rule of thumb)."""
    e, a = np.asarray(expected, float), np.asarray(actual, float)
    edges = np.unique(np.quantile(e, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    pe = np.histogram(e, edges)[0] / len(e)
    pa = np.histogram(a, edges)[0] / len(a)
    pe, pa = np.clip(pe, 1e-6, None), np.clip(pa, 1e-6, None)
    return float(np.sum((pa - pe) * np.log(pa / pe)))
