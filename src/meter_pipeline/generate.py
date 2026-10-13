"""Synthetic meter data with the problems real feeds have.

Everything here is made up. The point is to have messy input with known
problems, so the cleaning and detection steps can be checked against the truth.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

INTERVAL = pd.Timedelta(minutes=15)

# Each site is configured differently, as in real life.
SITES = {
    "S1": {"unit": "kWh", "mode": "interval"},
    "S2": {"unit": "Wh", "mode": "interval"},
    "S3": {"unit": "kWh", "mode": "cumulative"},
}
METERS_PER_SITE = 4


def meter_ids() -> list[tuple[str, str]]:
    out = []
    n = 1
    for site in SITES:
        for _ in range(METERS_PER_SITE):
            out.append((f"M{n:02d}", site))
            n += 1
    return out


def generate(seed: int = 7, days: int = 28, start: str = "2026-01-05"):
    """Return (raw readings, truth). Start is a Monday."""
    if days < 2:
        raise ValueError("days must be at least 2 to generate gaps in the demo feed")
    rng = np.random.default_rng(seed)
    grid = pd.date_range(start, periods=days * 96, freq="15min")
    frames = []
    truth = {"drift": ["M05"], "overnight": ["M08"], "reset": ["M10"]}

    for mid, site in meter_ids():
        base = rng.uniform(0.4, 1.2)
        bump = rng.uniform(0.8, 2.0)
        hour = grid.hour + grid.minute / 60
        weekday = grid.dayofweek < 5
        working = weekday & (hour >= 7) & (hour < 18)
        kwh = base + bump * working + rng.normal(0, 0.05, len(grid))
        kwh = np.clip(kwh, 0.05, None)
        day_idx = (grid - grid[0]).days.values

        if mid in truth["drift"]:  # slow upward drift from day 7
            kwh = kwh * (1 + 0.006 * np.clip(day_idx - 7, 0, None))
        if mid in truth["overnight"]:  # machine left running at night from day 14
            night = (hour < 5) & (day_idx >= 14)
            kwh = kwh + 0.9 * night

        cfg = SITES[site]
        value = kwh.copy()
        if cfg["mode"] == "cumulative":
            value = np.cumsum(kwh) + rng.uniform(1000, 5000)
            if mid in truth["reset"] and days > 20:  # counter rolls back to zero on day 20
                k = 20 * 96
                value[k:] = value[k:] - value[k] + kwh[k]
        if cfg["unit"] == "Wh":
            value = value * 1000

        df = pd.DataFrame({"meter_id": mid, "site_id": site, "ts": grid, "value": value})
        # arrival time: mostly within minutes, some readings arrive a day or more late
        delay = pd.to_timedelta(rng.integers(1, 10, len(df)), unit="min")
        late = rng.random(len(df)) < 0.03
        delay = delay + pd.to_timedelta(np.where(late, rng.integers(6, 40, len(df)), 0), unit="h")
        df["ingested_at"] = df["ts"] + delay

        # missing readings: a few gaps of 2 to 12 intervals
        keep = np.ones(len(df), dtype=bool)
        for _ in range(4):
            s = int(rng.integers(100, len(df) - 20))
            keep[s : s + int(rng.integers(2, 13))] = False
        df = df[keep]

        # duplicates, sent again a bit later
        dup = df.sample(frac=0.015, random_state=int(rng.integers(0, 10_000))).copy()
        dup["ingested_at"] = dup["ingested_at"] + pd.Timedelta(minutes=30)
        frames.append(pd.concat([df, dup]))

    raw = pd.concat(frames).sort_values(["ingested_at", "meter_id"]).reset_index(drop=True)
    return raw, truth
