from __future__ import annotations

import argparse

from . import store
from .detect import detect_all
from .evals import score
from .generate import generate


def main() -> None:
    p = argparse.ArgumentParser(description="Meter data demo on synthetic readings")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--days", type=int, default=28)
    p.add_argument("--db", default=":memory:", help="DuckDB file (default: in memory)")
    args = p.parse_args()

    raw, truth = generate(seed=args.seed, days=args.days)
    con = store.connect(args.db)
    report = store.run(con, raw)

    print("DATA QUALITY")
    print("\n".join(report.lines()))
    findings = detect_all(store.load(con))
    print("\nFINDINGS")
    for f in findings:
        print(f"{f.meter_id}  {f.kind:<9} {f.detail}")
    print("\nCHECK AGAINST INJECTED PROBLEMS")
    for k, v in score(findings, truth).items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
