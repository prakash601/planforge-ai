"""Reproducible capture diagnostics; geometry and calibration remain separate."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .lidar import CaptureError, LidarCapture, LidarCaptureLoader


def time_stats(times: list[float]) -> dict:
    delta = np.diff(times)
    return {
        "count": len(times), "first": times[0], "last": times[-1],
        "duration_seconds": times[-1] - times[0],
        "median_interval_seconds": float(np.median(delta)) if delta.size else None,
        "median_rate_hz": float(1 / np.median(delta)) if delta.size else None,
        "min_interval_seconds": float(delta.min()) if delta.size else None,
        "max_interval_seconds": float(delta.max()) if delta.size else None,
    }


def inspect_images(capture: LidarCapture, sample_count: int) -> dict:
    headers = set()
    for frame in capture.frames:
        with Image.open(frame.depth_path) as depth, Image.open(frame.confidence_path) as confidence:
            if depth.format != "PNG" or confidence.format != "PNG":
                raise CaptureError(f"frame {frame.frame_id}: expected PNG images")
            if depth.size != confidence.size or depth.mode not in ("I;16", "I;16B", "I") or confidence.mode != "L":
                raise CaptureError(f"frame {frame.frame_id}: invalid depth/confidence layout")
            headers.add((depth.width, depth.height, depth.mode, confidence.mode))
    if len(headers) != 1:
        raise CaptureError("image layout changes within capture")
    width, height, depth_mode, confidence_mode = headers.pop()
    indices = np.linspace(0, len(capture.frames) - 1, min(sample_count, len(capture.frames)), dtype=int)
    samples = []
    for index in indices:
        frame = capture.frames[int(index)]
        depth = frame.read_depth()
        confidence = frame.read_confidence()
        labels, counts = np.unique(confidence, return_counts=True)
        if not set(labels.tolist()) <= {0, 1, 2}:
            raise CaptureError(f"frame {frame.frame_id}: unexpected confidence labels {labels.tolist()}")
        valid = depth[depth > 0]
        samples.append({
            "frame_id": frame.frame_id, "depth_min_raw": int(depth.min()), "depth_max_raw": int(depth.max()),
            "nonzero_depth_percentiles_raw": dict(zip(("p05", "p50", "p95"), np.percentile(valid, [5, 50, 95]).tolist())) if valid.size else None,
            "zero_depth_fraction": float(np.mean(depth == 0)),
            "confidence_counts": {str(int(label)): int(count) for label, count in zip(labels, counts)},
        })
    return {"width": width, "height": height, "depth_mode": depth_mode, "confidence_mode": confidence_mode,
            "headers_checked": len(capture.frames), "pixels_sampled_frames": len(samples), "samples": samples}


def inspect_rgb(path: Path) -> dict:
    video = cv2.VideoCapture(str(path))
    try:
        if not video.isOpened():
            raise CaptureError("RGB video could not be opened")
        width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(video.get(cv2.CAP_PROP_FPS))
        if width <= 0 or height <= 0 or count <= 0 or not np.isfinite(fps) or fps <= 0:
            raise CaptureError("invalid RGB video metadata")
        decoded = []
        actual_count = 0
        targets = {0, count // 2, count - 1}
        # Sequential decoding avoids inaccurate seeking in variable-rate MP4s.
        while video.grab():
            if actual_count in targets:
                ok, frame = video.retrieve()
                if not ok or frame.shape[:2] != (height, width):
                    raise CaptureError(f"RGB video frame {actual_count} could not be decoded")
                decoded.append(actual_count)
            actual_count += 1
        if actual_count == 0:
            raise CaptureError("RGB video has no decodable frames")
        return {"width": width, "height": height, "frame_count_reported": count,
                "frame_count_sequential": actual_count,
                "fps_reported": fps, "duration_seconds_estimated": count / fps,
                "decoded_sample_indices": decoded, "backend": video.getBackendName(),
                "timestamp_alignment": "unknown; matching counts do not establish synchronization"}
    finally:
        video.release()


def inspect_capture(path: str | Path, sample_count: int = 8) -> dict:
    if sample_count < 1:
        raise CaptureError("sample_count must be positive")
    capture = LidarCaptureLoader().load(path)
    images = inspect_images(capture, sample_count)
    rgb = inspect_rgb(capture.rgb_path)
    positions = np.asarray([frame.position for frame in capture.frames])
    quaternions = np.asarray([frame.quaternion_xyzw for frame in capture.frames])
    intrinsics = np.asarray([frame.intrinsics_fx_fy_cx_cy for frame in capture.frames])
    ids = [int(frame.frame_id) for frame in capture.frames]
    warnings = [
        "Depth scale, pose direction/axes/units and IMU units are not recorded in the supplied files.",
        "Confidence labels 0/1/2 are observed; their meaning requires exporter documentation.",
        "Video synchronization is unverified; no explicit RGB timestamps were supplied.",
    ]
    if np.any(intrinsics[:, 2] >= images["width"]) or np.any(intrinsics[:, 3] >= images["height"]):
        warnings.append("Odometry principal points exceed depth dimensions; intrinsics cannot be used directly on depth pixels.")
    if rgb["frame_count_reported"] != len(capture.frames):
        warnings.append("RGB frame count differs from odometry/depth count.")
    if rgb["frame_count_sequential"] != rgb["frame_count_reported"]:
        warnings.append("Sequential RGB count differs from container metadata; investigate truncation or decoder behavior.")
    if any(right != left + 1 for left, right in zip(ids, ids[1:])):
        warnings.append("Frame IDs have gaps or are not in ascending consecutive order.")
    files = [p for p in capture.path.rglob("*") if p.is_file() and p.name != ".DS_Store"]
    return {
        "capture_id": capture.path.name, "status": "metadata_and_samples_validated",
        "file_count_excluding_ds_store": len(files), "bytes_excluding_ds_store": sum(p.stat().st_size for p in files),
        "odometry": time_stats([frame.timestamp for frame in capture.frames]),
        "imu": time_stats([float(row["timestamp"]) for row in capture.imu_rows]),
        "frame_ids": {"first": capture.frames[0].frame_id, "last": capture.frames[-1].frame_id,
                      "consecutive": all(b == a + 1 for a, b in zip(ids, ids[1:]))},
        "position_bounds_raw": {"min_xyz": positions.min(axis=0).tolist(), "max_xyz": positions.max(axis=0).tolist()},
        "quaternion_norm_range": [float(value) for value in (np.linalg.norm(quaternions, axis=1).min(), np.linalg.norm(quaternions, axis=1).max())],
        "odometry_intrinsics_raw": {"fields": ["fx", "fy", "cx", "cy"], "min": intrinsics.min(axis=0).tolist(), "max": intrinsics.max(axis=0).tolist()},
        "camera_matrix_raw": capture.camera_matrix, "images": images, "rgb": rgb,
        "mesh_files": [str(p.relative_to(capture.path)) for p in files if p.suffix.lower() in {".ply", ".obj", ".glb", ".stl"}],
        "warnings": warnings,
        "validation_scope": "All CSV records, PNG IDs and image headers; evenly spaced depth/confidence pixel samples; sequential RGB grab/decode count with retrieval at first/middle/last reported frames. Other PNG pixels are not decoded.",
    }
