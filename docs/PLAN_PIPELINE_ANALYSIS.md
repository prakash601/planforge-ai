# Task 6: Rendered Plans And One-Command LiDAR Pipeline

Updated: 2026-10-03. Local-only documentation; data and outputs remain ignored.
Tasks 4 and 5 were committed together as `27df1510` because Task 4 was still
uncommitted when the user requested the Task 5 checkpoint. Task 6 is separate
and uncommitted at this verification point. No push, PR or merge was requested.

## Implemented Commands

```sh
uv sync --locked --extra dev --python 3.11
.venv/bin/planforge run \
  --input data/1a8384c3f6 \
  --output outputs/task6/1a8384c3f6 \
  --calibration outputs/calibration/1a8384c3f6/calibration.json
```

The installed console entry point is `planforge.cli:main`. One raw capture
directory is accepted per command. Calibration is explicit and must already
exist; no manual edits to intermediate scene, geometry or measurement files
are needed. Task 2's calibration search is not rerun or silently replaced by
default camera conventions. RGB is used for resolution metadata, not textured
reconstruction or opening inference.

Optional arguments: `--frame-step`, `--pixel-stride`, `--voxel-size`,
`--max-voxels` and `--up-vector`. The CLI sets `OMP_NUM_THREADS=1` if the caller
has not already set it, before importing Open3D. Voxel sizes and other geometry
thresholds are still in hypothesized pose units. All settings are preserved in
the run record, including defaults not exposed as CLI switches.

For a rendering-only iteration from a Task 5 artifact:

```sh
.venv/bin/python scripts/render_plan.py \
  outputs/measurements/1a8384c3f6 \
  --output outputs/plans/1a8384c3f6
```

Its run record says `render_only`, not a fresh reconstruction. The HTML reports
are standalone files with relative local assets; no application server is
required. For convenient in-app inspection and browser tests, a local server
is also serving `outputs/task6` at `http://127.0.0.1:8768/`.

## Outputs And Flow

Raw capture -> ingestion -> RGB resolution -> reconstruction -> candidate
geometry -> measurements/schema validation -> rendering -> completed run.

Each completed capture directory contains:

- `plan.svg`: scalable dimensioned candidate plan.
- `plan.png`: matching fixed-layout bitmap, 1600 pixels wide; height expands
  for longer dimension tables.
- `index.html`: static responsive report, downloadable artifacts, legible
  dimension table and evidence flags.
- `measurements.json`: unchanged Task 5 semantic contract.
- `run.json`: completion status, raw input/calibration paths, explicit selected
  hypothesis, full stage settings, stage/total compute timings, source hash,
  package/runtime versions, artifact index and limitations.
- `debug/geometry.json`: the candidate geometry used for measurement/rendering.
- `debug/reconstruction/`: full raw and filtered PLY, cloud arrays, scene
  metadata and bounded viewer previews from Task 3.

Raw inputs are not modified or copied into Git. Generated cloud evidence can
be large and remains ignored.

## Drawing Policy

Supported closed-region boundaries are rendered with indexed wall references
and a length/sensitivity table. Candidate rooms receive R labels, polygon area
and ceiling height when supported; unavailable ceilings stay unavailable.
Holes remain white exclusions and their boundaries are included. The renderer
uses one coordinate projection for SVG and PNG; font rasterization differs
between the browser's SVG font and Pillow's embedded scalable default font.

When closed regions exist, the region view omits other observed runs and says
so. It must not be read as the whole-property footprint. Without closed regions,
observed wall support is dashed and no area is fabricated. An unresolved or
ambiguous capture produces a visible no-supported-plan-geometry artifact,
not a fake rectangle or blank failed image.

SVG and PNG carry unverified-scale and uncalibrated-sensitivity labels. Units
are pose units, not meters. No verified north arrow or physical scale bar is
invented. The HTML table remains readable on mobile even when the full drawing
is reduced to a preview; the SVG link exposes the full-resolution drawing.

## Publication And Failure Policy

The pipeline stages all artifacts in a temporary sibling directory. Failures
during computation do not replace a previous completed run. Publication moves
an existing matching output to a backup, renames the completed workspace into
place, and restores the backup if that rename fails. Temporary files are
cleaned after success/failure.

The raw input tree, its ancestor directories and unrelated output directories
are rejected. Existing output is replaceable only when its completed run record
matches the input path. This is a local filesystem publication protocol, not
a distributed transaction or a concurrent-writer locking protocol; simultaneous
runs against the same output directory are not supported. A machine crash
between renames is not the same as a caught exception and may require recovery.

## Actual Sample Runs

All three captures were run from raw data through the installed command using
their existing explicit provisional calibration files, with no frame skipping:

| Capture | Frames | Candidate regions | Plan result | Recorded total compute |
| --- | ---: | ---: | --- | ---: |
| `1a8384c3f6` | 5,251 | 1 | Four supported region boundaries; area, unavailable ceiling | 55.99 s |
| `c00a170fe1` | 1,715 | 0 | Fifteen dashed support runs; no floor area | 16.60 s |
| `c7d28f72c6` | 9,745 | 0 | Orientation ambiguous; explicit no-supported-plan result | 199.99 s |

These are local run observations under varying machine load, not a controlled
performance benchmark. The largest run overlapped verification work. The first
plan preview was refreshed after adding area/ceiling sensitivity text; its
recorded timings describe the original complete pipeline invocation.

The first capture's area remains 7.956286 pose units squared, not a verified
square-meter room area. No sample identifies room names, adjacency, device/app,
physical dimensions or damage ground truth. Captures are not stitched together.

## Verification

- **104 Python tests pass locally**, including 13 new rendering/pipeline checks
  on top of the previous 91. Coverage includes SVG/PNG pixel content, dimensions,
  holes, partial/unresolved states, deterministic rendering, escaped text,
  artifact/config/timing preservation, stage failures, rename rollback,
  unrelated-output/raw-input protection and explicit CLI calibration errors.
- **Two Playwright tests pass**, at 1440x900 and 390x844, each exercising all
  three real reports. Tests verify nonblank PNG pixels, image load, links,
  measurement JSON, page overflow, SVG text bounds and absence of page errors.
  Screenshots under `outputs/task6-browser-tests` were visually inspected for
  desktop closed-region and mobile partial-capture reports.
- The wheel and source distribution build; the installed wheel's CLI and
  packaged measurement schema were verified. Existing dependencies were used
  for this package check; it is not a clean-machine or offline cold-run claim.
- A second full run of `c00a170fe1` through the installed wheel produces
  **byte-identical content in all 11 non-timing artifacts**. `run.json` is not
  byte-identical because timings and output run environment are recorded.
- Ruff checks for Task 6 Python files, `uv lock --check` and `git diff --check`
  pass. Docs, data and outputs remain untracked/ignored; no README was added.
- Task 6 has no GitHub CI result yet. Physical accuracy, uncertainty coverage,
  repeat-capture precision, drift correction and whole-property completeness
  remain unverified.

## Next

Task 7 adds candidate doors/windows/openings and stable wall associations, with
miss/phantom cases kept distinct from width accuracy. This will require its own
evidence and tests; an empty opening list today does not prove absence.
