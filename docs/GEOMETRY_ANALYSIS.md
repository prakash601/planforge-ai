# Task 4: Candidate Room Geometry

Updated: 2026-10-03. Local-only; docs, data and outputs remain gitignored.

## What Is Implemented

`scripts/extract_rooms.py` reads full Task 3 `SpatialScene` artifacts, not browser
previews. It exports a versioned `RoomGeometry`: surface equations and evidence,
candidate roles, provisional orientation, supported wall runs, closed region
polygons, topology diagnostics, flags and source/calibration provenance.

This is a geometry baseline, not a measured floor plan. Scale is unverified,
supplied poses remain uncorrected, and inferred roles/regions are candidates.
Task 5 handles measurement contracts and uncertainty; Task 9 handles drift.

## Algorithm And Evidence

1. Sample at most 40,000 filtered cloud points deterministically. Estimate local
   normals on the full filtered cloud with Open3D, 30 nearest neighbors.
2. Group unoriented normals into at most 12 direction pools (0.2 bin width,
   20-degree alignment). Use Open3D RANSAC in each pool and retain models whose
   supporting normals agree. This prevents horizontal cross-sections through
   vertical walls from dominating unrestricted plane extraction.
3. Fit plane equations to normal-consistent support using SVD; merge coplanar
   models within 5 degrees and 0.06 pose units. Re-expand geometric support within
   the distance threshold to retain corner extents that normal estimation omits.
   Fit support and geometric extent support are both reported; they can overlap
   across intersecting surfaces and are not independent confidence samples.
4. Infer a provisional up direction from broad one-sided planes with stable
   camera clearance. Competing directions, including opposite signs, can produce
   `orientation_ambiguous`; no region is then emitted. Geometry cannot independently
   establish the gravity sign. `--up-vector` is an explicit unverified override,
   not an accuracy assertion. Synthetic rotated-room tests use their known up.
5. Select a broad lower horizontal floor candidate supported by cloud/path
   evidence. Label ceiling candidates only when observed broad horizontal plane
   evidence lies above the camera path. Classify approximately vertical surfaces
   as wall candidates only with sufficient extent and floor contact.
6. Derive wall runs from observed mid-height support, splitting gaps over 0.3
   pose units. Floor/ceiling seams and door headers alone cannot supply a wall
   footprint. Defaults require length 0.8, height 1.2 and floor contact within
   0.3 pose units. Small/short objects are rejected where this evidence permits;
   tall furniture can still resemble a wall and is explicitly a limitation.
7. Intersect supported wall lines, adjusting observed endpoints only within
   0.2 pose units. Shapely nodes/polygonizes the linework and reports dangling
   edges, cut edges and invalid rings. No rectangle or Manhattan prior is used;
   missing walls are not supplied by a hull or bounding box.
8. Accept only valid regions with area at least 1 pose-unit squared, at least
   20 floor-support samples and at least one camera-path sample. Preserve holes
   and per-edge source-surface evidence. Multiple regions are possible, but are
   not certified rooms, room identities or an adjacency graph.

Convex surface envelopes are **display bounds only**: they can span holes or
disconnected patches and must not be interpreted as filled observed surfaces.
The boundary algorithm does not use those envelopes to fabricate room closure.
The plane-search budget (24 default attempts) and unassigned sample count are
reported, including a flag when the attempt budget is reached.

Libraries: Open3D 0.19.0 and Shapely 2.1.2, pinned by `uv.lock`.
Primary references: [Open3D point-cloud plane segmentation](https://www.open3d.org/docs/release/tutorial/geometry/pointcloud.html),
[Shapely polygonize_full](https://shapely.readthedocs.io/en/stable/reference/shapely.polygonize_full.html).

## Supplied Capture Results

| Capture | Planes | Orientation | Wall Runs | Closed Candidate Regions | Status |
| --- | ---: | --- | ---: | ---: | --- |
| 1a8384c3f6 | 15 | Provisional | 19 | 1 | One supported region, remaining wall coverage partial; ceiling unobserved |
| c00a170fe1 | 22 | Provisional | 15 | 0 | Incomplete coverage; two linework regions lack camera-path support; ceiling unobserved; plane budget reached |
| c7d28f72c6 | 24 | Ambiguous | 0 | 0 | Floor/ceiling roles unresolved; plane budget reached |

The first capture's region has 748 sampled floor-support points and 696 camera
samples. It is **not** a complete property footprint or a verified room count.
All captures have unresolved coverage and physical accuracy. Threshold changes
can change candidate topology; increasing junction tolerance is not evidence
that an absent boundary exists.

An exploratory IMU check tested only two acceleration-axis mappings through
nearest supplied pose rotations. Mean normalized-direction concentration was
low (roughly 0.14-0.40 across captures/mappings). This does not validate IMU
semantics, sign, synchronization or gravity. IMU is not used to declare up in
this baseline; the geometry report records that limitation.

## Artifacts And Viewer

Each `outputs/geometry/<capture>/geometry.json` includes equations, candidate
roles, support/residuals, envelopes, wall support and adjusted junction endpoints,
region polygons/holes, world-space overlays, provenance and failure flags.
The browser bundle includes the Task 3 bounded cloud preview and filtered PLY.
It does not copy raw multi-million-point PLYs into this stage.

Viewer controls: plane envelopes, surface selection, wall support traces and
closed-region boundaries. Blue indicates floor candidates, gold ceiling
candidates, rose wall candidates, and grey other/unresolved planes. Purple
lines show wall support traces; orange lines show closed candidate boundaries.
For ambiguous orientation the viewer keeps its display up separate from the
unresolved inference and exposes all detected planes for inspection.

## Reproduction

```sh
uv sync --locked --extra dev --python 3.11
npm ci --prefix viewer
npm run build --prefix viewer
OMP_NUM_THREADS=1 uv run --locked python scripts/extract_rooms.py \
  outputs/reconstruction --output outputs/geometry
uv run --locked python -m http.server 8767 --bind 127.0.0.1 \
  --directory outputs/geometry
```

Open `http://127.0.0.1:8767/`. `--up-vector 0 1 0` is available for an explicitly
assumed direction; it must not be presented as sensor-derived gravity.
The CLI also exposes plane distance, sampling, plane budget and junction
tolerance. All algorithm settings and the source Task 3 fingerprint are exported.
Use `OMP_NUM_THREADS=1` for reproducible serial Open3D experiments; CI sets this
for geometry tests. Exact cross-platform floating-point identity is not promised.

## Verification

Python coverage includes rectangular, L-shaped, rotated and non-orthogonal rooms,
missing ceilings/walls, large support gaps, fragmented coplanar walls, small
furniture, disconnected regions, unvisited-region rejection, orientation-sign
ambiguity, malformed scene arrays and unsupported settings. These are synthetic
geometry checks, not a ground-truth accuracy benchmark on the supplied data.

Browser checks cover desktop/mobile nonblank canvas pixels, all sample captures,
overlay toggles, plane selection, trajectory/rotation, viewport bounds and errors.
A separate intercepted synthetic fixture exercises both exterior and hole
boundary rendering; it is not an additional real-capture result.

Local results: 62 Python tests passed, production viewer build passed, and all
three geometry browser checks passed. Two desktop/mobile checks each also passed
against the updated reconstruction and calibration viewers; the geometry-only
fixture was intentionally skipped on those non-geometry views. Screenshots were
visually inspected. A second serial run over all three scenes produced
byte-identical `geometry.json` files, checked with SHA-256. New GitHub CI has not
been run for these uncommitted changes.

Next: Task 5, measurements and uncertainty. Only supported candidate geometry can
be measured; incomplete/unresolved captures must retain their flags and avoid
invented dimensions. No case-study accuracy gate is claimed passed.
