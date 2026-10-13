"""Two checks that matter to a customer: drifting meters and machines running at night."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Finding:
    meter_id: str
    kind: str  # "drift" or "overnight"
    detail: str


def _usable(readings: pd.DataFrame) -> pd.DataFrame:
    df = readings[readings["quality"].isin(["ok", "estimated"])].copy()
    df["date"] = df["ts"].dt.normalize()
    return df


def detect_drift(readings: pd.DataFrame, min_slope: float = 0.004, min_r2: float = 0.6):
    """Flag meters whose weekday use keeps climbing day after day.

    Weekday working hours only (07:00 to 18:00), so the weekly pattern and a night time
    step change do not look like a trend. A meter is flagged
    when the trend explains most of the movement and rises faster than `min_slope`
    (share of its typical daily use, per day). Days are compared on average load per
    interval, so a day with a few missing readings does not look like a dip.
    """
    df = _usable(readings)
    df = df[(df["ts"].dt.dayofweek < 5) & (df["ts"].dt.hour >= 7) & (df["ts"].dt.hour < 18)]
    out = []
    for mid, g in df.groupby("meter_id"):
        daily = g.groupby("date")["kwh"].agg(["mean", "count"])
        daily = daily[daily["count"] >= 36]  # skip days with too much missing data (44 per day)
        if len(daily) < 10:
            continue
        y = daily["mean"].to_numpy() / daily["mean"].median()
        x = np.arange(len(y), dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        fit = slope * x + intercept
        ss_res = float(((y - fit) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        if slope > min_slope and r2 > min_r2:
            out.append(Finding(mid, "drift", f"weekday use rising {slope * 100:.2f}% per day (R2 {r2:.2f}, {len(y)} weekdays)"))
    return out


def detect_overnight(readings: pd.DataFrame, ratio: float = 1.5, min_increase: float = 0.2):
    """Flag meters whose night time load (00:00 to 05:00) stepped up recently.

    Compares the last 7 days with the first 7 days of the same meter.
    """
    df = _usable(readings)
    df = df[df["ts"].dt.hour < 5]
    out = []
    for mid, g in df.groupby("meter_id"):
        nightly = g.groupby("date")["kwh"].mean()
        if len(nightly) < 14:
            continue
        before, after = nightly.iloc[:7].mean(), nightly.iloc[-7:].mean()
        if after - before > min_increase and after / before > ratio:
            out.append(Finding(mid, "overnight", f"night load {before:.2f} to {after:.2f} kWh per interval ({after / before:.1f}x)"))
    return out


def detect_all(readings: pd.DataFrame) -> list[Finding]:
    return detect_drift(readings) + detect_overnight(readings)
