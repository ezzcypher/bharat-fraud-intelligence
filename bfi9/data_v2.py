"""BFI v2 evaluation-row frame: one row per validation/test TransactionID (175,998 expected).

Columns come only from real sources:
  Phase 4 stored scores (via Phase 8)      -> split, score, decision, risk_band, seen_user
  Phase 8 validated feature store           -> relative day, amount, ProductCD, card4, card6, P_emaildomain, n_missing_inputs
  train_identity TransactionID column       -> identity_present
isFraud is present only in evaluation mode. Nothing is invented (no dates, names, merchants, payment modes)."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import phase8

ATTR = ["TransactionDT", "TransactionAmt", "ProductCD", "card4", "card6", "P_emaildomain", "addr1", "addr2"]
CATEGORICAL = ["ProductCD", "card4", "card6", "P_emaildomain", "addr1", "addr2"]

# Requested business concepts -> what IEEE-CIS actually provides (shown in the UI so "not in dataset" is never
# confused with "no matching records").
FIELD_AVAILABILITY = [
    ("Transaction type", "partial", "ProductCD", "Masked product code (5 values). The real transaction/product type is not disclosed."),
    ("Payment channel (online/offline, UPI, POS...)", "not in dataset", "-", "IEEE-CIS contains card-not-present e-commerce only; no channel field."),
    ("Card network / card type", "available", "card4, card6", "e.g. visa/mastercard and debit/credit (masked card attributes, not customers)."),
    ("Customer attributes (age, segment, account)", "not in dataset", "identity_present", "Only whether an identity record exists; no customer profile fields."),
    ("Geography", "partial", "addr1, addr2", "Masked billing region / country codes; real place names are not disclosed."),
    ("Purchaser e-mail domain", "available", "P_emaildomain", "Domain only (e.g. gmail.com), no addresses."),
    ("Calendar date", "not in dataset", "day (relative)", "TransactionDT is seconds from an undisclosed reference."),
    ("Amount", "available", "amount_usd", "TransactionAmt in USD."),
]


@lru_cache(maxsize=1)
def _store_path():
    p = phase8.load()
    st = p.prep_raw.store_status()
    f = p.settings.FEATURE_STORE / str(st.get("store_file", ""))
    return f if st.get("inputs_valid") and f.is_file() else None


@lru_cache(maxsize=1)
def _attributes() -> pd.DataFrame | None:
    """Six filter columns + per-row missing-input count, read column-by-column (no full copy in memory)."""
    f = _store_path()
    if f is None:
        return None
    pf = pq.ParquetFile(f)
    names = pf.schema_arrow.names
    t = pf.read(columns=["TransactionID"] + [c for c in ATTR if c in names])
    df = t.to_pandas().set_index("TransactionID")
    # Step: count missing model inputs per row, one column at a time (constant extra memory)
    feats = [c for c in names if c not in ("TransactionID", "TransactionDT")]
    miss = np.zeros(len(df), dtype=np.int32)
    for c in feats:
        miss += pf.read(columns=[c]).column(0).is_null().to_numpy(zero_copy_only=False).astype(np.int32)
    df["n_missing_inputs"] = miss
    return df


@lru_cache(maxsize=1)
def _identity_ids() -> frozenset:
    p = phase8.load()
    f = p.settings.RAW_DIR / "train_identity.csv"
    return frozenset(pd.read_csv(f, usecols=["TransactionID"])["TransactionID"]) if f.is_file() else frozenset()


@lru_cache(maxsize=1)
def eval_frame() -> pd.DataFrame:
    """Joined, validated frame. Raises if the join would duplicate or drop transactions."""
    pred = phase8.predictions().rename(columns={"score_A": "score", "seen_A": "seen_user"})
    attrs = _attributes()
    if attrs is not None:
        # Step: one-to-one join check (no duplicated rows, no unmatched IDs)
        assert attrs.index.is_unique, "duplicate TransactionIDs in feature store"
        missing = pred.index.difference(attrs.index)
        assert len(missing) == 0, f"{len(missing)} scored transactions missing from the feature store"
        df = pred.join(attrs, how="left", validate="one_to_one")
        df["day"] = (df.pop("TransactionDT") // 86400).astype(int)  # relative day index (no calendar)
        df = df.rename(columns={"TransactionAmt": "amount_usd"})
        for c in ("addr1", "addr2"):   # masked numeric codes -> categorical labels (exact codes kept, no meaning invented)
            if c in df:
                df[c] = df[c].astype("Int64").astype("string").astype(object).where(df[c].notna(), None)
    else:
        df = pred
    ids = _identity_ids()
    df["identity_present"] = df.index.isin(ids) if ids else pd.NA
    assert len(df) == len(pred) and df.index.is_unique
    df.attrs["sources"] = {"scores": "Phase 4 stored predictions via Phase 8 data_access.predictions()",
                           "attributes": "Phase 8 feature store (validated)" if attrs is not None else "UNAVAILABLE",
                           "identity": "train_identity.csv TransactionID column" if ids else "UNAVAILABLE"}
    return df


def available_filters(df: pd.DataFrame) -> list[str]:
    """Only offer filters whose columns exist in the frame."""
    cand = ["split", "day", "score", "risk_band", "decision", "amount_usd", *CATEGORICAL, "identity_present", "n_missing_inputs", "isFraud"]
    return [c for c in cand if c in df.columns and df[c].notna().any()]


def daily_counts(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per relative day: transactions and alerts (no labels)."""
    df = eval_frame() if df is None else df
    if "day" not in df:
        return pd.DataFrame()
    g = df.groupby("day").agg(transactions=("score", "size"), alerts=("decision", lambda s: int((s != "no alert").sum())),
                              mean_score=("score", "mean"), split=("split", "first"))
    return g.reset_index()
