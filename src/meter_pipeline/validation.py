"""Validate external feeds before cleaning or writing any readings."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .generate import SITES

REQUIRED_COLUMNS = ("meter_id", "site_id", "ts", "value", "ingested_at")


def validate_raw(raw: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized copy, with timestamps stored as naive UTC.

    Naive timestamps are interpreted as UTC; offset timestamps are converted to
    UTC. Unknown site profiles and invalid values fail the entire batch.
    """
    missing = set(REQUIRED_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    result = raw.loc[:, list(REQUIRED_COLUMNS)].copy()
    for column in ("meter_id", "site_id"):
        valid = result[column].map(lambda value: isinstance(value, str) and bool(value.strip()))
        if not valid.all():
            raise ValueError(f"{column} must contain non-empty strings")
        result[column] = result[column].str.strip()
    unknown = set(result["site_id"]) - set(SITES)
    if unknown:
        raise ValueError("Unknown site_id: " + ", ".join(sorted(unknown)))
    if (result.groupby("meter_id")["site_id"].nunique() > 1).any():
        raise ValueError("Each meter_id must belong to exactly one site_id")
    for column in ("ts", "ingested_at"):
        try:
            result[column] = pd.to_datetime(
                result[column], format="mixed", utc=True, errors="raise"
            ).dt.tz_localize(None)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"{column} must contain valid timestamps") from exc
        if result[column].isna().any():
            raise ValueError(f"{column} must not contain missing timestamps")
    if (result["ts"] != result["ts"].dt.floor("15min")).any():
        raise ValueError("ts must align to a 15-minute UTC interval")
    if (result["ingested_at"] < result["ts"]).any():
        raise ValueError("ingested_at must not precede ts")
    if result["value"].map(lambda value: isinstance(value, (bool, np.bool_))).any():
        raise ValueError("value must contain finite non-negative numbers")
    try:
        result["value"] = pd.to_numeric(result["value"], errors="raise").astype(float)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("value must contain finite non-negative numbers") from exc
    if not np.isfinite(result["value"]).all() or (result["value"] < 0).any():
        raise ValueError("value must contain finite non-negative numbers")
    return result
