# Meter Anomaly Pipeline

A small Python pipeline that takes messy energy meter readings, cleans them into one standard format and flags two things a customer would care about:

- a **drifting meter**: weekday use that keeps creeping up day after day
- a **machine running at night**: night time load that stepped up and stayed up

It uses **synthetic data**. Nothing here comes from a real site or real hardware. The generator injects known problems so every step can be checked against the truth.

## What the feed looks like

| Problem | How it is handled |
|---|---|
| Sites report in different units (kWh or Wh) | Converted to kWh |
| Some sites send interval values, others a running counter | Counters are turned into 15 minute values |
| Counter resets to zero | The reset interval is flagged, not turned into negative energy |
| Duplicate readings | The most recently received row wins |
| Late readings (arrive hours or a day after the timestamp) | Picked up by the next run, which fills the gap they belong to |
| Missing readings | Marked `missing` for interval meters. Counter gaps are spread evenly and marked `estimated` |

## How it works

```
raw readings -> clean (units, counters, duplicates, gaps) -> DuckDB upsert -> detect -> check vs truth
```

- `generate.py` builds 12 meters over 3 differently configured sites with injected problems.
- `clean.py` standardises to 15 minute kWh and returns a quality report.
- `store.py` writes to DuckDB with a primary key on meter and timestamp. Writes are upserts, so running the same input twice changes nothing and a backfill is the same call with a later cut off.
- `detect.py` has the two checks. Drift is a trend on weekday working hours only, so a night time change does not look like drift. The night check compares the last 7 days with the first 7.
- `evals.py` scores the findings against the injected problems.

## Run it

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m meter_pipeline          # demo on synthetic data
python -m pytest                                  # 6 tests
```

Example output:

```
DATA QUALITY
rows in              32397
duplicates removed   480
late rows (>1h)      958
missing intervals    237
estimated intervals  121
counter resets       1

FINDINGS
M05  drift     weekday use rising 0.67% per day (R2 0.84, 20 weekdays)
M08  overnight night load 0.77 to 1.68 kWh per interval (2.2x)
```

## Honest limits

- The data is synthetic and the injected problems are clean. Precision and recall of 1.0 on the demo only show the code does what it was written to do, not how it would do on a real site. I tried seven seeds and all gave 1.0, but that is still the same generator.
- The thresholds are hand picked. Real meters would need them tuned per site.
- Batch only. There is no streaming and no real meter protocol such as Modbus or M-Bus.
- Anomaly detection is rule based, not a trained model.

> These are the original implementation notes. Use the main README for the current installation commands and docs/demo-output.txt for newly verified results.
