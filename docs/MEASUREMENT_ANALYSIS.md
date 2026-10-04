# Task 5: Candidate Measurements And Uncertainty

Updated: 2026-10-04. Docs are published; `data/` and `outputs/` remain gitignored.

## Scope And Artifacts

`src/planforge/measurements/` consumes the Task 4 `RoomGeometry` contract.
`scripts/measure_geometry.py` accepts a capture directory containing
`geometry.json` or a root of capture directories. It does not rerun or modify
reconstruction, change poses, infer openings or render a floor plan.

```sh
.venv/bin/python scripts/measure_geometry.py outputs/geometry --output outputs/measurements
```

Each capture gets `measurements.json`; a root manifest lists the artifacts.
The entire batch is computed and validated before measurement files are
published. Validation errors preserve previous outputs. Publication itself is
not a filesystem transaction: an I/O failure can still leave a partial batch.
Input-tree output paths are rejected.

The packaged `src/planforge/measurements/schema-v1.json` defines schema version
`1.0.0`, Draft 2020-12. It is source code, not local documentation, and belongs
in the eventual commit. It is included in the built Python wheel. Validation
adds checks JSON Schema cannot express: finite numbers, unique IDs, references,
owners, polygon validity and interval ordering/containment.

## Measurement Policies

- `observed_run` wall length is the distance between observed support endpoints.
  It is not necessarily the length of a complete physical wall.
- `region_boundary` wall length is a polygon edge between supported candidate
  junctions. Every outer and hole edge needs full source-wall support, not only
  a supported midpoint. These records reference the candidate region ID.
- Floor area is the general Shapely polygon area, with holes subtracted. It is
  not the convex plane envelope or a whole-property footprint.
- Ceiling height requires a single candidate ceiling envelope overlapping at
  least 50% of the region. Floor and ceiling plane heights are evaluated along
  provisional up at overlap vertices. The reported value is the midrange;
  evidence retains minimum/maximum height, including a sloped ceiling.
- Plane envelopes are coverage proxies and may span holes. Their overlap does
  not prove a fully observed ceiling. Multiple supported ceiling candidates
  produce an unavailable value instead of silently choosing one.
- No candidate ceiling produces `status=unavailable`, `value=null` and
  `unavailable_reason=no_supported_ceiling`. Wall-top height is not substituted.
- Partial captures may still emit observed wall lengths, but never an invented
  region, area or room height. Ambiguous/unresolved orientation emits no
  measurements.

## Units And Uncertainty

Schema v1 supports only the current unverified-scale contract. All lengths use
`pose_unit` and areas `pose_unit_squared`; `meters_per_pose_unit=null`.
Every measurement includes source surface IDs, global calibration/source
provenance and an uncertainty object. No physical confidence interval exists:
`physical_interval=null`, `confidence_level=null`, scale status
`physical_interval_status=unbounded_unknown_scale`.

The initial ranges are **deterministic geometry sensitivity**, not statistical
confidence intervals or guaranteed error bounds. They remain uncalibrated:

- Endpoint displacement allowance: plane-distance threshold plus the maximum
  supporting surface median residual. Region edges also include the junction
  tolerance. Length range is nominal length +/- twice this allowance, clamped
  to zero below.
- Area sensitivity: erode/dilate the polygon, including holes, by the boundary
  displacement allowance. The resulting areas give a conditional range.
- Ceiling sensitivity: retain the observed plane-envelope height range, then
  expand by twice the floor/ceiling plane-distance-plus-residual allowance.
- Support count never divides down uncertainty. Fused points share poses and
  sensor errors and are not independent physical measurements.

These ranges assume the supplied scale convention, surface roles, orientation
and topology are fixed. They exclude unknown absolute scale, pose drift,
sensor bias, wrong roles/topology and unobserved geometry. Therefore they must
not be presented as 95% CIs or centimeter accuracy. Task 13 later calibrates
interval coverage on held-out measured data.

## Stable Identity

Room, wall and measurement IDs use a capture namespace and SHA-256 content
identities (20 hex characters). Ring winding and starting vertex are
canonicalized; holes sorted; wall endpoints sorted. Geometry is rounded to six
decimals for identity only, not used to declare measurement precision.

IDs survive array ordering and equivalent ring/endpoint representations.
Geometry revisions can change IDs; these are not physical room identities
across captures. A source geometry hash changes whenever the source contract
changes. Each measurement references its owner; room boundaries reference their
room. Opening IDs/wall references are reserved in the schema, but v1 requires
an empty openings array and an `openings_not_inferred` flag. Empty does not mean
the property has no openings.

## Actual Sample Results

| Capture | Candidate regions | Observed runs | Boundary edges | Measurement records |
| --- | ---: | ---: | ---: | ---: |
| `1a8384c3f6` | 1 | 19 | 4 | 25 |
| `c00a170fe1` | 0 | 15 | 0 | 15 |
| `c7d28f72c6` | 0 | 0 | 0 | 0 |

The first capture's candidate area is **7.956286 pose units squared**; its
conditional sensitivity range is **[5.028223, 11.472698]** in the same area
units. Its four boundary lengths are approximately **2.526766, 2.552327,
3.001873 and 3.273040 pose units**. Its ceiling height remains unavailable.
No square-meter or physical-room-area claim follows from these numbers.

The second capture retains partial support-run lengths only. The third capture
retains its orientation ambiguity and no measurable room geometry. Captures
are not combined and their IDs do not establish adjacency or room identity.

## Verification

- 91 Python tests pass locally, including the 62 earlier checks and 29 new
  measurement checks: rectangle, L-shape, oblique polygon, holes, synthetic
  cloud-to-measurement integration, missing/multiple/nonoverlapping ceilings,
  sloped-height range, stable IDs, uncertainty monotonicity, malformed geometry,
  invalid schema/foreign keys and CLI repeatability/input protection.
- All three sample exports validate against the packaged schema and semantic
  checks. A second full measurement run produces byte-identical JSON for all
  three captures.
- Source distribution and wheel build successfully; the schema resource is
  included. The build's missing-README warning is expected because the user
  explicitly requested no README yet.
- Viewer behavior is unchanged in Task 5; no new browser checks or dimensioned
  UI are claimed. Task 4's viewer remains separate.
- GitHub CI has not run these uncommitted Task 5 changes. No ground-truth
  accuracy, repeat-capture physical repeatability or interval calibration was
  measured.

## Next

Task 6: readable dimensioned SVG/PNG plan and a combined one-command LiDAR
pipeline, retaining these scale/uncertainty limitations and partial outputs.
