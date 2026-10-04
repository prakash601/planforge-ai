# Compliance Matrix

Requirement -> file path -> artifact -> status.

Status values: **Implemented** (works end-to-end, locally tested),
**Partial** (real but incomplete or unverified), **Not started** (no artifact).

Source of requirements: `docs/01`-`11` distilled from the case study in
`docs/source/`. Build sequence and per-task evidence: [ROADMAP.md](ROADMAP.md).

**Summary: 1 of 3 input tiers; 4 of 8 deliverables complete; 0 of 6 measured
gates achievable.** The LiDAR tier is a working, tested engine. Video, photos,
damage, the benchmark set, the head-to-head, the fix loop and the walk-in test
are not started. Every measured gate needs laser/tape ground truth that the
supplied captures do not contain, so none can be claimed.

## Part 1 - Capture route and input tiers

| # | Requirement | File path | Artifact | Status |
| --- | --- | --- | --- | --- |
| 1.1 | Choose a capture route (own iOS app, or stock tool + one-page protocol) | `docs/CAPTURE-ROUTE.md` | Route 2 chosen | Implemented |
| 1.2 | TestFlight/dev build, or named stock tool with protocol | `docs/CAPTURE-ROUTE.md` | one-page protocol | Partial (tool name/version to confirm) |
| 1.3 | Device matrix: which tier on which hardware, honest accuracy | `docs/CAPTURE-ROUTE.md` | device matrix table | Implemented |
| 1.4 | Photo tier: 2-8 stills/room, per-room folders, stitched plan, widened intervals | - | - | Not started |
| 1.5 | Video tier: handheld walkthrough clip | - | - | Not started |
| 1.6 | LiDAR tier: depth, poses, intrinsics on Pro-class devices | `src/planforge/ingestion/lidar.py` | `LidarCaptureLoader`, validated frame records | Implemented |
| 1.7 | Same output contract from every tier | `src/planforge/measurements/schema-v1.1.json` | one JSON Schema for all tiers | Partial (only LiDAR feeds it) |

## Part 2 - Output contract per capture

| # | Requirement | File path | Artifact | Status |
| --- | --- | --- | --- | --- |
| 2.1 | Dimensioned per-room plan: walls | `src/planforge/geometry/rooms.py` | `RoomGeometry` wall runs | Implemented |
| 2.2 | Floor area | `src/planforge/measurements/model.py` | supported region area incl. holes | Implemented |
| 2.3 | Ceiling height | `src/planforge/measurements/model.py` | height where ceiling evidence overlaps | Partial (often unavailable) |
| 2.4 | Openings | `src/planforge/openings/detection.py` | geometry-only candidate gaps + widths | Partial (no real sample opening confirmed) |
| 2.5 | Stitched multi-room plan, correct adjacency | `src/planforge/stitching/model.py` | candidate `property.json`, room graph | Partial (1 room, 0 edges, 0 overlaps) |
| 2.6 | Per-surface damage regions with class + metric extent | - | - | Not started |
| 2.7 | Concealed-damage flags with firing rule | - | - | Not started |
| 2.8 | Scope line items keyed to surfaces | - | - | Not started |
| 2.9 | Confidence interval on every measurement | `src/planforge/measurements/model.py` | sensitivity intervals per measurement | Partial (provisional, unverified units) |
| 2.10 | One command per capture | `src/planforge/cli.py` | `planforge run` | Implemented |
| 2.11 | JSON to the published schema | `src/planforge/measurements/schema-v1.1.json` | Draft 2020-12 schema, validated | Partial (packaged, not web-published) |
| 2.12 | Rendered plan | `src/planforge/rendering/plans.py` | `plan.svg`, `plan.png`, `index.html` | Implemented |

## Part 2b - Self-built benchmark set

| # | Requirement | File path | Artifact | Status |
| --- | --- | --- | --- | --- |
| B.1 | Multi-room capture (3+ rooms + connector) | - | - | Not started |
| B.2 | Furnished room with two staged damage classes | - | - | Not started |
| B.3 | Same rooms at all three tiers | - | - | Not started |
| B.4 | One room captured twice at the same tier | - | - | Not started |
| B.5 | Laser/tape ground truth on everything | - | - | Not started (supplied captures have no known dimensions) |

## Part 2c - Round-1 gates

| Gate | Target | Achievable today | Status |
| --- | --- | --- | --- |
| Opening widths | <= 2 cm on >= 85%, miss/phantom = miss | No ground truth | Not measurable |
| Ceiling height | <= 1.5 cm/room, cross-capture spread <= 1 cm | No ground truth, scale unverified | Not measurable |
| Repeatability | Same room within 1 cm or 0.5% per wall | No repeat capture | Not measurable |
| Drift accountability | Stated method + footprint ablation on/off | `src/planforge/drift/model.py`, `scripts/ablate_drift.py` | Implemented (ablation exists; not "poses as-is") |
| Photo-tier whole-property stitch | Correct adjacency, no overlaps, +/-8% | Photo tier absent | Not measurable |
| Photo wall lengths | +/-8% with calibrated intervals | Photo tier absent | Not measurable |
| Video wall lengths | +/-3% with calibrated intervals | Video tier absent | Not measurable |

## Part 3 - Head-to-head vs incumbent (10%)

| # | Requirement | File path | Artifact | Status |
| --- | --- | --- | --- | --- |
| 3.1 | LiDAR output vs one named consumer app on 2 rooms | - | - | Not started |
| 3.2 | One table, our error vs theirs, dimension by dimension | - | - | Not started |
| 3.3 | Beat/tie >= 70% of shared dimensions, submit app export | - | - | Not started |

## Part 4 - Fix loop (25%)

| # | Requirement | File path | Artifact | Status |
| --- | --- | --- | --- | --- |
| 4.1 | Worst gate + failing number | - | - | Not started (no benchmark to pick from) |
| 4.2 | Root-cause hypothesis + evidence | - | - | Not started |
| 4.3 | Shipped fix + predicted number | - | - | Not started |
| 4.4 | Regenerable before/after runs + readable diff | - | - | Not started |

## Part 5 - Process evidence (5%)

| # | Requirement | File path | Artifact | Status |
| --- | --- | --- | --- | --- |
| 5.1 | Commit as you work; auditable history | `git log`, PRs #5-#12 | 11 incremental commits | Implemented |
| 5.2 | Every design decision defensible live | `docs/12-DESIGN.md`, per-task analysis | design + evidence trail | Partial (defense not rehearsed) |

## Deliverables

| # | Deliverable | File path | Status |
| --- | --- | --- | --- |
| D.1 | Compliance matrix | `docs/COMPLIANCE.md` | Implemented (this file) |
| D.2 | Capture route + device matrix | `docs/CAPTURE-ROUTE.md` | Implemented (protocol + matrix; LiDAR only today) |
| D.3 | Repo + README, one command/capture, <15 min | `README.md`, `src/planforge/cli.py` | Implemented |
| D.4 | Reproduction bundle | `scripts/` | Partial (scripts exist; no single bundle) |
| D.5 | Benchmark report (all tiers, repeatability, head-to-head, timing) | - | Not started |
| D.6 | Fix-loop bundle | - | Not started |
| D.7 | Technical report, max 6 pages | `docs/TECHNICAL-REPORT.md` | Implemented |
| D.8 | Raw benchmark data | - | Not started |

## Constraints

| Constraint | Status |
| --- | --- |
| Handheld consumer capture only | Partial (LiDAR samples, unclear capture app) |
| Pretrained model/dataset/API disclosure | Implemented (no pretrained models used) |
| Runs without calling your infrastructure | Implemented (fully local) |
| Weights/binaries fetched by script or volume | Partial (no large models; `data/` is local-only) |
| Mirrors, glass, wet-look, low light coverage | Not started |

## Scoring reality

| Weight | Component | Status |
| --- | --- | --- |
| 30% | Walk-in test | Not runnable (needs all three tiers) |
| 25% | Fix loop delta | Not started |
| 15% | Verified benchmark accuracy | Not measurable (no ground truth) |
| 10% | Compliance matrix coverage | Implemented (this file) |
| 10% | Head-to-head | Not started |
| 5% | Capture route quality | Implemented (route, protocol, device matrix; LiDAR only) |
| 5% | Process evidence | Implemented |

## Honest gaps in one line each

- **Photo and video tiers** are mandatory and absent; photos are the stated floor.
- **Damage, concealed-damage and scope items** have no module.
- **The benchmark set and its ground truth** do not exist, so no gate is measurable.
- **Head-to-head and the fix loop** both depend on that benchmark.
- **The walk-in test** needs all three tiers cold; only LiDAR exists.
