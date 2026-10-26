# Processing a CSV feed

The CLI can process a CSV instead of generating a demo. The included sample is
synthetic and contains only two intervals per meter: it demonstrates ingestion,
not an anomaly benchmark.

```bash
meter-anomaly --input examples/readings.csv --db readings.duckdb --json-output reports/latest.json
```

The command prints its quality report and findings, persists normalized readings,
and writes JSON containing `input_mode`, `until`, `findings_scope`, `stored_rows`,
`quality`, `findings`, and `evaluation`. Quality counts describe this input batch;
findings and stored row counts describe the entire database after the upsert.
CSV reports have `evaluation: null` because the source has no labelled truth.
An empty finding list can also mean there is insufficient history: drift needs
at least 10 eligible weekdays and overnight detection needs at least 14 nights.

## Input contract

| Column | Required value |
|---|---|
| `meter_id` | Non-empty string, belonging to one site in this batch |
| `site_id` | `S1`, `S2`, or `S3`; profiles below |
| `ts` | Interval timestamp on a 15-minute UTC boundary |
| `value` | Finite, non-negative number in the site's configured unit |
| `ingested_at` | Arrival timestamp at or after `ts` |

| Profile | Unit | Measurement mode |
|---|---|---|
| `S1` | kWh | Interval consumption |
| `S2` | Wh | Interval consumption, converted to kWh |
| `S3` | kWh | Cumulative counter, converted to differences |

These are the existing demo site profiles, not automatic device discovery. Adapt
`generate.SITES` and validate the configuration before importing other site types.
Meter identifiers must remain assigned to the same profile across runs; the
database stores normalized readings and does not enforce a persistent site registry.

Timestamps without offsets are interpreted as UTC. Offset timestamps are converted
to UTC before storage. Convert local civil times with an explicit offset when
daylight-saving transitions matter. Additional CSV columns are ignored.

The whole batch is validated before readings are written. Invalid columns,
timestamps, readings, or profiles cause an error and exit code 2. Negative counter
values are invalid; a drop between non-negative counter readings is a reset.
Duplicates keep the most recently received row. For equal arrival timestamps,
the last row in the input wins deterministically. The caller's DataFrame is not
modified by validation.

## Arrival cutoffs and reruns

```bash
meter-anomaly --input examples/readings.csv --db readings.duckdb --until 2026-01-05T00:10:00Z
meter-anomaly --input examples/readings.csv --db readings.duckdb --json-output reports/latest.json
```

Supply the full raw history for the meters being recomputed on every backfill.
The cleaner reconstructs counter gaps from adjacent raw readings; this is not a
delta-only ingestion API. An early cutoff with no arrivals is valid. A cutoff
limits this batch; it does not delete rows already stored by a later run.
Rerunning the same history upserts existing meter/timestamp keys without creating
duplicates. It does not delete readings removed from the source history.

Synthetic evaluation is included only for the full demo in an in-memory database.
It is omitted for CSV input, cutoff runs, or persistent databases, where a full
ground-truth comparison would be misleading.

JSON output cannot point at the input or database path. Parent directories are
created as needed; an existing report at a different path is replaced. A report
write error can occur after database processing completes: reports and database
writes are not a shared transaction. For untrusted feeds, also bound input size
and history length upstream; missing intervals are materialized in memory.
