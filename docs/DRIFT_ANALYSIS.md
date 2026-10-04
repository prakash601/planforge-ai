# Task 9: Drift Correction and Ablation (Translation-Only Loop Baseline)

Updated: 2026-10-04. Committed (PR #11). Docs are published; `data/` and `outputs/` remain gitignored.

## Method

`src/planforge/drift/` implements the failure mode actually observed in the
samples: two captures return near their start while a third ends meters away
on a short path. `DriftConfig` (window 5, ratio threshold 0.05, minimum path
1.0) detects a loop from the supplied trajectory, and `estimate_correction`
distributes the window-averaged closure error linearly across frames
(translation only; quaternions pass through unchanged). Rotation drift is
explicitly not estimated. Without a detected loop the correction is exactly
zero, so the corrected side is identical to the raw-pose baseline by
construction and is not recomputed.

`scripts/ablate_drift.py` runs raw vs corrected reconstructions with identical
settings and compares closure error, raw-vs-corrected cloud distance, early/late
half overlap residuals, surface plane residuals, and room footprints from
`extract_geometry` on both scenes. Existing raw artifacts are reused only after
a config and calibration-fingerprint check.

```sh
.venv/bin/python scripts/ablate_drift.py \
  --inputs data/1a8384c3f6 data/c00a170fe1 data/c7d28f72c6 \
  --calibrations outputs/calibration/1a8384c3f6/calibration.json \
                 outputs/calibration/c00a170fe1/calibration.json \
                 outputs/calibration/c7d28f72c6/calibration.json \
  --raw-artifacts outputs/reconstruction/1a8384c3f6 \
                  outputs/reconstruction/c00a170fe1 \
                  outputs/reconstruction/c7d28f72c6 \
  --output outputs/drift
```

## Ablation Findings

| Capture | Loop | Closure before -> after | Cloud median | Overlap median | Footprint |
| --- | --- | --- | --- | --- | --- |
| `1a8384c3f6` | Yes (ratio 0.003) | 0.175 -> 0.0001 | 0.070 | 0.359 -> 0.373 | 1 room (7.96) -> 0 rooms; walls 23 -> 9 |
| `c00a170fe1` | No (ratio 0.22) | 3.178 unchanged, identical | n/a | n/a | n/a (control) |
| `c7d28f72c6` | Yes (ratio 0.004) | 0.387 -> 0.0002 | 0.103 | 0.275 -> 0.227 | 0 rooms both; orientation ambiguous both |

What this means, honestly framed:

- Closure error is removed by construction on loop captures; that is
  self-consistency, not measured accuracy. No ground truth exists.
- The correction is small (max offsets 0.17/0.39 pose units) and surface plane
  residuals barely move (floor 0.0099 -> 0.0088, walls 0.0226 -> 0.0263 on the
  first capture). It sharpens nothing measurable at this magnitude.
- Half-to-half overlap residuals are dominated by coverage differences between
  early and late observations, not by slow linear drift: unchanged on the first
  capture, ~18% better on the third. The metric conflates coverage with drift
  and is reported as a consistency signal, not a drift proof.
- The strongest finding is topological sensitivity: on `1a8384c3f6`, sub-0.2-unit
  pose redistribution collapses wall runs from 23 to 9 and loses the single
  closed candidate region, while orientation stays provisional. The Task 4
  region is not stable under drift-scale pose changes. Footprint comparisons
  across drift states must carry that instability explicitly.
- The open-trajectory capture is a clean control: exactly-zero correction,
  nothing recomputed, nothing claimed.

## Verification

- **8 new drift tests pass**: loop detection/correction/closure removal,
  exact-zero open-trajectory correction, short-path rejection, invalid input
  rejection, frame identity preservation, cloud-distance calibration,
  overlap sensitivity, and correction-index bounds.
- Neighboring suites rerun: 25 passed
  (`test_drift`, `test_stitching`, `test_pipeline`).
- Real-sample ablation completed on this machine (34 s + 73 s corrected
  reconstructions; full corrected artifacts preserved under `outputs/drift/`).
  Corrected-run determinism was not independently re-verified in Task 9.
- Ruff is not installed in this checkout; no lint claimed. No GitHub CI result
  exists for these uncommitted changes.

## Limits And Next

Rotation drift, gravity alignment, inter-capture alignment, physical scale, and
the case-study drift gate all remain unproven; supplied poses are still the only
odometry source. The pipeline default stays raw-pose; no `--correct-drift` flag
was added, so the baseline cannot be silently replaced.

Task 10: damage, concealed-damage rules, and scope items on aligned RGB
projected onto reconstructed surfaces. New or staged damage data is needed;
the supplied captures are not assumed to contain damage.
