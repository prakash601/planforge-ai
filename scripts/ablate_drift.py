"""Raw-pose vs loop-closure-corrected reconstruction ablation (Task 9).

For each capture: analyze the supplied trajectory, estimate the
translation-only loop correction, and compare raw vs corrected runs with
identical reconstruction settings. Captures without a detected loop use an
exactly-zero correction, so the corrected side is identical by construction
and is not recomputed. Existing raw artifacts are reused after a config and
calibration-fingerprint check; mismatches recompute the raw side explicitly.
"""

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from time import perf_counter

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np

from planforge.diagnostics.artifacts import write_json
from planforge.diagnostics.calibration import Hypothesis
from planforge.drift import (
    DriftConfig,
    analyze_trajectory,
    cloud_distance,
    correct_frames,
    estimate_correction,
    overlap_residual,
)


def load_calibration(path):
    payload = json.loads(Path(path).read_text())
    payload.pop("key", None)
    return Hypothesis(**payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", type=Path, required=True,
                        help="Raw LiDAR capture directories")
    parser.add_argument("--calibrations", nargs="+", type=Path, required=True,
                        help="Explicit provisional calibration JSON per input, in order")
    parser.add_argument("--raw-artifacts", nargs="+", type=Path, required=True,
                        help="Existing raw-pose reconstruction dirs per input, in order")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--pixel-stride", type=int, default=4)
    parser.add_argument("--voxel-size", type=float, default=0.05)
    parser.add_argument("--skip-geometry", action="store_true",
                        help="Skip footprint comparison via room geometry")
    args = parser.parse_args()
    try:
        from planforge.diagnostics.artifacts import rgb_metadata
        from planforge.geometry import GeometryConfig, extract_geometry, load_scene
        from planforge.ingestion import LidarCaptureLoader
        from planforge.measurements import measure_geometry
        from planforge.reconstruction import ReconstructionConfig, reconstruct
    except ImportError as error:
        parser.exit(1, f"missing dependency: {error}\n")
    if not (len(args.inputs) == len(args.calibrations) == len(args.raw_artifacts)):
        parser.exit(1, "inputs, calibrations and raw-artifacts must align one-to-one\n")
    try:
        config = ReconstructionConfig(
            frame_step=args.frame_step,
            pixel_stride=args.pixel_stride,
            voxel_size=args.voxel_size,
        )
        drift = DriftConfig()
        args.output.mkdir(parents=True, exist_ok=True)
        summary = []
        for input_path, calib_path, raw_dir in zip(args.inputs, args.calibrations, args.raw_artifacts):
            started = perf_counter()
            capture = LidarCaptureLoader().load(input_path)
            hypothesis = load_calibration(calib_path)
            rgb_size = rgb_metadata(capture.rgb_path)
            trajectory = np.array([f.position for f in capture.frames], dtype=float)
            analysis = analyze_trajectory(trajectory, drift)
            offsets, provenance = estimate_correction(trajectory, drift)
            cap_out = args.output / capture.path.name
            cap_out.mkdir(parents=True, exist_ok=True)
            record = {
                "capture_id": capture.path.name,
                "analysis": analysis,
                "max_offset_pose_units": provenance["max_offset_pose_units"],
                "method": provenance["method"],
            }
            if not analysis["loop_detected"]:
                record.update(status="identical_no_loop_detected",
                              corrected_recomputed=False,
                              closure_after_pose_units=analysis["closure_distance_pose_units"])
            else:
                corrected = replace(capture, frames=tuple(correct_frames(capture.frames, offsets)))
                scene = reconstruct(corrected, rgb_size, hypothesis,
                                    cap_out / "corrected", config, str(calib_path),
                                    lambda m: print(f"[{capture.path.name}] {m}", file=sys.stderr))
                corrected_traj = np.asarray(scene.trajectory)
                after = analyze_trajectory(corrected_traj, drift)
                raw_scene = load_scene(raw_dir)
                expected = json.loads((raw_dir / "spatial_scene.json").read_text())
                if expected["config"] != config.__dict__ or expected["hypothesis"] != hypothesis.to_dict():
                    raise ValueError(f"{capture.path.name}: existing raw artifacts do not match ablation config")
                raw_points = np.asarray(raw_scene.points, dtype=float)
                new_points = np.asarray(scene.points, dtype=float)
                record.update(
                    status="complete",
                    corrected_recomputed=True,
                    closure_after_pose_units=after["closure_distance_pose_units"],
                    raw_points=int(len(raw_points)),
                    corrected_points=int(len(new_points)),
                    cloud_distance_raw_vs_corrected=cloud_distance(raw_points, new_points),
                    overlap_residual_raw=overlap_residual(raw_points, np.asarray(raw_scene.frame_indices)),
                    overlap_residual_corrected=overlap_residual(new_points, np.asarray(scene.frame_indices)),
                )
                if not args.skip_geometry:
                    raw_geo = extract_geometry(raw_scene, GeometryConfig())
                    new_geo = extract_geometry(scene, GeometryConfig())
                    raw_model = measure_geometry(raw_geo.to_dict())
                    new_model = measure_geometry(new_geo.to_dict())
                    def areas(model):
                        return sorted(
                            m["value"] for m in model["measurements"]
                            if m["kind"] == "floor_area" and m["value"] is not None)
                    def residuals(geo):
                        by_role = {}
                        for surface in geo.to_dict()["surfaces"]:
                            by_role.setdefault(surface["role"], []).append(surface["residual_median"])
                        return {role: float(sorted(v)[len(v) // 2]) for role, v in by_role.items()}
                    record["footprint_area_pose2"] = {"raw": areas(raw_model), "corrected": areas(new_model)}
                    record["region_count"] = {"raw": len(raw_model["rooms"]), "corrected": len(new_model["rooms"])}
                    record["wall_count"] = {"raw": len(raw_model["walls"]), "corrected": len(new_model["walls"])}
                    record["orientation_status"] = {
                        "raw": raw_geo.to_dict()["orientation"]["status"],
                        "corrected": new_geo.to_dict()["orientation"]["status"]}
                    record["surface_residual_median"] = {
                        "raw": residuals(raw_geo), "corrected": residuals(new_geo)}
            record["compute_seconds"] = perf_counter() - started
            write_json(cap_out / "ablation.json", record)
            summary.append(record)
            print(f"{record['capture_id']}: {record['status']} "
                  f"(closure {analysis['closure_distance_pose_units']:.3f} -> "
                  f"{record.get('closure_after_pose_units', analysis['closure_distance_pose_units']):.3f})")
        write_json(args.output / "ablation_summary.json", {
            "status": "complete", "captures": summary,
            "scale_status": "unverified",
            "correction": "translation_only_linear_loop_distribution",
            "limitations": ["Rotation drift uncorrected", "Physical scale unverified",
                            "No measured ground truth; closure is self-consistency, not accuracy"],
        })
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Drift ablation failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
