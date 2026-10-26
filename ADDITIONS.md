# Repository preparation additions

The original application, fixtures, evaluation sets and tests came from the supplied project archive.

Added during preparation:

- Installable setuptools packaging, dependency metadata, development/provider extras and a console command.
- Packaged demo resources for the AI projects; local `.env` loading and configurable resource directories.
- GitHub Actions for lint, tests, wheel/source builds and offline demos on Python 3.10 and 3.12.
- README badges, quick start for Windows and Unix, architecture diagram and code navigation.
- Preserved original README as design notes; recorded actual demo output.
- MIT license, contributing and security documentation, expanded ignore rules.
- Corrections documented below when validation identified problems.

No production deployment, live provider results or real customer data are claimed.

Fixed empty arrival-cutoff batches so early backfill runs are safe, validated the generator's minimum time window, and added regression coverage.

Added source-distribution manifests and CI verification of installed wheels from outside the checkout.

## 26 October 2026 upgrade

- Reviewed and merged contributor PR #1, preserving elapsed working-day spacing in drift detection.
- Added batch validation, UTC normalization, deterministic duplicate tie handling, and regression tests confirming invalid feeds leave stored readings unchanged.
- Added CSV ingestion, arrival cutoffs, JSON reports, and actionable command-line errors.
- Prevented report paths from overwriting input feeds or database files.
- Limited synthetic scoring to an isolated complete demo, avoiding misleading scores for external or partial data.
- Added an example feed, input-contract documentation, and a CSV smoke test in CI.
