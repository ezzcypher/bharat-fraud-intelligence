"""Data-quality KPIs and raw-vs-cleaned comparison. Pure pandas; works on any frame; rules are documented."""
from __future__ import annotations

import numpy as np
import pandas as pd

OUTLIER_RULE = "IQR rule: value < Q1 - 1.5*IQR or > Q3 + 1.5*IQR (same rule as the v1 notebook Step 10)"


def kpis(df: pd.DataFrame, label: str | None = None, id_col: str | None = None) -> dict:
    """Row/column/duplicate/missing/label KPIs. Label stats only when the label column exists and is binary."""
    n, k = df.shape
    miss = int(df.isna().sum().sum())
    out = {"rows": n, "columns": k, "duplicate_rows": int(df.duplicated().sum()), "missing_cells": miss,
           "missing_pct": round(100 * miss / (n * k), 4) if n * k else None,
           "numeric_columns": int(df.select_dtypes("number").shape[1]), "categorical_columns": int(k - df.select_dtypes("number").shape[1])}
    if id_col and id_col in df:
        out["unique_ids"] = int(df[id_col].nunique()); out["duplicate_ids"] = int(df[id_col].duplicated().sum())
    if label and label in df and set(df[label].dropna().unique()) <= {0, 1}:
        pos = int(df[label].sum())
        out.update(positives=pos, negatives=int(n - pos - df[label].isna().sum()), prevalence_pct=round(100 * pos / n, 4) if n else None)
    return out


def missing_by_column(df: pd.DataFrame) -> pd.DataFrame:
    m = df.isna().sum()
    return pd.DataFrame({"column": m.index, "missing": m.values, "missing_pct": (100 * m / len(df)).round(4).values}).sort_values("missing", ascending=False)


def outliers(df: pd.DataFrame, cols=None, label: str | None = None) -> pd.DataFrame:
    """IQR outlier counts per numeric column (+ label rate among outliers when a label exists)."""
    cols = cols or [c for c in df.select_dtypes("number").columns if df[c].nunique() > 2 and c != label]
    rows = []
    for c in cols:
        s = df[c].dropna()
        q1, q3 = s.quantile([.25, .75]); iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        o = (df[c] < lo) | (df[c] > hi)
        r = {"column": c, "q1": q1, "q3": q3, "lower": lo, "upper": hi, "outliers": int(o.sum()), "outlier_pct": round(100 * o.mean(), 4)}
        if label and label in df and o.any():
            r["label_rate_in_outliers_pct"] = round(100 * df.loc[o, label].mean(), 4)
        rows.append(r)
    return pd.DataFrame(rows)


def schema_compare(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    ca, cb = list(a.columns), list(b.columns)
    common = [c for c in ca if c in cb]
    return {"only_in_first": [c for c in ca if c not in cb], "only_in_second": [c for c in cb if c not in ca], "common": common,
            "dtype_changes": {c: (str(a[c].dtype), str(b[c].dtype)) for c in common if str(a[c].dtype) != str(b[c].dtype)}}


def column_changes(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Per common column: missing, unique and mean before/after. Order-independent (no row alignment assumed)."""
    rows = []
    for c in schema_compare(a, b)["common"]:
        num = pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c])
        r = {"column": c, "dtype_raw": str(a[c].dtype), "dtype_clean": str(b[c].dtype), "missing_raw": int(a[c].isna().sum()), "missing_clean": int(b[c].isna().sum()),
             "unique_raw": int(a[c].nunique()), "unique_clean": int(b[c].nunique()),
             "mean_raw": float(a[c].mean()) if num else np.nan, "mean_clean": float(b[c].mean()) if num else np.nan}
        r["changed"] = (r["missing_raw"] != r["missing_clean"]) or (r["unique_raw"] != r["unique_clean"]) or (r["dtype_raw"] != r["dtype_clean"]) \
            or (num and not np.isclose(r["mean_raw"], r["mean_clean"], equal_nan=True))
        rows.append(r)
    return pd.DataFrame(rows)


def correlations(df: pd.DataFrame, cols=None, method: str = "pearson") -> pd.DataFrame:
    cols = cols or list(df.select_dtypes("number").columns)
    return df[cols].corr(method=method)


def pct_change(old, new):
    """Percentage change, or None when not meaningful (non-numeric or zero baseline)."""
    try:
        old, new = float(old), float(new)
    except (TypeError, ValueError):
        return None
    return None if old == 0 else 100 * (new - old) / old
