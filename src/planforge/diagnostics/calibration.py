"""Compare explicit calibration hypotheses without changing supplied poses."""

from dataclasses import asdict, dataclass
from itertools import product

import numpy as np
from scipy.spatial.transform import Rotation

from planforge.ingestion import FrameRecord, LidarCapture


@dataclass(frozen=True)
class Hypothesis:
    depth_scale: float = 0.001
    intrinsics: str = "rgb_scaled"
    camera_axes: str = "opengl"
    pose_direction: str = "camera_to_world"

    def __post_init__(self):
        if not np.isfinite(self.depth_scale) or self.depth_scale <= 0:
            raise ValueError("depth_scale must be finite and positive")
        if self.intrinsics not in ("rgb_scaled", "as_recorded"):
            raise ValueError("unsupported intrinsics hypothesis")
        if self.camera_axes not in ("opencv", "opengl"):
            raise ValueError("unsupported camera axes")
        if self.pose_direction not in ("camera_to_world", "world_to_camera"):
            raise ValueError("unsupported pose direction")

    @property
    def key(self):
        return f"{self.depth_scale:g}/{self.intrinsics}/{self.camera_axes}/{self.pose_direction}"

    def to_dict(self):
        return {"key": self.key, **asdict(self)}


def candidate_hypotheses(scales=(0.0005, 0.001, 0.002, 0.01, 1.0)):
    return [Hypothesis(*values) for values in product(scales, ("rgb_scaled", "as_recorded"),
            ("opencv", "opengl"), ("camera_to_world", "world_to_camera"))]


def depth_intrinsics(frame: FrameRecord, shape, rgb_size, hypothesis: Hypothesis):
    fx, fy, cx, cy = frame.intrinsics_fx_fy_cx_cy
    if hypothesis.intrinsics == "rgb_scaled":
        height, width = shape
        rgb_width, rgb_height = rgb_size
        if min(rgb_width, rgb_height) <= 0:
            raise ValueError("RGB resolution must be positive")
        fx, cx = fx * width / rgb_width, cx * width / rgb_width
        fy, cy = fy * height / rgb_height, cy * height / rgb_height
    return np.array([fx, fy, cx, cy])


def backproject(depth, intrinsics, scale):
    fx, fy, cx, cy = intrinsics
    v, u = np.indices(depth.shape)
    z = depth.astype(np.float64) * scale
    return np.stack(((u - cx) * z / fx, (v - cy) * z / fy, z), axis=-1)


def camera_transform(frame: FrameRecord, hypothesis: Hypothesis):
    """Return optical (x right/y down/z forward) to hypothesized world transform."""
    rotation = Rotation.from_quat(frame.quaternion_xyzw).as_matrix()
    translation = np.array(frame.position)
    if hypothesis.pose_direction == "world_to_camera":
        rotation, translation = rotation.T, -rotation.T @ translation
    axes = np.diag([1, -1, -1]) if hypothesis.camera_axes == "opengl" else np.eye(3)
    return rotation @ axes, translation


def transform_points(points, frame, hypothesis):
    rotation, translation = camera_transform(frame, hypothesis)
    return points @ rotation.T + translation


def compare_pair(source, target, rgb_size, hypothesis, pixel_stride=4, min_confidence=2):
    """Project source into target; penalize missing overlap and relative residuals."""
    source_frame, source_depth, source_confidence = source
    target_frame, target_depth, target_confidence = target
    source_k = depth_intrinsics(source_frame, source_depth.shape, rgb_size, hypothesis)
    target_k = depth_intrinsics(target_frame, target_depth.shape, rgb_size, hypothesis)
    source_points = backproject(source_depth, source_k, hypothesis.depth_scale)
    target_points = backproject(target_depth, target_k, hypothesis.depth_scale)
    source_valid = (source_depth > 0) & (source_confidence >= min_confidence)
    points = source_points[::pixel_stride, ::pixel_stride][source_valid[::pixel_stride, ::pixel_stride]]
    if len(points) < 20:
        return {"valid": False, "reason": "insufficient source depth support"}
    world = transform_points(points, source_frame, hypothesis)
    rotation, translation = camera_transform(target_frame, hypothesis)
    projected = (world - translation) @ rotation
    z = projected[:, 2]
    safe_z = np.where(z > 0, z, 1)
    fx, fy, cx, cy = target_k
    u = np.rint(projected[:, 0] * fx / safe_z + cx).astype(int)
    v = np.rint(projected[:, 1] * fy / safe_z + cy).astype(int)
    height, width = target_depth.shape
    inside = (z > 0) & (u >= 1) & (u < width - 1) & (v >= 1) & (v < height - 1)
    indices = np.flatnonzero(inside)
    u, v = u[inside], v[inside]
    # Reject invalid neighbors and depth discontinuities before estimating normals.
    neighbors = np.stack([target_depth[v, u], target_depth[v, u-1], target_depth[v, u+1],
                          target_depth[v-1, u], target_depth[v+1, u]])
    normal = np.cross(target_points[v, u+1] - target_points[v, u-1], target_points[v+1, u] - target_points[v-1, u])
    norm = np.linalg.norm(normal, axis=1)
    supported = (target_confidence[v, u] >= min_confidence) & (neighbors.min(axis=0) > 0)
    supported &= ((neighbors.max(axis=0) - neighbors.min(axis=0)) < 0.05 * neighbors[0]) & (norm > 1e-12)
    indices, u, v, normal, norm = indices[supported], u[supported], v[supported], normal[supported], norm[supported]
    overlap = len(indices) / len(points)
    if len(indices) < 20:
        return {"valid": True, "score": 1.0, "overlap_fraction": overlap, "inlier_fraction": 0.0,
                "relative_depth_median": None, "relative_plane_median": None, "plane_median_pose_units": None}
    observed = target_points[v, u]
    relative_depth = np.abs(projected[indices, 2] - observed[:, 2]) / observed[:, 2]
    plane = np.abs(np.sum((projected[indices] - observed) * normal / norm[:, None], axis=1))
    relative_plane = plane / observed[:, 2]
    # A relative error avoids making a collapsed, tiny-scale cloud look accurate.
    quality = (np.clip(relative_depth / 0.05, 0, 1) + np.clip(relative_plane / 0.03, 0, 1)) / 2
    score = (1 - overlap) + overlap * float(quality.mean())
    return {"valid": True, "score": score, "overlap_fraction": overlap,
            "inlier_fraction": float(np.mean((relative_depth < 0.03) & (relative_plane < 0.02))),
            "relative_depth_median": float(np.median(relative_depth)),
            "relative_plane_median": float(np.median(relative_plane)), "plane_median_pose_units": float(np.median(plane))}


def sample_pairs(capture: LidarCapture):
    """Sample five time windows and two separations, not just adjacent frames."""
    count = len(capture.frames)
    pairs = []
    for start in np.linspace(0, max(0, count - 121), 5, dtype=int):
        for lag in (30, 90):
            end = min(int(start) + lag, count - 1)
            if end > start and (int(start), end) not in pairs:
                pairs.append((int(start), end))
    return pairs


def rank_hypotheses(captures, rgb_sizes, hypotheses):
    cache = {}
    pairs_by_capture = []
    for capture in captures:
        pairs = sample_pairs(capture)
        pairs_by_capture.append(pairs)
        for index in {index for pair in pairs for index in pair}:
            frame = capture.frames[index]
            cache[capture.path.name, index] = (frame, frame.read_depth(), frame.read_confidence())
    rankings = []
    for hypothesis in hypotheses:
        results = []
        for capture, rgb_size, pairs in zip(captures, rgb_sizes, pairs_by_capture):
            diagnostics = []
            for left, right in pairs:
                # Symmetric evaluation reduces bias from occlusion in one direction.
                for a, b in ((left, right), (right, left)):
                    result = compare_pair(cache[capture.path.name, a], cache[capture.path.name, b], rgb_size, hypothesis)
                    result.update(source_frame=capture.frames[a].frame_id, target_frame=capture.frames[b].frame_id)
                    diagnostics.append(result)
            valid = [row for row in diagnostics if row["valid"]]
            score = float(np.mean([row["score"] for row in valid])) if valid else 1.0
            results.append({"capture_id": capture.path.name, "score": score, "pairs": diagnostics})
        rankings.append({"hypothesis": hypothesis.to_dict(), "score": float(np.mean([row["score"] for row in results])), "captures": results})
    return sorted(rankings, key=lambda result: result["score"])
