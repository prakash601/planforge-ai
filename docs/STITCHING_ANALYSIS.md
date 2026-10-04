# Task 8: Candidate Property Stitching (Assumed Single Property)

Updated: 2026-10-04. Committed (PR #10). Docs are published; `data/` and `outputs/` remain gitignored.

## Assumption

Per user instruction 2026-10-03, all three sample captures are treated as one
property. This is recorded in `property.json` provenance as
`assumed_per_user_instruction`, not evidence. Capture room identities, shared
openings, and inter-capture alignment remain unresolved.

## Implemented Scope

`src/planforge/stitching/` combines validated per-capture measurement models
(schema v1.0/v1.1) into a candidate `property.json` (schema `1.0.0`):

- `StitchingConfig` carries the property ID (default `property-assumed-single`).
- Transforms are 2D rigid `{rotation_deg, translation}` per capture, defaulting
  to identity with `unverified` status and explicit provenance. Optional
  `--transforms` JSON supplies manual unverified alternatives; unknown captures,
  nonfinite values, and path-like property IDs are rejected.
- Rooms, walls, openings, and measurements keep their per-capture stable IDs
  (already capture-namespaced) with an added `capture_id` field and
  `*_property` coordinates in the common frame.
- The room graph has one node per candidate room. Edges come only from explicit
  `--links` manual adjacency; no automatic shared-opening matching is attempted.
  Current samples provide no shared openings, so edges are empty.
- Pairwise room-polygon intersections in the property frame are reported under
  `overlaps` with pose-unit areas. Wall-run crossings across captures are not
  treated as intersections; only closed-region overlaps count.
- `scripts/stitch_property.py` emits `property.json`, `property.svg/png`,
  `index.html`, and `run.json`. Output must sit outside the input trees.

```sh
.venv/bin/python scripts/stitch_property.py \
  --inputs outputs/task7/1a8384c3f6/measurements.json \
           outputs/task7/c00a170fe1/measurements.json \
           outputs/task7/c7d28f72c6/measurements.json \
  --output outputs/property/assumed-single \
  --property-id property-assumed-single
```

## Actual Sample Findings

| Capture | Rooms | Walls | Openings | Note |
| --- | ---: | ---: | ---: | --- |
| `1a8384c3f6` | 1 | 23 | 0 | Single candidate region |
| `c00a170fe1` | 0 | 15 | 0 | Observed runs only, no closed boundary |
| `c7d28f72c6` | 0 | 0 | 0 | Orientation ambiguous, no walls |

Stitched property: 1 room, 38 walls, 0 openings, 0 adjacency edges,
0 room overlaps. Flags include `single_property_assumed_per_user_instruction`,
`transforms_unverified_identity_or_manual`, `partial_captures_without_closed_regions`,
`orientation_unresolved_in_some_captures`, `rooms_unconnected` (single-room variant),
and `no_associated_openings_in_inputs`. This is not a connected whole-property
layout and proves no adjacency, footprint, or physical accuracy. The rendered
common-frame map overlays all runs with identity transforms; cross-capture wall
proximity on that map is not measured intersection evidence.

## Verification

- **7 new stitching tests pass** (namespace/assumption marking, manual
  transforms, overlap detection, manual links, empty-capture handling,
  duplicate/bad-transform/bad-link rejection, bad-polygon rejection).
- Subset rerun: 99 passed (`test_stitching`, pipeline, measurements, rendering,
  plus calibration/ingestion/openings suites excluding reconstruction/geometry);
  targeted rerun of stitching/pipeline/measurements/rendering: 51 passed.
- Real-sample stitch repeats deterministically; `property.json` validates
  against the packaged schema plus foreign-key, polygon, and finiteness checks.
- Ruff is not installed in this checkout, so lint is not claimed for Task 8.
- No GitHub CI result exists for these uncommitted changes. Drift correction
  (Task 9), damage (Task 10), video/photos tiers, and the measured benchmark
  remain pending.

## Next

Task 9: drift correction and ablation (loop-closure/pose-graph or plane-based,
raw-pose vs corrected runs with overlap/closure/footprint comparison). Do not
treat identity stitching as alignment; Task 9 correction applies to
within-capture poses first, with inter-capture alignment still requiring
measured evidence.
