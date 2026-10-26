from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import duckdb

from . import store
from .detect import detect_all
from .evals import score
from .generate import generate


def main() -> None:
    p = argparse.ArgumentParser(description="Clean meter readings and detect consumption anomalies")
    p.add_argument("--input", type=Path, help="CSV feed; omit to run the synthetic demo")
    p.add_argument("--seed", type=int, default=7, help="Synthetic demo seed (default: 7)")
    p.add_argument("--days", type=int, default=28, help="Synthetic demo days (default: 28)")
    p.add_argument("--db", default=":memory:", help="DuckDB file (default: in memory)")
    p.add_argument("--until", help="Include arrivals up to this timestamp; naive times mean UTC")
    p.add_argument("--json-output", type=Path, help="Write quality, findings and row counts as JSON")
    args = p.parse_args()

    # Prevent report output from overwriting the source feed or the database.
    if args.json_output:
        protected = [args.input] if args.input else []
        if args.db != ":memory:":
            protected.append(Path(args.db))
        if any(args.json_output.resolve() == path.resolve() for path in protected):
            p.error("--json-output must differ from --input and --db")
    try:
        until = None if args.until is None else pd.to_datetime(args.until, utc=True)
        if until is not None and pd.isna(until):
            raise ValueError("--until must be a valid timestamp")
        if args.input:
            raw = pd.read_csv(args.input, dtype={"meter_id": "str", "site_id": "str"})
            truth = None
        else:
            raw, truth = generate(seed=args.seed, days=args.days)
        with store.connect(args.db) as con:
            report = store.run(con, raw, until=until)
            readings = store.load(con)
            findings = detect_all(readings)
        # Only the isolated full demo has ground truth for every stored reading.
        evaluation = (
            score(findings, truth)
            if truth is not None and until is None and args.db == ":memory:"
            else None
        )
        if args.json_output:
            payload = {
                "input_mode": "csv" if args.input else "synthetic",
                "until": until.isoformat() if until is not None else None,
                "findings_scope": "all stored readings",
                "stored_rows": len(readings),
                "quality": asdict(report),
                "findings": [asdict(finding) for finding in findings],
                "evaluation": evaluation,
            }
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, duckdb.Error) as exc:
        p.error(str(exc))

    print("DATA QUALITY")
    print("\n".join(report.lines()))
    print("\nFINDINGS")
    for f in findings:
        print(f"{f.meter_id}  {f.kind:<9} {f.detail}")
    if evaluation is not None:
        print("\nCHECK AGAINST INJECTED PROBLEMS")
        for k, v in evaluation.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
