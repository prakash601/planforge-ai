# PlanForge AI Documentation

This folder holds the requirements, design, roadmap and per-task analysis for
PlanForge AI. Start with the top-level [README](../README.md) if you want to run
the code.

## Orientation

| Document | What it covers |
| --- | --- |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Index of the case-study requirements distilled into `01`-`11` |
| [12-DESIGN.md](12-DESIGN.md) | Architecture, module map, domain objects and engineering rules |
| [ROADMAP.md](ROADMAP.md) | The 16-task build sequence with current status and evidence |

## Requirement breakdown

| File | Part |
| --- | --- |
| [01-CAPTURE-ROUTES-AND-INPUT-TIERS.md](01-CAPTURE-ROUTES-AND-INPUT-TIERS.md) | Capture routes and the three mandatory input tiers |
| [02-OUTPUT-CONTRACT.md](02-OUTPUT-CONTRACT.md) | Per-capture output contract |
| [03-BENCHMARK-SET.md](03-BENCHMARK-SET.md) | Self-built benchmark composition |
| [04-GATES.md](04-GATES.md) | Round-1 gates plus additions |
| [05-HEAD-TO-HEAD.md](05-HEAD-TO-HEAD.md) | Incumbent comparison |
| [06-FIX-LOOP.md](06-FIX-LOOP.md) | Fix-loop deliverable |
| [07-PROCESS-EVIDENCE.md](07-PROCESS-EVIDENCE.md) | Commit-as-you-work process evidence |
| [08-DELIVERABLES.md](08-DELIVERABLES.md) | The eight deliverables |
| [09-WALKIN-TEST.md](09-WALKIN-TEST.md) | Cold-run walk-in test |
| [10-SCORING-AND-CONSTRAINTS.md](10-SCORING-AND-CONSTRAINTS.md) | Scoring weights and constraints |
| [11-FLOW-PIPELINE.md](11-FLOW-PIPELINE.md) | End-to-end pipeline flow |
| [source/](source/) | Original case study PDF and extracted text |

## Task analysis

These are produced as each task completes. They record method, evidence,
verification and remaining limits. Several reference artifacts under
`outputs/`, which is gitignored: those runs are regenerable from the scripts
described in each document, not committed.

| Document | Task |
| --- | --- |
| [DATASET_ANALYSIS.md](DATASET_ANALYSIS.md) | Task 1 - dataset inspection |
| [CALIBRATION_ANALYSIS.md](CALIBRATION_ANALYSIS.md) | Task 2 - calibration hypotheses and viewer |
| [RECONSTRUCTION_ANALYSIS.md](RECONSTRUCTION_ANALYSIS.md) | Task 3 - scene reconstruction |
| [GEOMETRY_ANALYSIS.md](GEOMETRY_ANALYSIS.md) | Task 4 - candidate room geometry |
| [MEASUREMENT_ANALYSIS.md](MEASUREMENT_ANALYSIS.md) | Task 5 - measurements and uncertainty |
| [PLAN_PIPELINE_ANALYSIS.md](PLAN_PIPELINE_ANALYSIS.md) | Task 6 - rendering and CLI |
| [OPENING_ANALYSIS.md](OPENING_ANALYSIS.md) | Task 7 - candidate openings |
| [STITCHING_ANALYSIS.md](STITCHING_ANALYSIS.md) | Task 8 - candidate property stitching |
| [DRIFT_ANALYSIS.md](DRIFT_ANALYSIS.md) | Task 9 - drift correction and ablation |

## Status note

The sample captures are gitignored and have no measured ground truth, so the
analysis documents report local, unverified results. The wording of each
document (`complete locally`, `candidate`, `provisional`, `unverified`) is
intentional and should be preserved when quoting results.
