# PlanForge AI - Design Doc

Status: draft. Published in-repo since 2026-10-04.
Sources: `Applied-AI-Case-Study.pdf` (see `REQUIREMENTS.md`, `01`-`11`), actual sample data on disk (2026-10-02).

## 1. Goal

Convert iPhone captures (photos / video / LiDAR) into a dimensioned, structured
property model: per-room plans + stitched whole-property plan + measurements with
confidence intervals + damage assessment, emitted as JSON (published schema) + rendered plan.
One command per capture, fresh-capture to running in <15 min on a clean machine.

Non-goals for now: frontend, API/database, RAG/assistants, K8s/microservices.

## 2. What the sample data actually is (verified on disk)

`data/` total ~912M, 3 captures, LiDAR tier. NEVER commit (gitignored).

```
data/<capture_id>/
  depth/           16-bit grayscale PNG, 256x192; encoded units unconfirmed
  confidence/      8-bit grayscale PNG, 256x192, values 0/1/2; label meanings unconfirmed
  odometry.csv     timestamp, frame, x,y,z, qx,qy,qz,qw, fx,fy,cx,cy (+empty distortion cols)
                   rows = frames + header; raw pose + per-frame intrinsics (not depth-sized)
  imu.csv          timestamp, accel (a_x,a_y,a_z), gyro (alpha_x,alpha_y,alpha_z)
  rgb.mp4          42-241M per capture (RGB frames, extract on ingest)
  camera_matrix.csv  global 3x3 intrinsics (fx ~1599; odometry fx ~1596, RGB-resolution scale)
```

| capture | frames | depth/conf | rgb.mp4 |
|---|---|---|---|
| 1a8384c3f6 | 5251 | 5251 / 5251 | 128M |
| c00a170fe1 | 1715 | 1715 / 1715 | 42M |
| c7d28f72c6 | 9745 | 9745 / 9745 | 241M |

Key facts for design: pose + intrinsics per frame; calibration conventions still need validation.
The odometry principal point (~955,718) exceeds the depth dimensions (256x192),
so those intrinsics cannot be applied directly to depth pixels.
depth<->RGB resolution differs (256x192 vs RGB) so ingest must associate/upsample explicitly;
confidence masks gate which depth pixels enter the cloud; IMU is auxiliary (pose refinement later).
Open questions: depth unit scale factor confirmation, depth/RGB timestamp sync method,
which room each capture is (floor-only? with-ceiling? full room?), ground truth file location.

## 3. Architecture

All tiers normalize into ONE representation; every downstream module works on it.

```
Photos ──┐
Video ───┼──> ingestion ──> NormalizedSpatialScene ──> reconstruction ──> RoomGeometry
LiDAR ───┘   (per-tier loader,      (frames, point cloud,    (clean cloud,    (floor/ceiling/
              validation, fail        mesh, poses,             normalized       wall planes,
              explicit on missing     intrinsics, depth,       frame, debug     corners, polygon,
              data)                   metadata)                .ply artifacts)   openings)
                                                              │
                    ┌─────────────────────────────────────────┘
                    v
              measurement ──> stitching ──> damage ──> schemas/CLI/rendering
              (lengths, area,  (room graph,   (RGB seg →      (JSON + CI,
               height, ALL     drift corr.,   project →       SVG/PNG plan,
               with 95% CI)    ablation)     metric extent)   one cmd/capture)
                    │                                          │
                    └──────> evaluation <─────────────────────┘
                             (errors, repeatability, benchmark, fix-loop)
```

Domain objects: `SpatialScene`, `RoomGeometry` (floor/ceiling/wall planes, corners,
polygon, openings), `Measurement` (value, unit=m, CI, method), `Property`
(rooms, connections, global transform, surfaces, damages).

## 4. Module map (maps to `src/planforge/`)

- `domain/` scene, room, property, measurement, surface (units: m / m2, no internal rounding)
- `ingestion/` base `CaptureLoader.load(path)->SpatialScene`; `lidar.py` FIRST (this data),
  `video.py` / `photos.py` stubs behind the same interface
- `reconstruction/` depth→cloud, camera→world transform, frame-cloud fusion,
  statistical/voxel/outlier filtering; emits raw/filtered/normalized `.ply`
- `geometry/` RANSAC planes (floor → ceiling → walls after floor/ceiling removal),
  coplanar merge, furniture rejection (min area/support thresholds, no hard-coded wall count),
  corners = adjacent-wall intersections, Shapely polygon (validated: closed, no self-intersection)
- `measurement/` dimensions, area, height, uncertainty (CI from tier + residuals + observation count)
- `stitching/` RoomGraph (nodes=rooms, edges=shared openings), per-room→property transforms,
  pose-graph + loop closure + plane-anchored correction; ablation ON vs OFF is a deliverable
- `damage/` RGB detection/segmentation → project mask onto surface → metric area;
  concealed-damage flags + firing rule; start with 2 classes
- `evaluation/` absolute/relative/MAE/median/P90 error, % within 1 cm / 2 cm / 3% / 8%,
  repeatability spread, benchmark runner, worst-gate finder
- `rendering/` SVG-first floor plan (walls, lengths, label, area, openings), PNG export, debug overlays
- `schemas/` Pydantic output + benchmark schemas, stable across tiers (only provenance/CI change)
- `cli.py` Typer: `planforge run --input data/<cap> --output outputs/<cap>`

## 5. Gating requirements that shape design (from `04-GATES.md`)

- Openings ≤2 cm on ≥85%; miss/phantom = miss → detection needs geometric + RGB agreement, not RGB alone.
- Ceiling ≤1.5 cm/room, cross-capture spread ≤1 cm → report bias vs variance separately.
- Repeatability 1 cm / 0.5% per wall → deterministic algorithms where practical.
- Drift: poses-as-is = auto-fail → pose-graph optimization is mandatory, not optional.
- Photo stitch: correct adjacency, no overlaps, ±8% footprint → photo tier needs scale estimation + layout solver.
- Calibration scored every tier; photo ±8%, video ±3% with WIDER honest intervals on thin input.

## 6. Tech stack

Python 3.11+, Open3D, NumPy, SciPy, Shapely, OpenCV, PyTorch, Pydantic (+Settings/YAML),
Typer, pytest, Matplotlib. Later only if needed: FastAPI, React/Three.js, Postgres, MLflow/W&B.

## 7. Milestones M0-M20

The active implementation sequence, completion checks and progress are maintained
in [ROADMAP.md](ROADMAP.md). The milestone labels below remain an architecture outline.

M0 data discovery (this data) → M1 scene loader → M2 3D viewer → M3 floor → M4 ceiling →
M5 walls → M6 polygon → M7 measurements → M8 rendering → M9 evaluation → M10 openings →
M11 multi-room → M12 drift → M13 damage → M14 video → M15 photos → M16 calibration →
M17 benchmark → M18 fix loop → M19 productionization → M20 defense-ready cold run.

Task 1: `scripts/inspect_capture.py` + `docs/DATASET_ANALYSIS.md` from THIS data
(directory tree, formats, RGB/depth/pose/intrinsics/mesh availability, units, coordinate
frames, per-capture differences, pipeline support, missing info). No geometry yet.

Task 1 implements an upstream `CaptureLoader.load(path) -> LidarCapture` contract:
validated raw frame records, lazy pixel access, unmodified calibration/poses, IMU and
video references. It intentionally precedes `SpatialScene`; subsequent stages use
explicit provisional camera/world transforms, without certifying metric units. The actual
inspection results and validation boundaries are in `DATASET_ANALYSIS.md`.

## 8. Engineering rules

Explicit coordinate units internally, meters only after scale validation; raw captures immutable; every stage emits debug artifacts; explicit
failures, never silent fallback; deterministic where practical; every algorithm has a test;
capture parsing separate from algorithms; benchmark every geometry change; incremental
commits (process evidence is scored); no sample-specific hard-coding.

## 9. Implemented Geometry Baseline

Task 3 now produces the reusable `SpatialScene` contract in hypothesized pose
units, with scale status `unverified`. Task 4 consumes its full cloud arrays and
produces `RoomGeometry`: normal-aware plane evidence, coplanar merging,
provisional orientation, supported wall runs and general candidate polygonization.
Missing surfaces, orientation ambiguity and open boundaries remain explicit.
No dimensioned floor plan, verified room count, gravity or accuracy is claimed.
See [RECONSTRUCTION_ANALYSIS.md](RECONSTRUCTION_ANALYSIS.md) and
[GEOMETRY_ANALYSIS.md](GEOMETRY_ANALYSIS.md) for policies and local evidence.

## 10. Implemented Measurement Contract

Task 5 consumes `RoomGeometry` through `planforge.measurements.measure_geometry`.
The packaged `schema-v1.json` is JSON Schema Draft 2020-12, validated by
`jsonschema` plus foreign-key, finiteness, polygon and interval checks. This is
the actual candidate-measurement contract, preceding the broader planned
property/damage model above; no Pydantic layer was needed for this stage.

Stable IDs use capture namespace and canonical geometry; reversing wall
endpoints or changing polygon winding/start does not change identity. Geometry
changes can change IDs; they are not cross-capture physical-room identifiers.
Openings have a reserved identity contract but no detections in schema v1.

Observed support-run lengths and supported closed-region boundary lengths are
separate records. Regions include holes; ceiling height requires overlapping
candidate ceiling evidence and is otherwise unavailable. Sensitivity ranges
retain geometry thresholds and residual allowances without treating fused
pixels as independent measurements. Physical scale, pose drift, topology and
sensor bias are not covered by those ranges. See
[MEASUREMENT_ANALYSIS.md](MEASUREMENT_ANALYSIS.md). Task 6 adds rendering and the
combined LiDAR command; see the implemented baseline below.

## 11. Implemented Raw-To-Plan Pipeline

Task 6 adds `planforge run` through an installed argparse console entry point.
`pipeline.run_capture` composes the existing loader, reconstruction, geometry,
measurement and rendering modules. Calibration is an explicit input, not a
silently guessed metric convention; this command does not rerun Task 2's
hypothesis search. One raw capture is processed per invocation.

The renderer shares geometry/layout primitives across SVG and Pillow PNG,
exports a responsive static HTML report and retains the measurement JSON.
Indexed walls link map segments to dimension/sensitivity tables; holes are
retained; partial support is dashed; unresolved plans are explicitly empty.
No north arrow, certified metric scale bar, openings or whole-property claim
is added without evidence.

Complete stage outputs are built in a sibling temporary directory, then
published by rename with rollback on publication failure. Existing output
must have a matching completed run marker; unrelated directories and the raw
input tree are protected. Timings, settings, calibration, package versions,
source hash and intermediate cloud/geometry artifacts are saved together.
See [PLAN_PIPELINE_ANALYSIS.md](PLAN_PIPELINE_ANALYSIS.md) for commands, sample
results and verification limits.

## 12. Implemented Opening Candidate Baseline

Task 7 adds `openings.detect_openings(scene, geometry, config)` and
`attach_openings(model, detection)`. Bounded wall-plane occupancy gaps require
supportive borders and representative through-plane sight lines from multiple
first-supporting frame cameras. Unsupported coverage gaps are not emitted as
opening measurements. The evidence is depth-derived; RGB alignment and semantic
verification have not been added.

Schema v1.1 includes candidate opening records and width measurements, while
schema v1.0 remains valid for prior Task 5/6 artifacts. Contained openings
reference a supporting wall; a doorway between two runs references both jamb
runs through `adjacent_support` rather than fabricating a continuous wall.
Stable opening IDs derive from capture, source plane and canonical gap geometry.
Widths retain pose-unit sensitivity, unknown physical scale and provisional
classes. The pipeline saves opening diagnostics, and the plan renderer adds
candidate markers/tables without inventing door swing or verified window type.

`openings.evaluation.score_openings` uses one-to-one assignment to annotated
plane-local rectangles, reports misses, phantoms, width/class failures, and
includes missed/phantom cases in its pass fraction. Synthetic annotations are
not a measured property benchmark. See [OPENING_ANALYSIS.md](OPENING_ANALYSIS.md).
