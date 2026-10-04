# PlanForge AI

Multi-modal spatial reconstruction and property assessment. PlanForge AI turns
handheld property captures into a dimensioned property model: per-room floor
plans, ceiling heights, floor areas, openings and candidate whole-property
layouts, emitted as structured JSON plus a rendered plan.

> **Status: research prototype, LiDAR tier only.** The reconstruction, geometry,
> measurement, opening, stitching and drift stages are implemented and locally
> tested on three supplied LiDAR captures. **No physical ground truth exists for
> those captures**, so every measurement is reported in *unverified pose units*
> with provisional intervals. No accuracy claim is made. Video, photo, damage and
> whole-property validation tiers are not implemented yet. See
> [Roadmap](#roadmap) and [Honest limitations](#honest-limitations).

## What exists today

- **Ingestion** of a raw LiDAR capture: depth PNGs, confidence PNGs, per-frame
  poses and intrinsics, IMU and the RGB video, with validation and no guessed unit
  conversions.
- **Calibration diagnostics**: forty depth-scale / intrinsics / axis / pose
  hypotheses scored by cross-frame projective consistency, with a ranked report
  and interactive depth-only point-cloud viewer.
- **Reconstruction**: bounded voxel fusion of every frame with confidence and
  outlier filtering, producing raw and filtered clouds.
- **Room geometry**: RANSAC planes, coplanar merging, provisional orientation,
  supported wall runs and a general (non-four-wall) candidate polygon.
- **Measurements**: wall-run lengths, supported region boundaries and areas,
  ceiling height where observed, each with a versioned JSON Schema and
  sensitivity intervals.
- **Openings**: bounded wall-gap candidates gated by jamb/header support and
  multiple through-plane sight lines, with width measurements and miss/phantom
  inclusive scoring.
- **Stitching**: per-capture models combined into one candidate `property.json`
  with a room graph and overlap checks.
- **Drift**: loop-closure detection with a translation-only correction and a
  raw-vs-corrected ablation.
- **One command per capture**: `planforge run` goes from one raw capture to
  JSON + SVG + PNG + an HTML report.

## Quick start

Requires Python 3.11+. [uv](https://docs.astral.sh/uv/) is recommended.

```sh
uv sync --locked --extra dev --python 3.11
uv run --locked --extra dev python -m pytest -q
```

### Inspect a capture

```sh
uv run --locked python scripts/inspect_capture.py data/<capture_id> \
  --samples 8 --output outputs/dataset-inspection.json
```

### Calibrate (provisional) and view the cloud

```sh
uv run --locked python scripts/calibrate_capture.py data \
  --output outputs/calibration
```

This scores the candidate conventions, writes `calibration.json` per capture and
an interactive viewer under `outputs/calibration/index.html`. Build the viewer
assets first if `viewer/dist/` is absent:

```sh
npm ci --prefix viewer && npm run build --prefix viewer
```

### Run the full pipeline from one raw capture to a plan

```sh
uv run --locked planforge run \
  --input data/<capture_id> \
  --output outputs/<capture_id> \
  --calibration outputs/calibration/<capture_id>/calibration.json
```

Outputs `measurements.json` (rooms, walls, openings and measurements),
`plan.svg`, `plan.png`, `index.html`, `run.json` (timings, settings, calibration,
package versions, source hash) and a `debug/` folder of stage artifacts.

### Stitch captures into a candidate property

```sh
uv run --locked python scripts/stitch_property.py \
  --inputs outputs/<a>/measurements.json outputs/<b>/measurements.json \
  --output outputs/property \
  --property-id property-assumed-single
```

### Drift ablation (raw vs loop-closure corrected)

```sh
uv run --locked python scripts/ablate_drift.py \
  --inputs data/<a> data/<b> \
  --calibrations outputs/calibration/<a>/calibration.json outputs/calibration/<b>/calibration.json \
  --raw-artifacts outputs/reconstruction/<a> outputs/reconstruction/<b> \
  --output outputs/drift
```

## Capture format

PlanForge LiDAR ingestion expects one directory per capture:

```text
data/<capture_id>/
  depth/           16-bit grayscale PNG, 256x192, encoded units unconfirmed
  confidence/      8-bit PNG, 256x192, labels 0/1/2
  odometry.csv     timestamp, frame, x,y,z, qx,qy,qz,qw, fx,fy,cx,cy
  imu.csv          timestamp, accel (a_x,a_y,a_z), gyro (alpha_x,alpha_y,alpha_z)
  camera_matrix.csv  3x3 global intrinsics (RGB-resolution scale)
  rgb.mp4          RGB video
```

Raw captures are treated as immutable and are never rewritten. Depth/pose units,
RGB synchronisation and physical scale are **not** assumed; calibration is an
explicit input, not a silently guessed convention.

## Repository layout

```text
src/planforge/
  ingestion/       capture loading and validation
  diagnostics/     calibration hypotheses, ranking and viewer export
  reconstruction/  depth -> fused cloud (SpatialScene)
  geometry/        floor/ceiling/wall planes and candidate polygon
  measurements/    lengths, areas, heights + JSON Schema
  openings/        gap detection, evaluation and scoring
  stitching/       property model, room graph, stitched plan
  drift/           loop-closure correction and metrics
  rendering/       SVG/PNG plan and HTML report
  pipeline.py      one-capture composition
  cli.py           the `planforge run` entry point
scripts/           inspect / calibrate / reconstruct / measure / render / stitch / ablate
tests/             pytest suite
viewer/            Vite + Three.js depth-cloud viewer
docs/              requirements, design, roadmap and per-task analysis
```

## Roadmap

The build sequence and per-task status live in [docs/ROADMAP.md](docs/ROADMAP.md).
Tasks 1-9 (LiDAR inspection through drift/multi-room stitching) are complete
locally. Remaining work: damage and scope items (Task 10), video tier (Task 11),
photo tier (Task 12), uncertainty calibration (Task 13), a measured benchmark
(Task 14), the head-to-head fix loop (Task 15) and reproduction/cold-run
readiness (Task 16).

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Inspect and reconstruct the samples | Complete locally |
| 2 | Single-room floor plan | Complete locally (candidate) |
| 3 | Openings and whole-property layout | Complete locally (candidate) |
| 4 | Damage and scope assessment | Not started |
| 5 | Video and photo tiers | Not started |
| 6 | Prove and package | Started (compliance matrix done; benchmark, fix loop, reports pending) |

## Honest limitations

- The three sample captures have **no known dimensions, no measured ground truth
  and no confirmed capture identities**. Accuracy, centimetre intervals and
  repeatability are therefore unproven, not merely unreported.
- Physical scale, depth/pose units and RGB<->depth synchronisation remain
  unverified. Measurements are in unverified pose units.
- Candidate room geometry is unstable: one capture has a supported closed region,
  two are incomplete or orientation-ambiguous, and the closed region collapses
  under drift-scale pose changes.
- Openings are geometry-only candidates. No real sample opening is confirmed;
  evaluation uses synthetic annotations.
- Drift correction is translation-only; rotation, gravity and inter-capture
  alignment are not solved. The pipeline default remains raw poses.
- The stitched property is under an assumed-single-property hypothesis and
  currently yields 1 room, 0 adjacency edges and 0 overlaps.

## Development

```sh
uv run --locked --extra dev python -m pytest -q      # 142 tests
uv run --locked ruff check .                          # if ruff is installed
```

CI runs the test suite, viewer build, CodeQL and gitleaks on every pull request.

## Documentation

- [docs/COMPLIANCE.md](docs/COMPLIANCE.md) - requirement-to-artifact compliance matrix and honest gap list
- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) - requirements distilled from the case study
- [docs/12-DESIGN.md](docs/12-DESIGN.md) - architecture and module map
- [docs/ROADMAP.md](docs/ROADMAP.md) - build sequence and current status
- [docs/DATASET_ANALYSIS.md](docs/DATASET_ANALYSIS.md) - what the samples actually contain
- [docs/CALIBRATION_ANALYSIS.md](docs/CALIBRATION_ANALYSIS.md) - hypothesis scoring
- [docs/RECONSTRUCTION_ANALYSIS.md](docs/RECONSTRUCTION_ANALYSIS.md) - fused scenes
- [docs/GEOMETRY_ANALYSIS.md](docs/GEOMETRY_ANALYSIS.md) - candidate room geometry
- [docs/MEASUREMENT_ANALYSIS.md](docs/MEASUREMENT_ANALYSIS.md) - measurements and uncertainty
- [docs/PLAN_PIPELINE_ANALYSIS.md](docs/PLAN_PIPELINE_ANALYSIS.md) - rendering and CLI
- [docs/OPENING_ANALYSIS.md](docs/OPENING_ANALYSIS.md) - opening detection and scoring
- [docs/STITCHING_ANALYSIS.md](docs/STITCHING_ANALYSIS.md) - candidate property stitching
- [docs/DRIFT_ANALYSIS.md](docs/DRIFT_ANALYSIS.md) - drift correction and ablation

## Security

See [SECURITY.md](SECURITY.md). Sample captures and generated outputs are never
committed.
