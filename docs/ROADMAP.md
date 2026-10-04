# PlanForge AI Roadmap

Updated: 2026-10-04. Status: docs published; `data/` and `outputs/` remain gitignored.

## What We Are Building

PlanForge AI turns handheld property captures into a dimensioned property model:
per-room floor plans, one connected whole-property plan, ceiling heights, floor
areas, openings, surface damage and scope line items. Each measurement includes
an uncertainty interval. The final pipeline accepts LiDAR, video and photos and
emits structured JSON plus a rendered plan through one command per capture.

The first usable milestone is smaller: inspect a LiDAR reconstruction, extract
room geometry and render a floor plan. Absolute accuracy is a later validation
result, not an assumption about the supplied samples.

Requirements come from the case study summarized in [REQUIREMENTS.md](REQUIREMENTS.md).
The build sequence below is our implementation plan, not additional instructions
from that document. Proposed commands and artifacts are future interfaces unless
explicitly marked complete.

## Current Position

| Work | Status | Evidence |
| --- | --- | --- |
| Repository and project setup | Complete | Python package, dependency lockfile and GitHub workflows exist |
| Task 1: sample inspection and raw loader | Complete | `scripts/inspect_capture.py`, `src/planforge/ingestion/`, local JSON report |
| Dataset analysis | Complete | [DATASET_ANALYSIS.md](DATASET_ANALYSIS.md) |
| Loader/inspector tests | Complete locally | Last verified run: 16 passing synthetic tests; CI execution is not claimed |
| Task 2: calibration investigation and 3D viewer | Complete locally | [CALIBRATION_ANALYSIS.md](CALIBRATION_ANALYSIS.md), ranked hypotheses and interactive depth-only clouds |
| Task 3: reusable scene reconstruction | Complete locally | [RECONSTRUCTION_ANALYSIS.md](RECONSTRUCTION_ANALYSIS.md), all 16,711 frames reconstructed, raw/filtered exports and viewer |
| Task 4: candidate room geometry | Complete locally | [GEOMETRY_ANALYSIS.md](GEOMETRY_ANALYSIS.md); candidate surfaces/regions, explicit partial/unresolved cases |
| Task 5: measurements and uncertainty | Complete locally (provisional) | [MEASUREMENT_ANALYSIS.md](MEASUREMENT_ANALYSIS.md); pose-unit measurements, uncalibrated sensitivity ranges, schema v1 |
| Task 6: plan rendering and combined CLI | Complete locally (candidate baseline) | [PLAN_PIPELINE_ANALYSIS.md](PLAN_PIPELINE_ANALYSIS.md); SVG/PNG/report and raw-to-plan CLI on all three captures |
| Task 7: candidate openings | Complete (committed `ecc6915`) | [OPENING_ANALYSIS.md](OPENING_ANALYSIS.md); evidence gates, width/schema/plan integration, synthetic annotations; RGB verification pending |
| Task 8: multi-room stitching | Complete (merged PR #10) | [STITCHING_ANALYSIS.md](STITCHING_ANALYSIS.md); property model, room graph, identity/manual transforms, overlap checks, stitched plan; 1 room, 0 edges, alignment unverified |
| Task 9: drift correction and ablation | Complete (committed, translation-only loop baseline) | [DRIFT_ANALYSIS.md](DRIFT_ANALYSIS.md); loop detection, linear closure distribution, raw-vs-corrected ablation; closures to ~0, region instability 1->0 on loop capture, open-trajectory control identical |
| Multi-room, damage, video-only and photos | Planned | Not implemented |
| Ground-truth benchmark and final validation | Requires additional evidence | Samples have no known dimensions or capture identities |

We have three captures containing RGB, depth, confidence, poses, IMU and
intrinsics: 16,711 depth/pose frames total. We have no exporter information,
device metadata, known physical dimensions or measured ground truth. We will
investigate conventions from the available data instead of waiting for metadata.

Observed risks are already recorded: RGB-scale intrinsics on smaller depth
images, unconfirmed depth/pose units and conventions, and one fewer sequentially
decoded RGB frame than reported in each video. Sample IDs do not establish that
captures show the same room, distinct rooms or connected rooms.

## Build Sequence

### Phase 1: Understand And Reconstruct The Samples

**Task 1: Inspection and raw loader. Complete.**

- Validate metadata, frame pairing and image layouts; inspect RGB and sampled pixels.
- Preserve encoded depth and raw poses/calibration without guessed conversions.
- Produce the dataset report and synthetic ingestion tests.

**Task 2: Calibration investigation and diagnostic viewer. Complete locally.**

Evidence: [CALIBRATION_ANALYSIS.md](CALIBRATION_ANALYSIS.md). Forty hypotheses
were compared across all three captures; the same provisional convention won
each capture. Default clouds contain 36 sampled frames per capture. Desktop
and mobile browser checks passed. FFmpeg recovered all RGB frames when ignoring
edit lists; physical scale and RGB timestamp alignment remain unverified.

- Implement configurable depth-scale, intrinsics-scaling and pose-transform hypotheses.
- Back-project one depth frame, then compare overlapping frames under candidate conventions.
- Score consistency using overlap, point-to-plane residuals and surface alignment; retain competing hypotheses when evidence is ambiguous.
- Compare short sequences from all three captures to avoid choosing a convention that fits only one sample.
- Generate a point cloud and viewer with frame selection, trajectory and confidence filtering.
- Investigate the RGB count discrepancy with an independent decoding path; initially reconstruct using depth and poses.
- Record selected assumptions, alternatives, diagnostic scores and unresolved questions in a calibration report.

Deliverables: calibration configuration, diagnostic command, viewable point
clouds and `CALIBRATION_ANALYSIS.md` under `docs/`.

Completion check: short sequences reconstruct coherent surfaces under an
explicit, reproducible hypothesis. Ambiguous conventions are reported, not
silently chosen. Internal alignment can constrain relative depth/pose scale;
it cannot independently certify physical scale if both unit conventions are
unknown. RGB synchronization is tracked separately from depth-only readiness.

**Task 3: Reusable scene reconstruction. Complete locally.**

Evidence: [RECONSTRUCTION_ANALYSIS.md](RECONSTRUCTION_ANALYSIS.md). All three
full captures reconstruct with explicit provisional calibration, bounded voxel
fusion, confidence/outlier filtering and preserved raw/filtered artifacts.
Physical scale remains unverified and supplied poses are not drift-corrected.

- Define the common `SpatialScene` contract: frame conventions, calibration provenance, scale status, trajectory and reconstructed cloud.
- Fuse longer sequences with bounded memory, frame sampling and voxel downsampling.
- Filter invalid depth, apply documented confidence policies and remove outliers.
- Preserve raw and filtered clouds, configuration and diagnostics for reproduction.
- Make scale-dependent thresholds explicit; keep unverified-scale results distinguishable from validated metric scenes.

Deliverables: reconstruction module, scene contract and raw/filtered point clouds.
Completion check: every current capture can produce an inspectable scene with
repeatable configuration and useful diagnostics; unsupported assumptions fail clearly.

### Phase 2: Deliver A Single-Room Floor Plan

**Task 4: Room surfaces and boundaries. Complete locally (candidate baseline).**

Evidence: [GEOMETRY_ANALYSIS.md](GEOMETRY_ANALYSIS.md). Plane fitting, coplanar
merging, provisional orientation, extent rejection, supported wall intersections
and general polygonization are implemented. One supplied capture has a supported
closed candidate region; two remain incomplete or orientation-ambiguous. No
verified room count, gravity, footprint or physical accuracy is claimed.

- Estimate gravity/floor orientation; detect floor, observed ceiling and walls.
- Merge coplanar surfaces and reject furniture-sized structures where evidence allows.
- Find wall intersections and construct valid room polygons without assuming four walls.
- Handle partial coverage and absent ceilings explicitly; inspect whether a capture contains multiple rooms.

Deliverables: `RoomGeometry`, plane overlays, room polygons and synthetic geometry tests.
Completion check: geometry is explainable in the viewer; invalid polygons and
unobserved surfaces are flagged rather than replaced with invented geometry.

**Task 5: Measurements, uncertainty and output schema. Complete locally (provisional).**

Evidence: [MEASUREMENT_ANALYSIS.md](MEASUREMENT_ANALYSIS.md). Observed wall-run
lengths, supported region-boundary lengths, polygon area including holes and
ceiling height where candidate ceiling evidence overlaps are implemented.
The versioned JSON Schema enforces pose units, unverified scale, uncalibrated
sensitivity intervals and stable IDs; missing ceilings remain unavailable.
All three sample captures export successfully. Physical confidence intervals,
centimeter accuracy and uncertainty calibration remain unverified.

- Compute wall lengths, floor area and ceiling height where observed.
- Track scale provenance, units, evidence and uncertainty for every measurement.
- Define stable room, wall, opening and measurement IDs in structured output.
- Test geometry against synthetic scenes with known dimensions.
- Treat initial uncertainty estimates as provisional until calibrated on measured data.

Deliverables: measurement module and versioned JSON schema.
Completion check: synthetic measurement checks pass; sample outputs identify
unverified scale and do not claim centimeter accuracy.

**Task 6: Rendered plan and one-command LiDAR run. Complete locally (candidate baseline).**

Evidence: [PLAN_PIPELINE_ANALYSIS.md](PLAN_PIPELINE_ANALYSIS.md). The installed
`planforge run` command consumes one raw LiDAR capture and an explicit
provisional calibration file, reconstructs its cloud, extracts geometry and
measurements, and exports dimensioned SVG/PNG plus an HTML report. All three
captures complete, including partial/ambiguous outputs. Physical accuracy,
whole-property completeness and the final drift/benchmark gates remain unproven.

- Render walls, dimensions, room labels, areas and ceiling heights into SVG/PNG.
- Build a CLI that runs ingestion through reconstruction, geometry and output.
- Save results, debug artifacts, stage timings and run configuration together.

Implemented command: `planforge run --input data/<capture> --output outputs/<capture> --calibration outputs/calibration/<capture>/calibration.json`.
Completion check: a fresh run generates JSON and a readable plan without manual
edits to intermediate files. This is the first usable product milestone.

### Phase 3: Openings And Whole-Property Layout

**Task 7: Doors, windows and openings. Complete locally (geometry-only candidate baseline).**

Evidence: [OPENING_ANALYSIS.md](OPENING_ANALYSIS.md). Bounded wall gaps require
jamb/header support and representative through-plane sight lines from multiple
source frames before becoming candidates. Width measurements, stable wall
associations, schema v1.1 and plan markers are implemented. Synthetic annotated
door/window checks and miss/phantom-inclusive scoring pass. No actual sample
opening is confirmed; one sample gap remains unresolved. RGB alignment and
semantic verification remain pending, and no physical opening gate is claimed.

- Detect candidate openings from observed wall geometry and RGB evidence once aligned.
- Measure widths and attach openings to stable wall IDs.
- Evaluate missed and phantom openings as well as width error.

Completion check: synthetic and annotated checks cover detection failures;
the measured benchmark later checks the case-study opening gate.

**Task 8: Multi-room segmentation and stitching. Complete (merged PR #10, assumed-single-property candidate baseline).**

Evidence: [STITCHING_ANALYSIS.md](STITCHING_ANALYSIS.md). Per-capture models combine into one candidate `property.json` with room graph, unverified identity/manual 2D transforms, and overlap checks. Real-sample result under the user-instructed same-property assumption: 1 candidate room, 38 wall runs, 0 openings, 0 adjacency edges, 0 room overlaps. No connected layout, alignment, or physical accuracy is claimed.

- Represent rooms and shared openings as a room graph.
- Segment multi-room captures or combine room inputs into a common property frame.
- Produce one connected layout with correct adjacency and no unexplained overlaps.
- Resolve evidence for shared rooms/openings before combining the three sample captures.

Deliverables: property model, room graph and stitched plan.

**Task 9: Drift correction and ablation. Complete (committed, translation-only loop baseline).**

Evidence: [DRIFT_ANALYSIS.md](DRIFT_ANALYSIS.md). Loop-closure detection with linear translation-only distribution; raw-vs-corrected ablation preserves both runs. Real-sample result: closures 0.175/0.387 -> ~0 on loop captures, exact-zero control on the open capture, and closed-region instability (1 -> 0 rooms, 23 -> 9 walls) under sub-0.2-unit pose redistribution. Rotation drift, scale, and the measured drift gate remain unproven.

- Add loop-closure, pose-graph or plane-based correction based on observed failure modes.
- Preserve raw-pose and corrected runs with the same inputs and settings.
- Compare overlap residuals, closure error and stitched footprints with correction on/off.

Completion check: reproducible drift ablation exists. Using supplied poses as-is
is useful as a diagnostic baseline, but does not satisfy the final drift gate.

### Phase 4: Property Assessment

**Task 10: Damage, concealed-damage rules and scope items.**

- Select at least two damage classes and document model/data provenance.
- Detect or segment visible damage in aligned RGB and project it onto reconstructed surfaces.
- Estimate metric extent when scale and surface evidence support it.
- Emit concealed-damage flags with explicit triggering rules and evidence.
- Attach scope line items to surface IDs, keeping inferred flags distinct from observed damage.

Deliverables: damage module, rule outputs and assessment JSON.
Completion check: annotated data verifies the classes and projection; supplied
captures are not assumed to contain damage. New or staged damage data is needed.

### Phase 5: Add The Other Input Tiers

**Task 11: Video-only reconstruction.**

- Reconstruct from RGB frames without consuming the supplied depth or poses.
- Normalize results into the shared scene contract.
- Establish an explicit scale strategy and report unresolved scale honestly.
- Run the same geometry, measurement, stitching and assessment stages.

The existing `rgb.mp4` files can exercise this path, but they do not by themselves
prove performance on ordinary handheld videos or supply ground truth.

**Task 12: Photos and photo-based property stitching.**

- Accept 2-8 stills per room, including one folder per room for a property.
- Recover available geometry, estimate scale with stated evidence/priors and widen uncertainty when inputs are weak.
- Infer room placement and adjacency and render one whole-property plan.
- Flag ambiguous layouts and test sparse/poor-coverage inputs.

Completion check: both tiers use the same output contract; photo support includes
whole-property stitching. Standalone photo data and validation are still required.

**Task 13: Calibrate uncertainty across tiers.**

- Compare predicted intervals with held-out physical measurements.
- Separate systematic bias, repeatability variation and sensor/scale uncertainty.
- Check interval coverage by tier and condition, not just average error.

Completion check: calibrated intervals accompany every measurement and expand
appropriately for weaker inputs. Until measured data exists, calibration is unverified.

### Phase 6: Prove And Package The System

**Task 14: Capture route and real benchmark. Start preparation early.**

- Choose a reproducible future capture route: our own iOS app or a named stock tool/protocol.
- Publish a device matrix and a one-page capture/export protocol.
- Collect the same rooms at all three tiers, including 3+ rooms and a connector.
- Include a furnished room with two staged damage classes and a repeat capture at one tier.
- Record tape/laser ground truth and cover mirrors, glass, wet-look surfaces and low light.
- Build a benchmark manifest and regenerate errors, interval coverage, repeatability and timing from raw inputs.

The unknown source app for the current samples does not determine our future
capture route. Benchmark preparation can proceed during earlier phases, but
the final measured benchmark cannot be completed from these samples alone.

**Task 15: Head-to-head comparison and shipped fix loop.**

- Compare our LiDAR results with a named/versioned consumer scanning app on two measured rooms.
- Preserve app exports and compare shared dimensions; target beat/tie on at least 70%.
- Identify the worst benchmark gate and record its failing number.
- Declare a root-cause hypothesis, evidence, proposed fix and predicted result.
- Ship the fix and preserve regenerable before/after runs plus a readable code diff.

**Task 16: Reproduction and cold-run readiness.**

- Complete the requirement-to-code/artifact compliance matrix.
- Package dependencies and model retrieval for runs without our infrastructure.
- Verify clean-machine setup and one-command execution on all three tiers.
- Prepare the benchmark report, fix-loop bundle and technical report of at most six pages.
- Rehearse a live run on an unseen property using the published capture route.
- Add the requested final reproduction README only when authorized; the current instruction is to keep it absent.

Completion check: reported numbers are regenerable and an unseen capture runs
without sample-specific tuning or manual intervention.

## Final Acceptance Targets

These are case-study targets, not achieved results. See [04-GATES.md](04-GATES.md)
for details; unspecified Round-1 criteria are not invented here.

| Requirement | Target / evidence |
| --- | --- |
| Opening widths | Within 2 cm on at least 85%; missed/phantom detections count as misses |
| Ceiling height | Within 1.5 cm per room; repeat-capture spread at most 1 cm |
| Wall repeatability | Within 1 cm or 0.5% per wall across same-tier captures |
| Drift | Explicit correction and footprint ablation on/off |
| Photo wall lengths | Within +/-8%, with calibrated intervals |
| Video wall lengths | Within +/-3%, with calibrated intervals |
| Photo property layout | Correct adjacency, no overlaps, footprint within +/-8% |
| Head-to-head | Beat/tie incumbent on at least 70% of shared dimensions |
| Setup and execution | Clean-machine reproduction in under 15 minutes; one command per capture |
| Output | Plans, measurements, damage, concealed flags and scope items; JSON plus rendered plan |
| Final evidence | Compliance matrix, capture route, reproduction bundle, benchmark, fix loop, technical report and raw benchmark data |

## Progress Rules

- Update this roadmap after each task with status, evidence paths and remaining limitations.
- Mark a task complete only when its completion check and relevant tests pass.
- Keep captures immutable and keep `data/`, `docs/` and generated `outputs/` out of Git.
- Keep implementation commits incremental; distinguish local checks from CI and real measured validation.
- Add libraries and abstractions as their phase needs them; the final stack in the design doc is not all installed today.
- Prioritize the reconstruction and floor-plan pipeline; web dashboards, APIs and unrelated assistant features are outside the current roadmap.

Current next action: **Task 10, damage, concealed-damage rules and scope items**, needing new or staged damage data.
