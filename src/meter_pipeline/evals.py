"""Score the findings against the problems that were injected into the data."""
from __future__ import annotations

from .detect import Finding


def score(findings: list[Finding], truth: dict[str, list[str]]) -> dict:
    got = {(f.kind, f.meter_id) for f in findings}
    want = {(k, m) for k in ("drift", "overnight") for m in truth.get(k, [])}
    tp = len(got & want)
    precision = tp / len(got) if got else 1.0
    recall = tp / len(want) if want else 1.0
    return {
        "true_positives": tp,
        "false_positives": sorted(got - want),
        "missed": sorted(want - got),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
    }
