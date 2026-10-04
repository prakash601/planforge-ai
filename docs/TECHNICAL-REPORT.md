# PlanForge AI - Technical Report

Deliverable #7. Sections follow the case study: architecture, tier design and
device matrix, drift handling, error budget, calibration analysis, fix-loop story
and known failure modes.

> **Scope warning, stated up front.** This reports what was built and tested, in
> unverified pose units, on three LiDAR captures with no ground truth. It does
> **not** report metric accuracy, benchmark gates or a shipped fix loop, because
> none of those exist yet. Claims below are backed by the linked analysis docs.

## 1. Architecture

One representation, every stage downstream of it. LiDAR is implemented; video and
photos are intended to normalize into the same contract.

```
LiDAR capture ─> ingestion ─> reconstruction ─> geometry ─> measurements ─┐
Video (planned) ─┘            (SpatialScene)   (RoomGeometry) (schema)     │
Photos (planned)                                                          v
                        rendering (SVG/PNG/HTML) <── openings ── stitching ─ drift
```

`src/planforge/` modules: `ingestion/`, `diagnostics/`, `reconstruction/`,
`geometry/`, `measurements/`, `openings/`, `stitching/`, `drift/`, `rendering/`,
`pipeline.py` and `cli.py`. The pipeline composes them into one command per
capture: `planforge run --input <capture> --output <dir> --calibration <json>`.

Design rules that shaped the code: raw captures immutable; explicit coordinate
units, meters only after scale validation; every stage emits debug artifacts;
explicit failure instead of silent fallback; deterministic where practical; every
algorithm has a test. See [12-DESIGN.md](12-DESIGN.md).

## 2. Tier design and device matrix

| Tier | Hardware | Implemented | Honest accuracy |
| --- | --- | --- | --- |
| LiDAR | iPhone Pro | Yes | Unverified; candidate geometry only |
| Video | iPhone 15+ | No | Target +/-3%, unmeasured |
| Photos | iPhone 15+ | No | Target +/-8%, unmeasured |

Full protocol: [CAPTURE-ROUTE.md](CAPTURE-ROUTE.md). The same JSON Schema is
meant to serve every tier; only LiDAR feeds it today. Intervals must widen as
sensor data thins, but no interval is calibrated yet.

## 3. Drift handling

The observed failure mode is trajectory drift: two captures return near their
start while a third ends meters away on a short path. The implementation detects
a loop from the supplied trajectory and distributes the window-averaged closure
error linearly across frames. Rotation drift is **not** estimated; quaternions
pass through unchanged. With no detected loop the correction is exactly zero, so
the corrected run is identical to raw poses by construction.

| Capture | Loop | Closure before -> after | Footprint |
| --- | --- | --- | --- |
| `1a8384c3f6` | Yes | 0.175 -> 0.0001 | 1 room -> 0 rooms; walls 23 -> 9 |
| `c00a170fe1` | No | 3.178 unchanged (control) | n/a |
| `c7d28f72c6` | Yes | 0.387 -> 0.0002 | 0 rooms both |

The ablation (`scripts/ablate_drift.py`) exists, which is what the drift-
accountability gate checks for: an on/off comparison, not "poses used as-is".
The gate's *metric* form remains unproven. The strongest finding is topological
sensitivity: sub-0.2-unit pose redistribution collapses wall runs from 23 to 9 and
loses the single closed region, so the Task 4 region is not stable under
drift-scale changes. See [DRIFT_ANALYSIS.md](DRIFT_ANALYSIS.md).

## 4. Error budget and uncertainty

All lengths are `pose_unit`, areas `pose_unit_squared`, and
`meters_per_pose_unit=null`. No physical confidence interval exists
(`physical_interval=null`, scale status `unbounded_unknown_scale`).

The reported ranges are **deterministic geometry sensitivity**, not statistical
confidence intervals: they vary geometry thresholds and residual allowances and
re-measure. They do not cover physical scale, pose drift, topology or sensor
bias. Ceiling height needs a candidate ceiling envelope overlapping >=50% of the
region; without one it reports `unavailable` rather than substituting wall-top
height. Partial captures emit observed wall lengths but never an invented region,
area or height. See [MEASUREMENT_ANALYSIS.md](MEASUREMENT_ANALYSIS.md).

## 5. Calibration analysis

Forty hypotheses (depth scale x intrinsics scaling x camera axes x pose
direction) were scored across all three captures by cross-frame projective
consistency. The same provisional convention won each capture:

```json
{"depth_scale": 0.001, "intrinsics": "rgb_scaled",
 "camera_axes": "opencv", "pose_direction": "camera_to_world"}
```

Selection is a "provisional diagnostic preference", not accuracy validation.
Relative consistency cannot independently certify physical scale when both unit
conventions are unknown, and RGB synchronization is unverified. The selected
convention is an explicit pipeline input, never silently guessed. See
[CALIBRATION_ANALYSIS.md](CALIBRATION_ANALYSIS.md).

## 6. Fix-loop story

**Not started.** The fix loop is 25% of the score and requires a worst gate with
a failing number, a root cause, a shipped fix, and regenerable before/after runs.
It depends on a benchmark with ground truth, which does not exist. No honest
fix-loop narrative can be written from the current data, so none is claimed.
See [06-FIX-LOOP.md](06-FIX-LOOP.md) and [COMPLIANCE.md](COMPLIANCE.md).

## 7. Known failure modes

- **No ground truth.** Physical scale, accuracy, repeatability and interval
  coverage are unverifiable on the supplied captures.
- **Geometry instability.** Two captures are incomplete or orientation-ambiguous;
  the one closed region collapses under drift-scale pose changes.
- **Openings are unconfirmed.** Detection is geometry-only; no real sample
  opening is confirmed and evaluation uses synthetic annotations.
- **RGB unused.** Openings and damage would need aligned RGB; synchronization is
  unverified, so RGB is inspection-only.
- **Translation-only drift.** Rotation, gravity and inter-capture alignment are
  unsolved.
- **Sparse tiers.** Photos and video are mandatory and unimplemented; the
  "any picture in, results out" floor is not met.
- **Missing contract fields.** Damage regions, concealed-damage flags and scope
  line items have no module.
- **Whole-property stitch unproven.** Stitching yields 1 room, 0 adjacency edges,
  0 overlaps under an assumed-single-property hypothesis.

## Reproduction

```sh
uv sync --locked --extra dev --python 3.11
uv run --locked --extra dev python -m pytest -q          # 142 tests
uv run --locked planforge run --input data/<capture> \
  --output outputs/<capture> \
  --calibration outputs/calibration/<capture>/calibration.json
```

Sample captures are gitignored and not distributed; the supplied numbers cannot
be regenerated without them. Everything above that is code, schema or analysis
is in the repository.
