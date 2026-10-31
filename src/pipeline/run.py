"""Reproducible data pipeline for IEEE-CIS-format transaction files: load -> validate -> clean -> transform -> aggregate -> write.

Runs out of the box on the FICTIONAL file examples/synthetic_transactions.csv, and on your own copy of the Kaggle
IEEE-CIS `train_transaction.csv` (downloaded with your own Kaggle account; it is never redistributed here).

It does NOT score transactions. The frozen Phase 4 model is not part of this repository, and synthetic rows must never be
scored as if they were real customers. Model results in this project come from the historical evaluation documented in
docs/MODEL_EVALUATION.md.

    python -m src.pipeline.run --input examples/synthetic_transactions.csv --out outputs/pipeline_demo
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from bfi9 import quality  # existing, unit-tested data-quality KPIs (reused, not re-implemented)

REQUIRED = ["TransactionID", "TransactionDT", "TransactionAmt", "ProductCD"]
OPTIONAL = ["card4", "card6", "P_emaildomain", "isFraud", "data_origin"]
PRODUCT_CODES = {"W", "C", "R", "H", "S"}  # the five ProductCD values present in IEEE-CIS
SECONDS_PER_DAY = 86400  # TransactionDT is seconds from an undisclosed reference: only a RELATIVE day exists


def load(path: str | Path) -> pd.DataFrame:
    """Read only the columns the pipeline uses (the full IEEE-CIS file has 394 columns)."""
    return pd.read_csv(path, usecols=lambda c: c in REQUIRED + OPTIONAL, low_memory=False)


def validate(df: pd.DataFrame) -> dict:
    """Schema + row-level rules. Missing required columns stop the run; bad rows are counted, then removed by clean()."""
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        return {"ok": False, "fatal": f"missing required columns: {missing}", "row_issues": {}}
    num = {c: pd.to_numeric(df[c], errors="coerce") for c in ("TransactionID", "TransactionDT", "TransactionAmt")}
    issues = {
        "TransactionID not a positive integer": ~((num["TransactionID"] > 0) & (num["TransactionID"] % 1 == 0)),
        "duplicate TransactionID": df["TransactionID"].duplicated(keep="first"),
        "TransactionDT not a non-negative integer": ~((num["TransactionDT"] >= 0) & (num["TransactionDT"] % 1 == 0)),
        "TransactionAmt missing or not positive": ~(num["TransactionAmt"] > 0),
    }
    warnings = {"ProductCD outside W/C/R/H/S": int((~df["ProductCD"].isin(PRODUCT_CODES)).sum())}
    if "isFraud" in df:
        issues["isFraud not 0/1"] = ~df["isFraud"].isin([0, 1])
    bad = pd.concat(issues, axis=1).any(axis=1)
    return {"ok": True, "fatal": None, "row_issues": {k: int(v.sum()) for k, v in issues.items()},
            "rows_failing_any_rule": int(bad.sum()), "warnings": warnings, "_bad_mask": bad}


def clean(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Drop the rows that failed a rule (counts are already in the report) and fix dtypes. Never fills values."""
    out = df.loc[~report["_bad_mask"]].copy()
    out["TransactionID"] = out["TransactionID"].astype("int64")
    out["TransactionDT"] = out["TransactionDT"].astype("int64")
    out["TransactionAmt"] = out["TransactionAmt"].astype(float)
    if "isFraud" in out:
        out["isFraud"] = out["isFraud"].astype("int8")
    return out


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Add the relative day used across the dashboard (TransactionDT // 86400). It is never converted to a date."""
    return df.assign(relative_day=df["TransactionDT"] // SECONDS_PER_DAY)


def aggregate(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    agg = {"transactions": ("TransactionID", "size"), "total_amount": ("TransactionAmt", "sum"), "median_amount": ("TransactionAmt", "median")}
    if "isFraud" in df:
        agg["label_rate"] = ("isFraud", "mean")
    daily = df.groupby("relative_day").agg(**agg).reset_index()
    mix = df["ProductCD"].value_counts().rename_axis("ProductCD").reset_index(name="transactions")
    mix["share"] = mix["transactions"] / mix["transactions"].sum()
    return {"daily_summary": daily, "product_mix": mix}


def run(input_path: str | Path, out_dir: str | Path) -> dict:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    raw = load(input_path)
    report = validate(raw)
    summary = {"input": Path(input_path).name, "rows_in": int(len(raw)),
               "data_origin": sorted(raw["data_origin"].dropna().astype(str).unique()) if "data_origin" in raw else ["not stated"]}
    if not report["ok"]:
        summary.update(status="failed", reason=report["fatal"])
        (out / "pipeline_report.json").write_text(json.dumps(summary, indent=1))
        return summary
    df = transform(clean(raw, report))
    tables = aggregate(df)
    df.to_csv(out / "clean_transactions.csv", index=False)
    for name, t in tables.items():
        t.to_csv(out / f"{name}.csv", index=False)
    summary.update(status="ok", rows_out=int(len(df)), rows_removed=int(len(raw) - len(df)),
                   row_issues=report["row_issues"], warnings=report["warnings"],
                   quality_after_cleaning=quality.kpis(df, label="isFraud", id_col="TransactionID"),
                   relative_days=int(df["relative_day"].nunique()), outputs=sorted(p.name for p in out.glob("*.csv")),
                   notes=["No model scoring is performed by this pipeline.",
                          "If data_origin is SYNTHETIC, labels are random and carry no fraud signal."])
    (out / "pipeline_report.json").write_text(json.dumps(summary, indent=1, default=float))
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--input", default="examples/synthetic_transactions.csv")
    p.add_argument("--out", default="outputs/pipeline_demo")
    a = p.parse_args(argv)
    s = run(a.input, a.out)
    print(json.dumps({k: s[k] for k in ("status", "rows_in", "rows_out", "rows_removed", "data_origin") if k in s}))
    return 0 if s["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
