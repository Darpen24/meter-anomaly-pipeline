"""DuckDB storage. Writes are upserts, so reruns and backfills are safe."""
from __future__ import annotations

import duckdb
import pandas as pd

from .clean import clean


def connect(path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(path)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            meter_id VARCHAR,
            ts TIMESTAMP,
            kwh DOUBLE,
            quality VARCHAR,
            PRIMARY KEY (meter_id, ts)
        )
        """
    )
    return con


def upsert(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    con.register("incoming", df)
    con.execute("INSERT OR REPLACE INTO readings SELECT meter_id, ts, kwh, quality FROM incoming")
    con.unregister("incoming")


def load(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("SELECT * FROM readings ORDER BY meter_id, ts").df()


def run(con: duckdb.DuckDBPyConnection, raw: pd.DataFrame, until: pd.Timestamp | None = None):
    """Process everything received up to `until`. Running it again changes nothing.

    A reading that arrives late is simply picked up by a later run and replaces the
    gap it belongs to. A backfill is the same call with a later `until`.
    """
    seen = raw if until is None else raw[raw["ingested_at"] <= until]
    cleaned, report = clean(seen)
    upsert(con, cleaned)
    return report
