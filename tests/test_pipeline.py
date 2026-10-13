import pandas as pd
import pytest

from meter_pipeline import store
from meter_pipeline.clean import clean
from meter_pipeline.detect import detect_all
from meter_pipeline.evals import score
from meter_pipeline.generate import generate


def _raw(rows):
    return pd.DataFrame(rows, columns=["meter_id", "site_id", "ts", "value", "ingested_at"]).astype(
        {"ts": "datetime64[ns]", "ingested_at": "datetime64[ns]"}
    )


def test_duplicates_keep_latest_and_wh_converted():
    raw = _raw(
        [
            ("M05", "S2", "2026-01-05 00:00", 1000.0, "2026-01-05 00:05"),
            ("M05", "S2", "2026-01-05 00:00", 1500.0, "2026-01-05 00:35"),
            ("M05", "S2", "2026-01-05 00:15", 2000.0, "2026-01-05 00:20"),
        ]
    )
    out, rep = clean(raw)
    assert rep.duplicates_removed == 1
    assert out["kwh"].tolist() == [1.5, 2.0]


def test_missing_interval_is_not_invented_for_interval_meters():
    raw = _raw(
        [
            ("M01", "S1", "2026-01-05 00:00", 1.0, "2026-01-05 00:05"),
            ("M01", "S1", "2026-01-05 00:30", 1.0, "2026-01-05 00:35"),
        ]
    )
    out, rep = clean(raw)
    assert rep.missing_intervals == 1
    assert out.loc[out["quality"] == "missing", "kwh"].isna().all()


def test_cumulative_gap_is_spread_and_reset_is_flagged():
    raw = _raw(
        [
            ("M09", "S3", "2026-01-05 00:00", 100.0, "2026-01-05 00:05"),
            ("M09", "S3", "2026-01-05 00:15", 101.0, "2026-01-05 00:20"),
            ("M09", "S3", "2026-01-05 00:45", 104.0, "2026-01-05 00:50"),  # two readings missing
            ("M09", "S3", "2026-01-05 01:00", 2.0, "2026-01-05 01:05"),  # counter reset
        ]
    )
    out, rep = clean(raw)
    q = out.set_index("ts")
    assert q.loc["2026-01-05 00:15", "kwh"] == 1.0
    assert q.loc["2026-01-05 00:30", "quality"] == "estimated"
    assert q.loc["2026-01-05 00:30", "kwh"] == 1.5
    assert q.loc["2026-01-05 00:45", "kwh"] == 1.5
    assert rep.counter_resets == 1


def test_rerun_changes_nothing_and_incremental_converges_to_full_run():
    raw, _ = generate(days=10)
    full = store.connect()
    store.run(full, raw)
    store.run(full, raw)  # same input again
    expected = store.load(full)
    assert len(expected) == full.execute("SELECT count(*) FROM readings").fetchone()[0]

    inc = store.connect()
    for day in (3, 6, 9):
        store.run(inc, raw, until=raw["ts"].min() + pd.Timedelta(days=day))
    store.run(inc, raw)  # late readings from the last days arrive
    got = store.load(inc)
    pd.testing.assert_frame_equal(got, expected)


def test_detection_finds_injected_problems_without_false_alarms():
    raw, truth = generate()
    con = store.connect()
    store.run(con, raw)
    result = score(detect_all(store.load(con)), truth)
    assert result["recall"] == 1.0
    assert result["false_positives"] == []


def test_clean_meters_are_not_flagged():
    raw, truth = generate(seed=3)
    con = store.connect()
    store.run(con, raw)
    flagged = {f.meter_id for f in detect_all(store.load(con))}
    assert flagged == set(truth["drift"]) | set(truth["overnight"])


def test_cutoff_before_first_arrival_is_safe():
    raw = _raw([("M01", "S1", "2026-01-05 00:00", 1.0, "2026-01-05 00:05")])
    with store.connect() as con:
        report = store.run(con, raw, until=pd.Timestamp("2026-01-04"))
        assert report.rows_in == 0
        assert store.load(con).empty
        assert detect_all(store.load(con)) == []
        store.run(con, raw)
        assert len(store.load(con)) == 1


@pytest.mark.parametrize("days", [0, 1, -1])
def test_generator_rejects_too_short_windows(days):
    with pytest.raises(ValueError, match="at least 2"):
        generate(days=days)
