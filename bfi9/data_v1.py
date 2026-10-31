"""BFI v1 (Indian banking) data, read-only. Separate project from v2: never joined with IEEE-CIS rows."""
from __future__ import annotations

import zipfile
from functools import lru_cache

import pandas as pd

from . import settings as S

LABEL, ID, DATE = "is_fraud", "transaction_id", "transaction_date"


def status() -> dict:
    return {"raw": S.V1_RAW_ZIP.is_file(), "cleaned": S.V1_CLEAN.is_file(), "synthetic_770k": S.V1_SYNTH_ZIP.is_file()}


@lru_cache(maxsize=1)
def raw() -> pd.DataFrame | None:
    """indian_banking_transactions.csv streamed out of the ZIP (the ZIP is never extracted or modified)."""
    if not S.V1_RAW_ZIP.is_file():
        return None
    with zipfile.ZipFile(S.V1_RAW_ZIP) as z, z.open(S.V1_RAW_MEMBER) as f:
        return pd.read_csv(f, low_memory=False)


@lru_cache(maxsize=1)
def cleaned() -> pd.DataFrame | None:
    """Phase 3 cleaned/sorted CSV, read as-is."""
    return pd.read_csv(S.V1_CLEAN, low_memory=False) if S.V1_CLEAN.is_file() else None


def get(name: str) -> pd.DataFrame | None:
    return {"raw": raw, "cleaned": cleaned}[name]()


def sample(df: pd.DataFrame, n: int, seed: int = 0) -> pd.DataFrame:
    """Plot-sized random sample (fixed seed -> reproducible charts)."""
    return df if len(df) <= n else df.sample(n, random_state=seed)
