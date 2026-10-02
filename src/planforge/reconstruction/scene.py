"""Streaming raw export and capped voxel fusion in hypothesized pose units."""

from dataclasses import asdict, dataclass
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from planforge.diagnostics.artifacts import write_json
from planforge.diagnostics.calibration import backproject, camera_transform, depth_intrinsics, transform_points


@dataclass(frozen=True)
class ReconstructionConfig:
    frame_step: int = 1
    pixel_stride: int = 4
    voxel_size: float = 0.05
    min_confidence: int = 2
    max_voxels: int = 500_000
    outlier_neighbors: int = 8
    outlier_std_ratio: float = 2.0
    preview_points: int = 150_000

    def __post_init__(self):
        for name in ("frame_step", "pixel_stride", "max_voxels", "outlier_neighbors", "preview_points"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.min_confidence) is not int or self.min_confidence not in (0, 1, 2):
            raise ValueError("min_confidence must be label 0, 1 or 2")
        for name in ("voxel_size", "outlier_std_ratio"):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class SpatialScene:
    capture_id: str
    points: np.ndarray
    confidence: np.ndarray
    frame_indices: np.ndarray
    observation_counts: np.ndarray
    trajectory: np.ndarray
    frames: tuple
    provenance: dict
    diagnostics: dict


PLY_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                      ("confidence", "u1"), ("frame_index", "<i4")])


class PlyWriter:
    """Keep only a frame-sized buffer; finalize vertex count without rereading."""

    def __init__(self, path):
        self.file = Path(path).open("wb")
        prefix = b"ply\nformat binary_little_endian 1.0\ncomment scale unverified\nelement vertex "
        self.file.write(prefix)
        self.offset = len(prefix)
        self.file.write(b"00000000000000000000\nproperty float x\nproperty float y\nproperty float z\nproperty uchar confidence\nproperty int frame_index\nend_header\n")
        self.count = 0

    def append(self, points, confidence, indices):
        records = np.empty(len(points), dtype=PLY_DTYPE)
        for axis, name in enumerate(("x", "y", "z")):
            records[name] = points[:, axis]
        records["confidence"], records["frame_index"] = confidence, indices
        self.file.write(records.tobytes())
        self.count += len(points)

    def close(self):
        self.file.seek(self.offset)
        self.file.write(f"{self.count:020d}".encode("ascii"))
        self.file.close()


def statistical_inliers(points, neighbors, std_ratio):
    if len(points) < 3:
        return np.ones(len(points), dtype=bool), None
    tree = cKDTree(points)
    k = min(neighbors + 1, len(points))
    distances = np.empty(len(points))
    chunk = max(1, min(8192, 131_072 // k))
    for start in range(0, len(points), chunk):
        distance, _ = tree.query(points[start:start + chunk], k=k, workers=1)
        distances[start:start + len(distance)] = distance[:, 1:].mean(axis=1)
    threshold = float(distances.mean() + std_ratio * distances.std())
    return distances <= threshold, threshold


def reconstruct(capture, rgb_size, hypothesis, output, config=ReconstructionConfig(), calibration_source=None, progress=None):
    """Publish completed artifacts only; failed runs preserve previous results."""
    output = Path(output)
    if output.resolve().is_relative_to(capture.path.resolve()):
        raise ValueError("output must be outside the raw capture directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reconstruction-", dir=output.parent) as temporary:
        scene = _reconstruct(capture, rgb_size, hypothesis, Path(temporary), config, calibration_source, progress)
        output.mkdir(parents=True, exist_ok=True)
        paths = sorted(Path(temporary).iterdir(), key=lambda path: path.name == "spatial_scene.json")
        for path in paths:
            shutil.move(str(path), output / path.name)
    return scene


def _reconstruct(capture, rgb_size, hypothesis, output, config, calibration_source, progress):
    output = Path(output)
    if output.resolve().is_relative_to(capture.path.resolve()):
        raise ValueError("output must be outside the raw capture directory")
    output.mkdir(parents=True, exist_ok=True)
    # Partial files are never advertised as a completed scene.
    raw_path = output / "raw.partial.ply"
    writer = PlyWriter(raw_path)
    voxels, labels, trajectory = {}, [], []
    preview_xyz, preview_confidence, preview_frames = [], [], []
    selected_count = len(range(0, len(capture.frames), config.frame_step))
    preview_per_frame = config.preview_points // selected_count
    source_digest = hashlib.sha256()
    counts = {"sampled_pixels": 0, "invalid_depth": 0, "confidence_rejected": 0, "raw_points": 0, "accepted_observations": 0}
    try:
        for local_index, index in enumerate(range(0, len(capture.frames), config.frame_step)):
            frame = capture.frames[index]
            depth, mask = frame.read_depth(), frame.read_confidence()
            source_digest.update(json.dumps([frame.frame_id, frame.timestamp, frame.position,
                                 frame.quaternion_xyzw, frame.intrinsics_fx_fy_cx_cy]).encode())
            source_digest.update(str((depth.shape, depth.dtype.str, mask.dtype.str)).encode())
            source_digest.update(depth.tobytes())
            source_digest.update(mask.tobytes())
            if depth.ndim != 2 or depth.shape != mask.shape or not set(np.unique(mask)) <= {0, 1, 2}:
                raise ValueError(f"{frame.frame_id}: invalid depth/confidence layout")
            k = depth_intrinsics(frame, depth.shape, rgb_size, hypothesis)
            local = backproject(depth, k, hypothesis.depth_scale)[::config.pixel_stride, ::config.pixel_stride]
            sampled = depth[::config.pixel_stride, ::config.pixel_stride]
            confidence = mask[::config.pixel_stride, ::config.pixel_stride]
            valid = (sampled > 0) & np.isfinite(local).all(axis=2)
            world = transform_points(local[valid], frame, hypothesis)
            if not np.isfinite(world).all():
                raise ValueError("nonfinite transformed coordinates")
            confidence = confidence[valid]
            writer.append(world, confidence, np.full(len(world), local_index))
            quota = preview_per_frame + (local_index < config.preview_points % selected_count)
            selection = np.linspace(0, len(world) - 1, min(quota, len(world)), dtype=int)
            preview_xyz.extend(world[selection].tolist())
            preview_confidence.extend(confidence[selection].tolist())
            preview_frames.extend([local_index] * len(selection))
            counts["sampled_pixels"] += sampled.size
            counts["invalid_depth"] += int(sampled.size - valid.sum())
            counts["raw_points"] += len(world)
            accepted = confidence >= config.min_confidence
            counts["confidence_rejected"] += int((~accepted).sum())
            world, confidence = world[accepted], confidence[accepted]
            counts["accepted_observations"] += len(world)
            keys_float = np.floor(world / config.voxel_size)
            if np.any(np.abs(keys_float) >= 2**62):
                raise ValueError("voxel coordinates exceed supported range")
            keys, inverse, support = np.unique(keys_float.astype(np.int64), axis=0, return_inverse=True, return_counts=True)
            sums = np.zeros((len(keys), 3))
            np.add.at(sums, inverse, world)
            levels = np.zeros(len(keys), dtype=np.uint8)
            np.maximum.at(levels, inverse, confidence)
            for key, total, n, level in zip(keys, sums, support, levels):
                key = tuple(key)
                if key in voxels:
                    value = voxels[key]
                    value[0] += total
                    value[1] += int(n)
                    value[2] = max(value[2], int(level))
                else:
                    if len(voxels) >= config.max_voxels:
                        raise ValueError("max_voxels exceeded; increase voxel_size or explicitly raise the memory limit")
                    voxels[key] = [total.copy(), int(n), int(level), local_index]
            _, center = camera_transform(frame, hypothesis)
            trajectory.append(center)
            labels.append({"id": frame.frame_id, "timestamp": frame.timestamp, "source_index": index})
            if progress and local_index % 250 == 0:
                progress(f"{capture.path.name}: frame {index + 1}/{len(capture.frames)}, {len(voxels)} voxels")
    except BaseException:
        writer.close()
        raw_path.unlink(missing_ok=True)
        raise
    writer.close()
    if not voxels:
        raw_path.unlink(missing_ok=True)
        raise ValueError("no supported depth observations")
    values = [voxels[key] for key in sorted(voxels)]
    points = np.array([value[0] / value[1] for value in values])
    levels = np.array([value[2] for value in values], dtype=np.uint8)
    indices = np.array([value[3] for value in values], dtype=np.int32)
    support = np.array([value[1] for value in values], dtype=np.int64)
    del voxels, values
    keep, threshold = statistical_inliers(points, config.outlier_neighbors, config.outlier_std_ratio)
    counts.update(voxels_before_outlier=len(points), outliers_removed=int((~keep).sum()), filtered_points=int(keep.sum()),
                  selected_frames=len(labels), total_frames=len(capture.frames), outlier_threshold_pose_units=threshold)
    provenance = {"schema_version": 1, "input_tier": "lidar", "hypothesis": hypothesis.to_dict(),
                  "calibration_source": calibration_source, "scale_status": "unverified",
                  "selected_depth_pose_sha256": source_digest.hexdigest(),
                  "fingerprint_scope": "decoded full depth/confidence images and pose/intrinsics metadata for selected frames; RGB pixels and IMU unused",
                  "coordinate_units": "hypothesized pose units, not certified meters",
                  "world_frame": "supplied pose frame; gravity and handedness not independently verified",
                  "optical_frame": "x right, y down, z forward", "pose_correction": "none; raw-pose baseline",
                  "rgb_resolution": list(rgb_size), "config": asdict(config),
                  "confidence_policy": "ordinal label threshold; exporter meanings unknown; voxel stores maximum accepted label",
                  "voxel_policy": "mean of accepted observations; observation_count counts pixels, not independent frames; frame_index is first supporting selected frame",
                  "outlier_policy": "global mean k-neighbor distance above mean + std_ratio * standard deviation",
                  "limitations": ["Physical scale unverified", "No RGB synchronization or coloring", "No drift correction", "Sparse legitimate surfaces may be removed by outlier filtering"]}
    scene = SpatialScene(capture.path.name, points[keep].astype(np.float32), levels[keep], indices[keep], support[keep],
                         np.array(trajectory), tuple(labels), provenance, counts)
    raw_path.replace(output / "raw.ply")
    filtered = PlyWriter(output / "cloud.ply")
    filtered.append(scene.points, scene.confidence, scene.frame_indices)
    filtered.close()
    np.savez_compressed(output / "cloud.npz", points=scene.points, confidence=scene.confidence,
                        frame_indices=scene.frame_indices, observation_counts=scene.observation_counts)
    write_json(output / "spatial_scene.json", {**provenance, "capture_id": scene.capture_id, "frames": labels,
               "trajectory": scene.trajectory.tolist(), "diagnostics": counts,
               "artifacts": {"raw": "raw.ply", "filtered": "cloud.ply", "arrays": "cloud.npz", "preview": "scene.json"}})
    selection = np.linspace(0, len(scene.points) - 1, min(config.preview_points, len(scene.points)), dtype=int)
    write_json(output / "scene.json", {**provenance, "capture_id": scene.capture_id, "frames": labels,
               "trajectory": scene.trajectory.tolist(), "points": scene.points[selection].ravel().tolist(),
               "confidence": scene.confidence[selection].tolist(), "frame_indices": scene.frame_indices[selection].tolist(),
               "point_count": len(selection), "full_point_count": len(scene.points), "diagnostics": counts})
    write_json(output / "raw_scene.json", {**provenance, "capture_id": scene.capture_id, "frames": labels,
               "trajectory": scene.trajectory.tolist(), "points": np.asarray(preview_xyz).ravel().tolist(),
               "confidence": preview_confidence, "frame_indices": preview_frames,
               "point_count": len(preview_frames), "full_point_count": counts["raw_points"], "diagnostics": counts,
               "preview_policy": "evenly spaced pixels per selected frame; bounded preview, not full raw cloud"})
    return scene
