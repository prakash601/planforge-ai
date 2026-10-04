# Deliverables (8)

1. Compliance matrix: requirement -> file path -> artifact -> status.
2. Capture route: TestFlight/dev build OR one-page stock-capture protocol + device matrix.
3. Repo, README to running on a fresh capture in under 15 min on a clean machine, one command per capture.
4. Reproduction bundle: everything needed to regenerate every reported number from raw inputs. Cached model outputs acceptable when cache replays deterministically AND live path also runs (walk-in runs live).
5. Benchmark report: gates at all three tiers, repeatability table, head-to-head table, timing.
6. Fix-loop bundle.
7. Technical report, max 6 pages: architecture, tier design + device matrix, drift handling, error budget, calibration analysis, fix-loop story, known failure modes. Cap is deliberate: length trades against engineering time; engineering is scored.
8. Raw benchmark data: sensor logs, ground truth, app exports.
