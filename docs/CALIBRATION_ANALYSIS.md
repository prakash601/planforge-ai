# Task 2: Calibration Investigation And Diagnostic Viewer

Completed locally on 2026-10-02 using only the three supplied captures.
Exporter/device metadata and measured dimensions are still unavailable.
This report records a diagnostic preference, not certified metric calibration.

## Result

The same hypothesis wins independently in all three captures:

```json
{
  "depth_scale": 0.001,
  "intrinsics": "rgb_scaled",
  "camera_axes": "opencv",
  "pose_direction": "camera_to_world"
}
```

Depth is multiplied by 0.001 into hypothesized pose-coordinate units. If the
pose coordinates are meters, this corresponds to millimeter-encoded depth;
physical meters have not been independently established. Camera axes in this
hypothesis are x right, y down, z forward. The xyzw quaternion supplies camera
rotation into the world, with x/y/z position as the camera center.

For 1920 x 1440 RGB and 256 x 192 depth, fx/cx and fy/cy are multiplied by
1/7.5. Per-frame intrinsics are retained. This convention gives coherent
wall-like surfaces in the inspected short sequences. It does not prove the
exporter's crop, pixel-center convention, registration or global physical scale.

## Reproduce

From the repository root:

```sh
uv sync --locked --extra dev --python 3.11
npm ci --prefix viewer
npm run build --prefix viewer
uv run --locked python scripts/calibrate_capture.py data --output outputs/calibration
uv run --locked python scripts/check_rgb.py data --output outputs/calibration/rgb-check.json
uv run --locked python -m http.server 8765 --bind 127.0.0.1 --directory outputs/calibration
```

Open `http://127.0.0.1:8765`. The server exposes only the generated diagnostic
directory. The built viewer bundles Three.js and icons locally, so viewing does
not fetch CDN assets. Dependency installation requires network access; subsequent
diagnostic runs and viewing operate locally.

Use a single capture path to inspect it alone. To replay an explicit hypothesis,
pass `--config outputs/calibration/<capture_id>/calibration.json`. To select a
different short sequence, set `--start-frame`, `--frames` and `--frame-step`.
Use a distinct output directory when preserving comparisons. `--scales` accepts
positive depth-scale candidates. Automatic ranking is provisional; a manual
configuration is recorded as such and does not acquire ground-truth validation.

Build the viewer before generating artifacts. If assets are absent, the command
still produces the point clouds and reports and explicitly warns that the browser
viewer was not copied. Rebuild and rerun to include it.

## Hypothesis Comparison

Forty hypotheses were tested: five depth scales (0.0005, 0.001, 0.002, 0.01, 1),
scaled/as-recorded intrinsics, OpenCV/OpenGL camera axes, and camera-to-world/
world-to-camera pose direction. Rotation and inverse transforms use SciPy's
rotation implementation; supplied poses are never optimized during Task 2.

Each capture contributes five windows distributed through its duration and
frame pairs separated by 30 or 90 records. Both projection directions are
scored, yielding 20 directional comparisons per capture and 60 per hypothesis.
Source pixels are sampled every four pixels with confidence label at least 2.
The label is a sampling policy, not a claim that the unknown exporter guarantees
a particular uncertainty level.

Back-projection uses the pinhole equations x=(u-cx)z/fx, y=(v-cy)z/fy. Source
points transform into the target camera and project onto its depth image.
Comparisons require valid target neighbors, confidence support and no large
local depth discontinuity. Target surface normals come from neighbor cross
products. Both relative depth error and relative point-to-plane error contribute
to the score, with penalties for unsupported overlap.

The relative residual terms are clipped at 5% depth and 3% point-to-plane error.
An inlier uses less than 3% depth and 2% point-to-plane error. These are diagnostic
settings, not case-study accuracy gates. Lower scores are better (0-1). A low
absolute residual alone cannot reward collapsing the cloud to a tiny scale.

| Candidate | Aggregate score |
| --- | ---: |
| 0.001, RGB-scaled, OpenCV, camera-to-world | 0.71974 |
| 0.002, RGB-scaled, OpenCV, camera-to-world | 0.85672 |
| 0.01, RGB-scaled, OpenCV, camera-to-world | 0.88514 |
| 1.0, RGB-scaled, OpenCV, camera-to-world | 0.89077 |
| 0.0005, RGB-scaled, OpenCV, camera-to-world | 0.91589 |
| 0.001, RGB-scaled, OpenCV, world-to-camera | 0.95037 |
| 0.001, RGB-scaled, OpenGL, camera-to-world | 0.96949 |

| Capture | Selected score | Mean supported overlap | Median of pair median relative depth errors | Median of pair median plane residuals, pose units |
| --- | ---: | ---: | ---: | ---: |
| `1a8384c3f6` | 0.7136 | 37.8% | 0.604% | 0.00634 |
| `c00a170fe1` | 0.7247 | 38.7% | 1.310% | 0.00968 |
| `c7d28f72c6` | 0.7209 | 37.0% | 0.710% | 0.00795 |

The winner's margin over the next tested candidate is about 0.137. All captures
prefer it, but the absolute score remains high because unsupported overlap is
penalized. The conditional residuals above apply only to supported projections;
they are not room-dimension errors, confidence intervals or accuracy claims.
Occlusion, motion, confidence policies and sensor artifacts affect these numbers.
Unexamined axis permutations, image orientation/cropping and pixel-center
conventions remain possible. Per-pair values and all candidates are retained.

## RGB Frame-Count Investigation

A separate FFmpeg 7.1 CLI path reproduced the OpenCV count discrepancy. Ignoring
MP4 edit lists recovered the full reported count, without decoder error messages:

| Capture | OpenCV / FFmpeg default | FFmpeg ignoring edit lists | Depth/pose frames |
| --- | ---: | ---: | ---: |
| `1a8384c3f6` | 5,250 | 5,251 | 5,251 |
| `c00a170fe1` | 1,714 | 1,715 | 1,715 |
| `c7d28f72c6` | 9,744 | 9,745 | 9,745 |

This supports a container timeline/edit-list explanation, rather than a missing
encoded sensor frame. FFmpeg documents that edit lists modify the stream index;
`-ignore_editlist 1` bypasses that behavior. This is a separate command/version
path, not an independent codec implementation, since OpenCV also uses FFMPEG.
The result does not identify which original sample was excluded under the
default timeline and does not establish frame-to-pose timestamp alignment.

Task 2 leaves RGB projection disabled. Before damage projection or textured
reconstruction, compare presentation timestamps against sensor timestamps and
choose an explicit timeline mapping. Do not repair alignment by truncating
depth/poses or matching frame counts alone. Source videos were not modified.

## Artifacts And Viewer

`outputs/calibration/` is gitignored and contains:

- `diagnostics.json`: candidate ranking, pair scores, per-capture winners, sampling/export settings and limitations.
- `manifest.json`: viewer capture list, chosen hypothesis and leading candidates.
- `rgb-check.json`: FFmpeg version, default/edit-list counts and decoder messages.
- `<capture>/calibration.json`: explicit working hypothesis for replay.
- `<capture>/cloud.ply`: binary PLY with xyz, confidence label and frame index.
- `<capture>/scene.json`: sampled points, frame IDs/timestamps and trajectory.
- `index.html` and `assets/`: locally bundled interactive viewer.

Each default scene contains 36 frames, starting at record 0 with a step of 30,
and 198,144 nonzero-depth points sampled at pixel stride 3 before confidence
filtering. These are short-sequence diagnostic clouds, not full reconstructions,
meshes or cleaned metric models. No outlier removal, drift correction or room
segmentation is applied. The trajectory uses the same selected transform convention.

The viewer switches between captures and sequence/single-frame modes, selects
frames, filters confidence labels, toggles the trajectory, changes point size,
fits the scene, auto-rotates and downloads the PLY. It continuously labels scale
as unverified. Screenshots show coherent wall-like patches and trajectories,
with incomplete coverage and artifacts still visible for later investigation.

## Verification

Python tests cover scaled back-projection, axis transforms, pose inversion with
rotation of translation, known synthetic plane motion, unsupported overlap,
invalid hypotheses, artifact provenance and write protection, plus ingestion
regressions. The last local run passed 27 tests.

The viewer production build passed. Playwright tests passed at 1440 x 900 and
390 x 844, covering all three captures, nonblank canvas-pixel checks, animated
rotation, frame selection, confidence filtering and viewport bounds. Screenshots
were visually inspected and are under `outputs/browser-tests/`. CI is configured
for Python tests and the viewer build; these checks have not run on GitHub for
this unpushed change. Browser tests currently use generated local scenes and are
not claimed as part of CI.

Browser check setup and run:

```sh
cd viewer
npx playwright install chromium
npm test
```

Run against the server above; `PLANFORGE_VIEWER_URL` can override its address.
Point-cloud generation and every tested decoder run completed locally.
Docs, raw data, build outputs and diagnostic artifacts remain gitignored.

## What Remains Unverified

- Absolute physical scale and centimeter-level accuracy.
- Exporter semantics, exact crop/pixel-center conventions and confidence-label meanings.
- RGB/sensor timestamp alignment despite matching decoded counts.
- Long-sequence drift, complete room coverage, room identity and shared-room relationships.
- Ground-truth dimensions, repeatability, openings, ceiling coverage and damage labels.

Task 3 should now build the reusable scene contract and bounded-memory fusion
using this explicit provisional configuration, preserve scale provenance, and
add filtering and longer-sequence diagnostics. Metric claims still require
independent physical evidence.

## Technical References

- [Open3D depth back-projection equations](https://www.open3d.org/docs/latest/python_api/open3d.geometry.PointCloud.html).
- [FFmpeg MOV/MP4 demuxer and edit-list options](https://ffmpeg.org/ffmpeg-formats.html#mov_002fmp4_002f3gp).

These explain the diagnostic methods; the numerical findings above come from
our local artifacts, not from the reference documentation.
