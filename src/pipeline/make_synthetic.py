"""Generate examples/synthetic_transactions.csv: FICTIONAL rows in the IEEE-CIS column format.

Nothing here is sampled, copied or derived from IEEE-CIS rows. IDs are 9-digit values starting at 900000001 (outside the
IEEE-CIS TransactionID range), email domains are reserved example domains (RFC 2606), and `isFraud` is an independent
random draw at a 3.5% rate, so it carries NO fraud signal. Every row has data_origin = SYNTHETIC.

    python -m src.pipeline.make_synthetic --rows 2000 --out examples/synthetic_transactions.csv
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd


def make(rows: int = 2000, seed: int = 20261101, days: int = 30) -> pd.DataFrame:
    r = np.random.RandomState(seed)  # legacy RandomState: its stream is frozen across NumPy versions
    df = pd.DataFrame({
        "TransactionID": np.arange(900000001, 900000001 + rows),
        "TransactionDT": np.sort(r.randint(86400, 86400 * (days + 1), rows)),
        "TransactionAmt": np.round(r.lognormal(3.9, 1.0, rows), 2) + 0.5,
        "ProductCD": r.choice(["W", "C", "R", "H", "S"], rows, p=[0.74, 0.12, 0.06, 0.05, 0.03]),
        "card4": r.choice(["visa", "mastercard", "american express", "discover"], rows, p=[0.65, 0.3, 0.03, 0.02]),
        "card6": r.choice(["debit", "credit"], rows, p=[0.75, 0.25]),
        "P_emaildomain": r.choice(["example.com", "example.org", "example.net", None], rows, p=[0.5, 0.25, 0.1, 0.15]),
        "isFraud": (r.random_sample(rows) < 0.035).astype(int),
    })
    df["data_origin"] = "SYNTHETIC"
    return df


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Write the fictional example transactions file.")
    p.add_argument("--rows", type=int, default=2000)
    p.add_argument("--out", default="examples/synthetic_transactions.csv")
    a = p.parse_args()
    make(a.rows).to_csv(a.out, index=False)
    print(f"wrote {a.rows} SYNTHETIC rows to {a.out}")
