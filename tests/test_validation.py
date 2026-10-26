import numpy as np
import pandas as pd
import pytest

from meter_pipeline import store
from meter_pipeline.clean import clean
from meter_pipeline.validation import validate_raw


@pytest.fixture
def raw():
    return pd.DataFrame({
        "meter_id": ["M01"], "site_id": ["S1"],
        "ts": ["2026-01-05T00:00:00Z"], "value": [1.0],
        "ingested_at": ["2026-01-05T00:05:00Z"],
    })


@pytest.mark.parametrize("column,value,message", [
    ("meter_id", None, "meter_id"), ("meter_id", " ", "meter_id"),
    ("site_id", "unknown", "Unknown site_id"),
    ("ts", "bad", "valid timestamps"), ("ts", None, "missing timestamps"),
    ("ts", "2026-01-05T00:01:00Z", "15-minute"),
    ("ingested_at", "2026-01-04", "must not precede"),
    ("value", -1, "finite non-negative"), ("value", np.inf, "finite non-negative"),
    ("value", np.nan, "finite non-negative"), ("value", "bad", "finite non-negative"),
    ("value", True, "finite non-negative"),
])
def test_invalid_batch_does_not_modify_database(raw, column, value, message):
    with store.connect() as con:
        store.run(con, raw)
        expected = store.load(con)
        bad = raw.astype(object)
        bad.loc[0, column] = value
        with pytest.raises(ValueError, match=message):
            store.run(con, bad)
        pd.testing.assert_frame_equal(store.load(con), expected)


def test_missing_columns_are_named(raw):
    with pytest.raises(ValueError, match="Missing required columns: value"):
        clean(raw.drop(columns="value"))


def test_mixed_site_profiles_for_one_meter_are_rejected(raw):
    other = raw.assign(site_id="S2")
    with pytest.raises(ValueError, match="exactly one site_id"):
        clean(pd.concat([raw, other], ignore_index=True))


def test_offsets_are_normalized_without_mutating_input(raw):
    original = raw.copy(deep=True)
    normalized = validate_raw(raw.assign(
        ts="2026-01-05T01:00:00+01:00", ingested_at="2026-01-05T01:05:00+01:00"
    ))
    assert normalized.ts.iloc[0] == pd.Timestamp("2026-01-05T00:00:00")
    pd.testing.assert_frame_equal(raw, original)


def test_equal_arrival_duplicates_use_last_input_row(raw):
    out, report = clean(pd.concat([raw, raw.assign(value=2)], ignore_index=True))
    assert out.kwh.tolist() == [2.0]
    assert report.duplicates_removed == 1


def test_offset_cutoff_accepts_string_timestamp_feed(raw):
    with store.connect() as con:
        report = store.run(con, raw, until=pd.Timestamp("2026-01-05T01:05:00+01:00"))
        assert report.rows_in == 1
        assert len(store.load(con)) == 1
