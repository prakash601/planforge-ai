"""Loop-closure drift analysis with translation-only correction.

Observed failure mode: two sample captures return near their start
(closure/path below 1%) while a third ends meters away on a short path.
The correction distributes the window-averaged closure error linearly
across frames. Rotation drift is not estimated; quaternions pass through
unchanged. When no loop is detected the correction is exactly zero, so the
corrected run is bit-identical to the raw-pose baseline by construction.
"""

from dataclasses import dataclass, replace

import numpy as np
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class DriftConfig:
    loop_window: int = 5
    loop_ratio_threshold: float = 0.05
    min_path_length: float = 1.0
    max_sample_points: int = 20_000

    def __post_init__(self):
        if type(self.loop_window) is not int or self.loop_window < 1:
            raise ValueError("loop_window must be a positive integer")
        for name in ("loop_ratio_threshold", "min_path_length"):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not 0 < self.loop_ratio_threshold < 1:
            raise ValueError("loop_ratio_threshold must be between 0 and 1")
        if type(self.max_sample_points) is not int or self.max_sample_points < 100:
            raise ValueError("max_sample_points must be an integer >= 100")


def _checked_trajectory(trajectory):
    path = np.asarray(trajectory, dtype=float)
    if path.ndim != 2 or path.shape[1] != 3 or len(path) < 2:
        raise ValueError("trajectory must be an Nx3 array with at least 2 frames")
    if not np.isfinite(path).all():
        raise ValueError("trajectory must be finite")
    return path


def analyze_trajectory(trajectory, config=None):
    """Report path length, closure error and whether a loop is detected."""
    config = DriftConfig() if config is None else config
    path = _checked_trajectory(trajectory)
    window = min(config.loop_window, len(path))
    start = path[:window].mean(axis=0)
    end = path[-window:].mean(axis=0)
    segments = np.linalg.norm(np.diff(path, axis=0), axis=1)
    path_length = float(segments.sum())
    closure_vector = end - start
    closure_distance = float(np.linalg.norm(closure_vector))
    ratio = closure_distance / path_length if path_length > 0 else float("inf")
    loop_detected = bool(
        path_length >= config.min_path_length and ratio < config.loop_ratio_threshold
    )
    return {
        "frame_count": len(path),
        "path_length_pose_units": path_length,
        "closure_vector_pose_units": closure_vector.tolist(),
        "closure_distance_pose_units": closure_distance,
        "closure_ratio": float(ratio),
        "loop_detected": loop_detected,
        "correction_status": "loop_closure_candidate" if loop_detected else "open_trajectory_no_correction",
    }


def estimate_correction(trajectory, config=None):
    """Return per-frame (N,3) translation offsets and analysis provenance."""
    config = DriftConfig() if config is None else config
    path = _checked_trajectory(trajectory)
    analysis = analyze_trajectory(path, config)
    if not analysis["loop_detected"]:
        offsets = np.zeros_like(path)
    else:
        closure = np.asarray(analysis["closure_vector_pose_units"])
        ramp = np.linspace(0.0, 1.0, len(path))[:, None]
        offsets = -closure[None, :] * ramp
    return offsets, {
        **analysis,
        "method": "translation_only_linear_loop_distribution",
        "rotation_correction": "none_quaternions_unchanged",
        "max_offset_pose_units": float(np.linalg.norm(offsets, axis=1).max()),
    }


def correct_frames(frames, offsets):
    """Return frame copies with corrected positions; IDs and rotations preserved."""
    offsets = np.asarray(offsets, dtype=float)
    if offsets.ndim != 2 or offsets.shape[1] != 3 or len(offsets) != len(frames):
        raise ValueError("offsets must be an Nx3 array matching the frame count")
    if not np.isfinite(offsets).all():
        raise ValueError("offsets must be finite")
    corrected = []
    for frame, offset in zip(frames, offsets):
        position = np.asarray(frame.position, dtype=float) + offset
        if not np.isfinite(position).all():
            raise ValueError("corrected position must be finite")
        corrected.append(replace(frame, position=tuple(float(v) for v in position)))
    return corrected


def apply_correction(points, frame_indices, offsets, frame_step=1):
    """Shift fused points by the offset of their first supporting frame."""
    points = np.asarray(points, dtype=float)
    frame_indices = np.asarray(frame_indices)
    offsets = np.asarray(offsets, dtype=float)
    if len(points) != len(frame_indices):
        raise ValueError("points and frame indices must match")
    if offsets.ndim != 2 or offsets.shape[1] != 3:
        raise ValueError("offsets must be an Nx3 array")
    if any(int(i) * frame_step >= len(offsets) for i in np.unique(frame_indices)):
        raise ValueError("frame indices exceed the correction length")
    return points + np.array([offsets[int(i) * frame_step] for i in frame_indices])


def _sample(points, limit):
    if len(points) <= limit:
        return np.asarray(points, dtype=float)
    selection = np.linspace(0, len(points) - 1, limit, dtype=int)
    return np.asarray(points, dtype=float)[selection]


def cloud_distance(points_a, points_b, max_sample=20_000):
    """Symmetric median/p90 nearest-neighbor distance between two clouds."""
    a, b = _sample(points_a, max_sample), _sample(points_b, max_sample)
    if len(a) < 1 or len(b) < 1:
        raise ValueError("both clouds must be nonempty")
    nearest = []
    for source, target in ((a, b), (b, a)):
        distance, _ = cKDTree(target).query(source, k=1, workers=1)
        nearest.append(np.asarray(distance, dtype=float))
    both = np.concatenate(nearest)
    return {
        "median_pose_units": float(np.median(both)),
        "p90_pose_units": float(np.quantile(both, 0.9)),
        "mean_pose_units": float(both.mean()),
    }


def overlap_residual(points, frame_indices, max_sample=20_000):
    """Internal consistency: median NN distance between early and late halves."""
    points = np.asarray(points, dtype=float)
    frame_indices = np.asarray(frame_indices)
    if len(points) != len(frame_indices) or len(points) < 2:
        raise ValueError("points and frame indices must match with at least 2 points")
    split = (np.min(frame_indices) + np.max(frame_indices)) / 2
    early = points[frame_indices <= split]
    late = points[frame_indices > split]
    if len(early) < 1 or len(late) < 1:
        raise ValueError("both trajectory halves must contain points")
    early, late = _sample(early, max_sample), _sample(late, max_sample)
    late_to_early, _ = cKDTree(early).query(late, k=1, workers=1)
    early_to_late, _ = cKDTree(late).query(early, k=1, workers=1)
    both = np.concatenate([np.asarray(late_to_early), np.asarray(early_to_late)])
    return {
        "median_pose_units": float(np.median(both)),
        "p90_pose_units": float(np.quantile(both, 0.9)),
        "early_points": int(len(early)),
        "late_points": int(len(late)),
    }
