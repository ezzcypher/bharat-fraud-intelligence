"""Global filter state -> boolean mask, chips and counts. Pure pandas (no Streamlit) so it is unit-testable."""
from __future__ import annotations

import pandas as pd

from . import settings as S


def defaults(df: pd.DataFrame) -> dict:
    """Default = everything selected (no filter active)."""
    d = {}
    if "split" in df: d["split"] = sorted(df["split"].unique())
    if "day" in df: d["day"] = (int(df["day"].min()), int(df["day"].max()))
    d["score"] = (0.0, 1.0)
    if "amount_usd" in df: d["amount_usd"] = (float(df["amount_usd"].min()), float(df["amount_usd"].max()))
    for c in ("risk_band", "decision", "ProductCD", "card4", "card6", "P_emaildomain", "addr1", "addr2"):
        if c in df: d[c] = []          # empty list = no restriction
    if "identity_present" in df and df["identity_present"].notna().any(): d["identity_present"] = "any"
    if "isFraud" in df and S.MODE == "evaluation": d["isFraud"] = "any"
    d["tid"] = ""
    return d


def mask(df: pd.DataFrame, f: dict) -> pd.Series:
    """Apply every active filter; unknown keys are ignored, missing columns are never invented."""
    m = pd.Series(True, index=df.index)
    if f.get("split") and "split" in df: m &= df["split"].isin(f["split"])
    if "day" in f and "day" in df: m &= df["day"].between(*f["day"])
    if "score" in f: m &= df["score"].between(*f["score"])
    if "amount_usd" in f and "amount_usd" in df: m &= df["amount_usd"].between(*f["amount_usd"])
    for c in ("risk_band", "decision", "ProductCD", "card4", "card6", "P_emaildomain", "addr1", "addr2"):
        if f.get(c) and c in df:
            vals = [None if v == "(missing)" else v for v in f[c]]
            m &= df[c].isin(vals) | (df[c].isna() & (None in vals))
    if f.get("identity_present") in ("yes", "no") and "identity_present" in df:
        m &= df["identity_present"] == (f["identity_present"] == "yes")
    if f.get("isFraud") in ("0", "1") and "isFraud" in df and S.MODE == "evaluation":   # label filter: evaluation mode only
        m &= df["isFraud"] == int(f["isFraud"])
    if str(f.get("tid", "")).strip():
        try:
            m &= df.index == int(str(f["tid"]).strip())
        except ValueError:
            m &= False
    return m


def chips(df: pd.DataFrame, f: dict) -> list[str]:
    """Human-readable list of filters that differ from the defaults."""
    base, out = defaults(df), []
    for k, v in f.items():
        if k in base and v != base[k] and v not in ("", "any", []):
            out.append(f"{k}: {v[0]:g}–{v[1]:g}" if isinstance(v, tuple) else f"{k}: {', '.join(map(str, v)) if isinstance(v, list) else v}")
    return out


def is_filtered(df: pd.DataFrame, f: dict) -> bool:
    return bool(chips(df, f))
