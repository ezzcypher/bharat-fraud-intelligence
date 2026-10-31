"""Pipeline tests on FICTIONAL data only (no licensed IEEE-CIS rows, no model)."""
import io
import json
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline import make_synthetic, run as pipe

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic_transactions.csv"


def test_example_file_is_synthetic_and_fictional():
    df = pd.read_csv(EXAMPLE)
    assert (df["data_origin"] == "SYNTHETIC").all()
    assert df["TransactionID"].min() >= 900000001  # outside the IEEE-CIS TransactionID range
    assert set(df["P_emaildomain"].dropna()) <= {"example.com", "example.org", "example.net"}


def test_example_file_matches_generator():
    pd.testing.assert_frame_equal(pd.read_csv(EXAMPLE), pd.read_csv(io.StringIO(make_synthetic.make(2000).to_csv(index=False))))


def test_pipeline_runs_end_to_end_on_synthetic(tmp_path):
    s = pipe.run(EXAMPLE, tmp_path)
    assert s["status"] == "ok" and s["rows_in"] == 2000 and s["rows_out"] + s["rows_removed"] == 2000
    assert s["data_origin"] == ["SYNTHETIC"]
    daily = pd.read_csv(tmp_path / "daily_summary.csv")
    assert daily["transactions"].sum() == s["rows_out"]
    assert json.loads((tmp_path / "pipeline_report.json").read_text())["status"] == "ok"
    assert pd.read_csv(tmp_path / "product_mix.csv")["share"].sum() == pytest.approx(1.0)


def test_bad_rows_are_counted_and_removed(tmp_path):
    df = make_synthetic.make(20).astype({"TransactionDT": float})
    df.loc[1, "TransactionID"] = df.loc[0, "TransactionID"]  # duplicate id
    df.loc[2, "TransactionAmt"] = -5                          # negative amount
    df.loc[3, "TransactionDT"] = 1.5                          # non-integer time
    df.loc[4, "isFraud"] = 7                                   # invalid label
    df.to_csv(tmp_path / "in.csv", index=False)
    s = pipe.run(tmp_path / "in.csv", tmp_path / "out")
    assert s["rows_removed"] == 4 and s["rows_out"] == 16
    assert s["row_issues"]["duplicate TransactionID"] == 1 and s["row_issues"]["isFraud not 0/1"] == 1


def test_missing_required_column_stops_without_outputs(tmp_path):
    make_synthetic.make(10).drop(columns="TransactionAmt").to_csv(tmp_path / "in.csv", index=False)
    s = pipe.run(tmp_path / "in.csv", tmp_path / "out")
    assert s["status"] == "failed" and "TransactionAmt" in s["reason"]
    assert not list((tmp_path / "out").glob("*.csv"))


def test_relative_day_is_never_a_date():
    out = pipe.transform(pd.DataFrame({"TransactionDT": [0, 86399, 86400, 172800]}))
    assert out["relative_day"].tolist() == [0, 0, 1, 2]
