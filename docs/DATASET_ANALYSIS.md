# Task 1: Dataset Analysis

Inspected 2026-10-02 using the local captures, not inferred from the case study.
Source report: `outputs/dataset-inspection.json` (gitignored).
The case study defines the eventual product requirements; it is not an instruction
to upload data or build every tier during this inspection milestone.

## Reproduction

From the repository root:

```sh
uv sync --locked --extra dev --python 3.11
uv run --locked --extra dev python scripts/inspect_capture.py data --samples 8 --output outputs/dataset-inspection.json
uv run --locked --extra dev python -m pytest -q
```

Use a single capture path instead of `data` to inspect one capture. Without
`--output`, JSON goes to stdout and progress goes to stderr. Invalid captures
produce an error record and exit code 1; inspection continues for other captures.
CLI usage errors return 2. Output paths inside the input tree are rejected.
Source captures are read only. Sequential video decoding can take a few minutes.
The locked environment records NumPy 2.4.6, Pillow 12.3.0, OpenCV headless
4.14.0.94 and pytest 9.1.1. The local successful run used Homebrew Python 3.11.10.
The initial Conda Python 3.11.7 environment crashed during pytest's `readline`
import, before tests ran; replacing the virtual environment resolved it.

## Inventory

All three captures have this structure:

```text
data/<capture_id>/
  depth/000000.png ...
  confidence/000000.png ...
  odometry.csv
  imu.csv
  camera_matrix.csv
  rgb.mp4
```

There are 16,711 paired depth/confidence frames in total. Source file sizes sum
to 873,680,157 bytes (about 833.2 MiB), excluding `.DS_Store`; filesystem disk
usage can be larger. No mesh files were found inside the capture directories.
Room names, capture-device/exporter metadata and measured ground truth were not
supplied in this structure. Capture length alone cannot establish room identity.

| Capture | Paired depth/pose frames | Pose duration (s) | IMU rows | RGB frames reported / decoded | Source bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| `1a8384c3f6` | 5,251 | 114.783 | 11,397 | 5,251 / 5,250 | 276,731,533 |
| `c00a170fe1` | 1,715 | 37.172 | 3,689 | 1,715 / 1,714 | 88,503,534 |
| `c7d28f72c6` | 9,745 | 214.929 | 21,339 | 9,745 / 9,744 | 508,445,090 |

Depth and confidence IDs exactly match odometry IDs for all three captures,
starting at `000000`, with no gaps or duplicates. Odometry and IMU timestamps are
finite and strictly increasing. Median pose rate is approximately 59.99 Hz,
but RGB container average rates are approximately 45.75, 46.12 and 45.34 fps.
Timestamp gaps mean the median pose interval does not imply a fixed-rate stream.
IMU median rate is approximately 99.3 Hz; it is a separate timestamped stream,
not one IMU row per image.

## Images And Video

All 16,711 depth image headers describe 256 x 192 16-bit grayscale PNGs
(Pillow `I;16`). All paired confidence headers describe 256 x 192 8-bit
grayscale PNGs (`L`). Eight evenly spaced pairs per capture were decoded.
Observed confidence labels were 0, 1 and 2. Low/medium/high confidence is a
plausible interpretation, not verified exporter metadata.

| Capture | Minimum / maximum encoded depth across sampled frames |
| --- | ---: |
| `1a8384c3f6` | 242 / 7,855 |
| `c00a170fe1` | 275 / 5,477 |
| `c7d28f72c6` | 604 / 7,781 |

These are sampled raw values, not global extrema or meters. Millimeters are a
plausible hypothesis, but the files do not establish the scale. The report also
records nonzero depth percentiles, zero fractions and confidence label counts
for each sampled frame. Pixel contents of unsampled PNGs remain unchecked.

RGB is 1920 x 1440 in every capture. OpenCV's FFMPEG backend reports N video
frames, but sequential `grab()` succeeds only N-1 times in all three captures.
The first and middle frames were retrieved successfully; the reported final
frame was unavailable. Initial random seeks to that final frame also failed.
This may reflect export/container or decoder behavior; it is not yet proven
that the source lost a sensor frame. Do not silently truncate depth/pose data
or assume which pose corresponds to a missing RGB frame. Compare an independent
decoder and exporter timestamps before RGB projection or damage analysis.

## Calibration And Poses

Task 2 follow-up: [CALIBRATION_ANALYSIS.md](CALIBRATION_ANALYSIS.md) now records
the preferred diagnostic convention and the RGB edit-list investigation. The
initial inspection observations below are preserved; the later decoder check
recovers all expected RGB frames with edit lists ignored. Synchronization and
physical scale are still unverified.

`odometry.csv` contains timestamp, string frame ID, x/y/z position,
qx/qy/qz/qw quaternion, fx/fy/cx/cy and optional distortion-center columns.
The loader preserves the header's quaternion ordering without claiming a
camera-to-world or world-to-camera convention. All quaternion norms are within
approximately 0.0000002 of one. That confirms normalization, not axis semantics.
IMU columns are timestamp, a_x/a_y/a_z and alpha_x/alpha_y/alpha_z. Their physical
units, gravity handling and reference frame remain unconfirmed.

Per-frame fx/fy range from about 1,581 to 1,618; principal points are about
(955,718). They exceed the 256 x 192 depth dimensions and fit the 1920 x 1440
RGB resolution. `camera_matrix.csv` contains a finite 3 x 3 pinhole matrix.
The raw per-frame calibration changes slightly over time and is preserved.

If the exporter confirms the depth image is aligned to the same uncropped RGB
camera, the resolution ratios are 256/1920 and 192/1440 (both 1/7.5).
Scaling fx, fy, cx and cy by that ratio is then a candidate conversion. Crop,
orientation, pixel-center conventions and depth registration must be verified
before adopting it. The earlier design doc's claim that these were ready-to-use
depth intrinsics was incorrect and has been corrected.

Position columns span several raw coordinate units in x/z and much less in y.
That suggests mostly horizontal handheld motion; it does not prove meters,
the gravity axis, room dimensions or capture coverage. No coordinate transform
or depth-unit conversion is performed by Task 1.

## Loader Contract And Pipeline Readiness

`src/planforge/ingestion/lidar.py` implements
`CaptureLoader.load(path) -> LidarCapture`. It validates CSV columns and numeric
values, time ordering, quaternion normalization, calibration shape and exact
image/odometry pairing. It returns immutable frame records with raw calibration,
raw poses, paths, timestamps and lazy depth/confidence pixel readers. It also
returns the IMU records, RGB path and global camera matrix. RGB decoding and
image-content checks belong to the inspector, not the metadata loader.

The loader returns an upstream raw capture, not a reconstructed `SpatialScene`.
This keeps unverified units and reference frames out of the geometry pipeline.
No photo/video-only loaders or geometry placeholders were added.

| Next stage | Available evidence | Remaining requirement |
| --- | --- | --- |
| Depth back-projection | Depth, per-frame calibration, confidence | Confirm depth scale, registration and intrinsics scaling |
| Cloud fusion | Time-ordered position and quaternion | Confirm units, pose direction, camera axes and gravity |
| RGB surface projection | RGB, calibration, matching reported counts | Resolve N-1 decoded frames and establish timestamp alignment |
| Room geometry | Candidate RGB-D streams | Reconstruct and visually inspect coverage; identify captures |
| Evaluation | Three source captures | Ground truth dimensions, room labels and repeat captures |
| Photos/video-only tiers | No standalone samples identified | Separate tier data and scale strategy |
| Multi-room/damage | No geometry or labels yet | Room relationships, surface evidence and damage annotations |

Task 2 can use this loader for a depth/pose viewer and calibration checks.
Metric reconstruction should begin only after the exporter conventions above
are confirmed or explicitly tested against a known physical dimension.

## Validation Boundaries

The inspector checked every CSV record, image ID and PNG header; it decoded
24 depth/confidence pairs and scanned the RGB streams sequentially, retrieving
available requested samples. Warnings are preserved in the report, including
the one-frame discrepancies. It does not claim full PNG pixel validation,
sensor synchronization, calibrated metric accuracy or room coverage.

Synthetic tests exercise valid parsing, unit preservation, missing/extra image
pairs, duplicate IDs, non-finite values, timestamp ordering, invalid quaternion
norms/focal lengths/calibration, confidence labels, image layout, video sampling,
CLI failure reporting and raw-input write protection. CI runs those tests with
synthetic inputs only; local sample captures are never required or uploaded.
`data/`, `docs/`, `outputs/` and `.venv/` remain gitignored. No README was added.
