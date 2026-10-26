"""Standardise readings from differently configured sites into 15 minute kWh."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .generate import INTERVAL, SITES
from .validation import validate_raw

LATE_AFTER = pd.Timedelta(hours=1)


@dataclass
class QualityReport:
    rows_in: int
    duplicates_removed: int
    late_rows: int
    missing_intervals: int
    estimated_intervals: int
    counter_resets: int

    def lines(self) -> list[str]:
        return [
            f"rows in              {self.rows_in}",
            f"duplicates removed   {self.duplicates_removed}",
            f"late rows (>1h)      {self.late_rows}",
            f"missing intervals    {self.missing_intervals}",
            f"estimated intervals  {self.estimated_intervals}",
            f"counter resets       {self.counter_resets}",
        ]


def _one_meter(g: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    g = g.sort_values("ts").set_index("ts")
    value = g["value"] / (1000.0 if cfg["unit"] == "Wh" else 1.0)
    grid = pd.date_range(g.index.min(), g.index.max(), freq=INTERVAL)
    out = pd.DataFrame(index=grid)
    out["kwh"] = np.nan
    out["quality"] = "missing"

    if cfg["mode"] == "interval":
        out.loc[value.index, "kwh"] = value.values
        out.loc[value.index, "quality"] = "ok"
        return out

    # Cumulative counter: energy in an interval is the difference between readings.
    delta = value.diff()
    steps = (value.index.to_series().diff() / INTERVAL).round()
    reset = delta < 0
    per_step = (delta / steps).where(~reset)
    for ts, v in per_step.dropna().items():
        n = int(steps[ts])
        span = pd.date_range(ts - (n - 1) * INTERVAL, ts, freq=INTERVAL)
        out.loc[span, "kwh"] = v
        out.loc[span, "quality"] = "ok" if n == 1 else "estimated"
    out.loc[value.index[reset.values], "quality"] = "reset"
    out.loc[out["quality"] == "reset", "kwh"] = np.nan
    return out


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, QualityReport]:
    """Return one row per meter and 15 minute interval, plus a quality report."""
    raw = validate_raw(raw)
    if raw.empty:
        empty = pd.DataFrame({
            "meter_id": pd.Series(dtype="str"),
            "ts": pd.Series(dtype="datetime64[ns]"),
            "kwh": pd.Series(dtype="float64"),
            "quality": pd.Series(dtype="str"),
        })
        return empty, QualityReport(0, 0, 0, 0, 0, 0)
    rows_in = len(raw)
    late_rows = int(((raw["ingested_at"] - raw["ts"]) > LATE_AFTER).sum())

    # Duplicates: keep the most recently received row for each meter and timestamp.
    deduped = raw.sort_values("ingested_at", kind="stable").drop_duplicates(["meter_id", "ts"], keep="last")
    removed = rows_in - len(deduped)

    parts = []
    for mid, g in deduped.groupby("meter_id"):
        cfg = SITES[g["site_id"].iloc[0]]
        part = _one_meter(g, cfg)
        part["meter_id"] = mid
        parts.append(part.rename_axis("ts").reset_index())
    out = pd.concat(parts, ignore_index=True)[["meter_id", "ts", "kwh", "quality"]]

    q = out["quality"]
    report = QualityReport(
        rows_in=rows_in,
        duplicates_removed=removed,
        late_rows=late_rows,
        missing_intervals=int((q == "missing").sum()),
        estimated_intervals=int((q == "estimated").sum()),
        counter_resets=int((q == "reset").sum()),
    )
    return out, report
