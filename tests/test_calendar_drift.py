"""Elapsed-time regression through the real clean/store/detect pipeline."""
import numpy as np
import pandas as pd
import pytest

from meter_pipeline import store
from meter_pipeline.detect import detect_drift


def _readings(spacing, rate, time_basis):
    dates = pd.bdate_range("2026-01-05", periods=14 * spacing)[::spacing]
    elapsed = (
        np.busday_count(dates.to_numpy(dtype="datetime64[D]")[0],
                        dates.to_numpy(dtype="datetime64[D]"))
        if time_basis == "working_day"
        else (dates - dates[0]).days.to_numpy()
    )
    values = 1 + rate * elapsed
    rows = []
    for day, value in zip(dates, values):
        for ts in pd.date_range(day + pd.Timedelta(hours=7), periods=44, freq="15min"):
            rows.append(("M01", "S1", ts, value, ts + pd.Timedelta(minutes=1)))
    raw = pd.DataFrame(rows, columns=["meter_id", "site_id", "ts", "value", "ingested_at"])
    with store.connect() as con:
        store.run(con, raw)
        return store.load(con), float(np.median(values))


@pytest.mark.parametrize("time_basis", ["working_day", "calendar_day"])
@pytest.mark.parametrize("spacing", [1, 2, 5])
@pytest.mark.parametrize("rate", [0.0, 0.001, 0.002, 0.01, 0.02])
def test_slope_uses_declared_elapsed_days(spacing, rate, time_basis):
    readings, median = _readings(spacing, rate, time_basis)
    result = detect_drift(readings, time_basis=time_basis)
    expected = rate / median > 0.004
    assert bool(result) == expected
    if expected:
        unit = time_basis.replace("_", " ")
        assert f"{rate / median * 100:.2f}% per {unit}" in result[0].detail


def test_default_keeps_working_day_interpretation():
    readings, _ = _readings(1, 0.01, "working_day")
    assert detect_drift(readings) == detect_drift(readings, time_basis="working_day")
    assert "per working day" in detect_drift(readings)[0].detail


def test_invalid_time_basis_is_rejected():
    with pytest.raises(ValueError, match="time_basis"):
        detect_drift(pd.DataFrame(), time_basis="observed_row")
