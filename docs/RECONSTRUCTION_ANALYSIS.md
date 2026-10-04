# Task 3: Reusable Scene Reconstruction

Updated: 2026-10-03. Local-only: docs, data and outputs remain ignored.

## Scope

`scripts/reconstruct_capture.py` consumes either one raw capture or a directory
of captures, plus an explicit calibration JSON from Task 2. It produces a
depth-only raw-pose baseline. It does not correct drift, align RGB, recover
gravity, extract room geometry or certify physical dimensions.

The common `SpatialScene` contract contains filtered XYZ, ordinal confidence,
first supporting selected frame, observation count, selected-frame trajectory,
frame IDs/timestamps/source indices, calibration provenance and diagnostics.
All coordinates and length thresholds use hypothesized pose units. The only
current scale status is `unverified`; no configuration can assert metric accuracy.

## Reconstruction Policies

- Default frame step 1: every pose/depth frame across the full capture duration.
- Default pixel stride 4: sample every fourth row and column, not every pixel.
- Raw PLY retains every finite positive-depth sample at that stride, including
  confidence labels 0 and 1. It is not the original dense capture.
- Confidence policy defaults to label 2. Exporter label meanings are unknown;
  this is an explicit ordinal threshold, not a calibrated probability.
- Voxel size defaults to 0.05 hypothesized pose units. Each voxel holds the
  observation-weighted centroid, maximum accepted confidence label, first
  supporting selected frame and count of contributing pixels. Pixel counts
  are not independent-frame support or measurement confidence intervals.
- SciPy cKDTree statistical filtering removes centroids whose mean distance to
  8 neighbors exceeds the global mean plus 2 standard deviations. Legitimate
  sparse surfaces can be removed. The raw cloud is preserved for comparison.
- Cloud memory is capped at 500,000 occupied voxels, with frame-sized input
  buffers, bounded neighbor-query batches and at most 150,000 preview points.
  Loader/trajectory metadata still scales with the number of input frames.
  Exceeding the voxel cap fails explicitly, without silently dropping voxels.
- The initial 0.04 voxel-size trial exceeded the cap on the largest capture.
  The 0.05 default is a documented resource/resolution tradeoff, not an accuracy
  finding. Users can explicitly change size, sampling and memory budget.
- Reconstruction occurs in a temporary directory. Computation failure cleans
  temporary files and preserves previous completed per-capture artifacts.
  Publication is per capture, not a transactional multi-capture batch; an I/O
  failure during publication can interrupt replacement of artifacts.

## Artifacts

Each capture directory contains:

- `raw.ply`: streamed, sampled, pre-confidence/pre-outlier observations.
- `cloud.ply`: filtered voxel centroids with confidence and first-support index.
- `cloud.npz`: full filtered arrays, including observation counts.
- `spatial_scene.json`: versioned scene metadata, provenance, full selected
  trajectory and frame list, configuration, counters and artifact paths.
- `scene.json`: bounded filtered preview for the viewer.
- `raw_scene.json`: bounded raw preview sampled evenly within each frame.

The SHA-256 fingerprint covers decoded full depth/confidence images and pose /
intrinsics metadata for selected frames. It excludes unused RGB pixels and IMU.
The selected hypothesis is copied into every scene, so replay does not depend
on the calibration file staying unchanged at its recorded source path.

The viewer switches between raw observations and filtered voxels and downloads
the full corresponding PLY. Displayed previews may contain fewer points than
the full artifacts. Fused clouds do not offer a misleading single-frame mode;
the frame slider selects trajectory positions. No RGB texture is shown.

## Reproduction

Run from the repository root after Task 2 artifacts exist:

```sh
uv sync --locked --extra dev --python 3.11
npm ci --prefix viewer
npm run build --prefix viewer
uv run --locked python scripts/reconstruct_capture.py data \
  --calibration outputs/calibration/1a8384c3f6/calibration.json \
  --output outputs/reconstruction
uv run --locked python -m http.server 8766 --bind 127.0.0.1 \
  --directory outputs/reconstruction
```

Open `http://127.0.0.1:8766/`. Reconstruction requires an explicit hypothesis,
not a hidden default calibration. Output inside the raw input tree is rejected.
All filter/sampling settings can be overridden with CLI flags; use `--help`.

## Verification

Synthetic tests cover fusion counts, invalid depth and confidence rejection,
frame sampling, standard binary PLY sizes, provenance, deterministic repeat
exports, bounded previews, voxel-cap failure, raw-write protection, failed-run
preservation and isolated-point rejection. Physical accuracy, drift improvement
and ground-truth filter quality remain unverified.

Local verification: 44 Python tests passed; production viewer build passed.
Two Playwright checks passed at 1440x900 and 390x844, covering all three
captures, raw/filtered switching, downloads, confidence filtering, trajectory,
rotation, non-background canvas pixels, screenshots and viewport bounds.
Desktop/mobile screenshots were visually inspected. These are local checks,
not a claim that new code has run in GitHub CI.

| Capture | Frames processed | Raw sampled points | Confidence rejected | Fused voxels | Outliers removed | Filtered points |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1a8384c3f6 | 5,251 | 16,131,072 | 1,818,089 | 195,713 | 5,572 | 190,141 |
| c00a170fe1 | 1,715 | 5,268,480 | 369,239 | 53,188 | 1,154 | 52,034 |
| c7d28f72c6 | 9,745 | 29,936,640 | 3,105,759 | 360,446 | 10,849 | 349,597 |

All 16,711 input frames were processed at stride 4, with no invalid sampled
depth in these captures. The combined run took 101.58 seconds; macOS
`/usr/bin/time -l` reported maximum resident size 434,601,984 bytes (414.5 MiB)
and peak memory footprint 376,408,640 bytes. These are local machine results,
not portability or performance guarantees.

Repeating the complete 1,715-frame capture produced byte-identical `raw.ply`,
`cloud.ply`, `cloud.npz`, both viewer previews and `spatial_scene.json`, checked
using SHA-256. Synthetic repeatability is also covered in the test suite.
The two larger captures were not independently repeated in full.

Browser command (server must already be running):

```sh
cd viewer
PLANFORGE_VIEWER_URL=http://127.0.0.1:8766 npm test \
  -- --output=../outputs/reconstruction-browser-tests
```

Task 4 is next: gravity/surface evidence, observed floor/ceiling/walls and room
boundaries. Reconstruction alone is not a floor plan or an accuracy benchmark.
