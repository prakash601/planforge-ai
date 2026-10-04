# Task 7: Geometry-Only Opening Candidates

Updated: 2026-10-04. Committed. Docs are published; `data/` and `outputs/` remain gitignored.

## Implemented Scope

Task 7 adds conservative wall-gap candidates, provisional door/window classes,
width measurements, stable wall associations, schema v1.1, plan overlays and
annotation scoring. It does not establish RGB timestamp/pose alignment, train
a semantic door/window detector or prove the case-study 2 cm / 85% opening gate.

The existing raw-to-plan command now runs opening detection and attachment
between base measurements and rendering. It saves `debug/openings.json`,
records the opening configuration/timing and exports schema `1.1.0`.

```sh
.venv/bin/planforge run --input data/c00a170fe1 \
  --output outputs/task7-pipeline/c00a170fe1 \
  --calibration outputs/calibration/c00a170fe1/calibration.json
```

For analysis from existing full Task 3/4 artifacts:

```sh
.venv/bin/python scripts/detect_openings.py \
  --scene outputs/reconstruction/1a8384c3f6 \
  --geometry outputs/geometry/1a8384c3f6/geometry.json \
  --output outputs/task7/1a8384c3f6
```

This emits `openings.json`, schema-valid `measurements.json`, SVG/PNG/report and
an `opening_analysis_only` run marker. It is not a fresh raw reconstruction.
The standalone analysis command does not provide the full pipeline's staged
publication guarantees. Source artifact trees are protected from overwrite.

## Detection And Evidence

Only candidate wall planes with a usable provisional floor frame are examined.
The full filtered cloud is used, not the browser preview. Confidence label 2
is the inherited acceptance policy, not an independently verified sensor
confidence semantics. Plane-local position/height occupancy uses bounded arrays;
SciPy connected components find empty regions. No rectangular room prior or
sample-specific IDs are built into detection.

Default thresholds, all in unverified pose units:

| Setting | Default |
| --- | ---: |
| Grid cell size | 0.1 |
| Plane-distance tolerance | 0.06 |
| Width range | 0.4-3.0 |
| Minimum gap height | 0.4 |
| Minimum floor-connected gap height | 1.3 |
| Floor-contact allowance | 0.2 |
| Minimum occupied border fraction | 0.55 |
| Minimum empty-component rectangularity | 0.8 |
| Minimum camera/point clearance from plane | 0.15 |
| Minimum representative crossing sight lines | 8 |
| Minimum supporting source frames | 2 |
| Maximum grid cells per surface | 200,000 |

A gap touching an outer side or upper wall-grid boundary is rejected because
the jamb/header is unobserved. Interior gaps need jamb, header and sill support;
floor-connected gaps need jamb/header support and sufficient height. Nonrectangular
or poorly supported voids are rejected rather than assigned a width.

Through-plane evidence uses the segment from each filtered voxel centroid to
its first supporting source-frame camera. The segment must cross the wall
plane with enough clearance on both sides and intersect the candidate gap.
At least eight such segments and two distinct frame indices are required.
These are **representative reconstructed sight lines, not original depth rays**;
voxel fusion and pose drift can make them inaccurate. Frame count does not
establish independence, semantic correctness or statistically calibrated certainty.

A bounded supported gap without sufficient crossing evidence remains under
`unresolved_gaps`, with no opening measurement. Occluded, glass/invalid-depth or
closed-door cases may be missed. No predicted list means no supported detections,
not proof that the space has no doors/windows.

Door/window labels describe geometry only: floor-connected versus enclosed
gap. They remain `status=candidate` and `opening_semantic_classes_unverified`.
No RGB evidence is used while its alignment remains unverified.

## Model And Rendering

`schema-v1.1.json` is packaged alongside the unchanged v1.0 schema. Validators
select an explicit supported version, check reference/ownership/source-surface
consistency and preserve old Task 5/6 artifacts.

An opening inside an observed wall extent references that wall (`contained`).
A doorway separating two observed runs references both nearby jamb runs
(`adjacent_support`); its primary wall ID is a deterministic member of the
support set. No artificial continuous wall is inserted into an open gap.
Unsupported wall association prevents the candidate from entering the model
and is counted in provenance as `unassociated_candidates`.

Opening IDs use capture, source plane, rounded canonical endpoints and height
extent. Width is measured from those plane-local endpoints. Its provisional
sensitivity allowance is twice (grid size + plane tolerance + median plane
residual); physical interval/confidence level remain null. Detection error,
wrong semantic class, unknown scale, bias and drift are not covered by that range.

Plans render visible candidates as red dashed indexed segments and width tables,
not verified door swings/window symbols. Candidates outside a closed-region
view may appear in the table without a map marker; the region view already
states that other observed runs are omitted. JSON retains every associated
candidate. Mobile table IDs/values stay on one line.

## Annotation Evaluation

```sh
.venv/bin/python scripts/evaluate_openings.py \
  --detections outputs/task7/synthetic/openings.json \
  --annotations outputs/task7/synthetic/annotations.json \
  --width-tolerance 0.11 \
  --output outputs/task7/synthetic/evaluation-cli.json
```

Annotations contain `surface_id`, `kind`, plane-local `interval` and
`height_interval`. They refer to the same plane-local frame as the detection.
SciPy Hungarian assignment matches same-surface rectangles one-to-one with
IoU >= 0.3. Reports include unmatched annotations (misses), unmatched candidates
(phantoms), width error and class agreement. The pass fraction divides passing
matches by annotated count plus phantom count; unmatched annotations do not
vanish from the denominator. Empty/empty returns null, not a perfect score.

The CLI scores detector proposals, before final wall association. A future
end-product benchmark must also count association failures/missing emitted
openings. The explicit tolerance is in pose units, not a 2 cm claim. Current
annotations are synthetic fixtures, not manually verified real-sample labels.

## Actual Sample Findings

| Capture | Wall planes examined | Associated candidates | Retained unresolved gaps | Status |
| --- | ---: | ---: | ---: | --- |
| `1a8384c3f6` | 11 | 0 | 1 | Complete candidate analysis |
| `c00a170fe1` | 12 | 0 | 0 | Complete candidate analysis |
| `c7d28f72c6` | 0 | 0 | 0 | Orientation unresolved/ambiguous |

The first capture's unresolved gap is on `surface-002`: approximately 0.7 pose
units wide, height range [0.3, 1.8], with supported borders but zero representative
crossing sight lines. It is not asserted to be a window. It may reflect missing
coverage, obstruction or another reconstruction effect. No sample-derived recall,
phantom rate or physical width accuracy can be claimed without annotations.

## Verification

- **127 Python tests pass locally**, including the previous 104 and 23 additional
  opening/integration checks. Door and window fixtures have explicit known
  plane-local annotations; tests cover widths, wall associations, solid walls,
  missing jamb/header, occlusion, missing/multiple-frame sight-line evidence,
  low-confidence rays, rotated/translated frames, bounded grids, provenance,
  stable repeat IDs, invalid references/configuration and evaluation failures.
- Miss/phantom scoring tests explicitly verify duplicate detections, missing
  detections, wrong widths and wrong classes reduce the pass fraction.
- All three full-scene opening analyses repeat with identical detection content.
  A real full raw-to-plan run of `c00a170fe1` includes the new stage and produces
  schema v1.1 plus diagnostics, in approximately 11.7 s on this local run.
  No new full raw runs of the other two captures are claimed in Task 7.
- **Four Playwright tests pass**: desktop/mobile real reports across all three
  samples, plus desktop/mobile explicitly synthetic opening fixture. Checks
  include nonblank images, marker pixels, report links/schema, overflow, SVG
  bounds and screenshots. The mobile synthetic fixture was visually inspected;
  table wrapping was corrected and browser checks repeated.
- The annotated synthetic doorway evaluation has one match, zero misses/phantoms,
  negligible numeric width error at tolerance 0.11 pose units. It is not a
  measured physical-room result or the case-study opening gate.
- Source distribution/wheel include the new opening modules and both schemas.
  No dependency changes were needed. Ruff and whitespace checks pass locally.
- No GitHub CI result exists for these uncommitted changes. RGB alignment,
  semantic validation, real annotations, physical scale, corrected poses and
  the measured opening gate remain pending.

The local inspection server is `http://127.0.0.1:8769/`; `synthetic/index.html`
is explicitly a generated example, not one of the supplied captures.

## Next

Task 8: multi-room candidate segmentation and stitching, with explicit
adjacency/identity evidence. Do not combine the three sample captures merely
because their folders exist; their shared-property relationships are unknown.
