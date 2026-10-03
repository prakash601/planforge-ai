"""Bounded occupancy gaps supported by through-plane representative sight lines."""

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np
from scipy.ndimage import find_objects, label


@dataclass(frozen=True)
class OpeningConfig:
    cell_size: float = 0.1
    plane_distance: float = 0.06
    min_width: float = 0.4
    max_width: float = 3.0
    min_height: float = 0.4
    min_door_height: float = 1.3
    floor_contact: float = 0.2
    border_support: float = 0.55
    min_rectangularity: float = 0.8
    ray_clearance: float = 0.15
    min_rays: int = 8
    min_frames: int = 2
    max_cells: int = 200_000

    def __post_init__(self):
        for name in (
            "cell_size",
            "plane_distance",
            "min_width",
            "max_width",
            "min_height",
            "min_door_height",
            "floor_contact",
            "ray_clearance",
        ):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.max_width < self.min_width or self.min_door_height < self.min_height:
            raise ValueError("inconsistent opening size thresholds")
        for name in ("border_support", "min_rectangularity"):
            if not np.isfinite(getattr(self, name)) or not 0 < getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        for name in ("min_rays", "min_frames", "max_cells"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


def detect_openings(scene, geometry, config=None):
    config = OpeningConfig() if config is None else config
    geometry = geometry.to_dict() if hasattr(geometry, "to_dict") else geometry
    if scene.capture_id != geometry["capture_id"]:
        raise ValueError("scene and geometry capture IDs differ")
    source_hash = geometry["provenance"].get("source_depth_pose_sha256")
    if source_hash != scene.provenance.get("selected_depth_pose_sha256"):
        raise ValueError("scene and geometry source hashes differ")
    result = {
        "schema_version": 1,
        "capture_id": scene.capture_id,
        "candidates": [],
        "unresolved_gaps": [],
        "diagnostics": {
            "surfaces_examined": 0,
            "skipped_surfaces": [],
            "status": "complete",
        },
        "provenance": {
            "config": asdict(config),
            "source_depth_pose_sha256": source_hash,
            "geometry_sha256": hashlib.sha256(
                json.dumps(
                    geometry, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest(),
            "units": "pose_unit",
            "rgb_evidence": "not_used_alignment_unverified",
            "ray_policy": "voxel centroid to first supporting frame camera; representative sight lines, not raw depth rays",
            "limitations": [
                "Unverified scale, orientation and supplied poses",
                "No semantic RGB verification",
                "Closed doors and opaque/invalid-depth windows can be missed",
                "Voxel centroids and pose drift can create false through-plane sight lines",
                "No physical opening accuracy or recall validation",
            ],
        },
    }
    orientation = geometry["orientation"]
    if (
        orientation["status"] not in ("provisional", "explicit_unverified")
        or "basis_world_to_local" not in orientation
    ):
        result["diagnostics"]["status"] = "orientation_unresolved"
        return result
    basis, origin = (
        np.asarray(orientation["basis_world_to_local"], float),
        np.asarray(orientation["origin_world"], float),
    )
    points, trajectory = (
        np.asarray(scene.points, float),
        np.asarray(scene.trajectory, float),
    )
    indices = np.asarray(scene.frame_indices)
    if (
        basis.shape != (3, 3)
        or origin.shape != (3,)
        or not np.isfinite(basis).all()
        or not np.isfinite(origin).all()
        or not np.allclose(basis @ basis.T, np.eye(3), atol=1e-5)
    ):
        raise ValueError("finite orthonormal geometry frame required")
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or not np.isfinite(points).all()
        or trajectory.ndim != 2
        or trajectory.shape[1] != 3
        or not np.isfinite(trajectory).all()
    ):
        raise ValueError("finite scene points and trajectory required")
    if (
        indices.shape != (len(points),)
        or not np.issubdtype(indices.dtype, np.integer)
        or np.any(indices < 0)
        or np.any(indices >= len(trajectory))
    ):
        raise ValueError("valid per-point frame provenance required")
    confidence = np.asarray(scene.confidence)
    if confidence.shape != (len(points),) or not set(np.unique(confidence)) <= {
        0,
        1,
        2,
    }:
        raise ValueError("valid confidence labels required")
    accepted = confidence >= 2
    points, indices = points[accepted], indices[accepted]
    cameras = trajectory[indices]
    local = (points - origin) @ basis.T
    for surface in sorted(geometry["surfaces"], key=lambda row: row["id"]):
        if surface["role"] != "wall_candidate":
            continue
        result["diagnostics"]["surfaces_examined"] += 1
        equation = np.asarray(surface["equation_world"], float)
        if (
            equation.shape != (4,)
            or not np.isfinite(equation).all()
            or not np.isclose(np.linalg.norm(equation[:3]), 1, atol=1e-5)
        ):
            raise ValueError("normalized wall plane required")
        normal = (basis @ equation[:3])[[0, 2]]
        normal /= np.linalg.norm(normal)
        tangent = np.array([-normal[1], normal[0]])
        t = local[:, [0, 2]] @ tangent
        distance = points @ equation[:3] + equation[3]
        wall_points = (np.abs(distance) <= config.plane_distance) & (local[:, 1] >= 0)
        if wall_points.sum() < 20:
            result["diagnostics"]["skipped_surfaces"].append(
                {"surface_id": surface["id"], "reason": "insufficient_points"}
            )
            continue
        lower = np.floor(t[wall_points].min() / config.cell_size) * config.cell_size
        nx = int(np.floor((t[wall_points].max() - lower) / config.cell_size)) + 1
        ny = int(np.floor(local[wall_points, 1].max() / config.cell_size)) + 1
        if nx * ny > config.max_cells or min(nx, ny) < 3:
            result["diagnostics"]["skipped_surfaces"].append(
                {"surface_id": surface["id"], "reason": "grid_budget_or_extent"}
            )
            continue
        occupancy = np.zeros((ny, nx), bool)
        x = np.floor((t[wall_points] - lower) / config.cell_size).astype(int)
        y = np.floor(local[wall_points, 1] / config.cell_size).astype(int)
        occupancy[y, x] = True
        components, _ = label(~occupancy)
        camera_distance = cameras @ equation[:3] + equation[3]
        through = (
            (camera_distance * distance < 0)
            & (np.abs(camera_distance) >= config.ray_clearance)
            & (np.abs(distance) >= config.ray_clearance)
        )
        crossing = (
            cameras[through]
            + (points[through] - cameras[through])
            * (
                camera_distance[through]
                / (camera_distance[through] - distance[through])
            )[:, None]
        )
        crossing_local = (crossing - origin) @ basis.T
        crossing_t = crossing_local[:, [0, 2]] @ tangent
        crossing_frames = indices[through]
        offset = float(np.median(local[wall_points][:, [0, 2]] @ normal))
        for component, bounds in enumerate(find_objects(components), 1):
            if bounds is None:
                continue
            y0, y1 = bounds[0].start, bounds[0].stop
            x0, x1 = bounds[1].start, bounds[1].stop
            width, height = (x1 - x0) * config.cell_size, (y1 - y0) * config.cell_size
            if (
                not config.min_width <= width <= config.max_width
                or height < config.min_height
                or x0 == 0
                or x1 == nx
                or y1 == ny
            ):
                continue
            bottom, top = y0 * config.cell_size, y1 * config.cell_size
            floor_connected = bottom <= config.floor_contact
            if floor_connected and height < config.min_door_height:
                continue
            rectangularity = float(np.mean(components[bounds] == component))
            borders = [
                occupancy[y0:y1, x0 - 1].mean(),
                occupancy[y0:y1, x1].mean(),
                occupancy[y1, x0:x1].mean(),
            ]
            if not floor_connected:
                borders.append(occupancy[y0 - 1, x0:x1].mean())
            if (
                rectangularity < config.min_rectangularity
                or min(borders) < config.border_support
            ):
                continue
            lo, hi = lower + x0 * config.cell_size, lower + x1 * config.cell_size
            inside = (
                (crossing_t >= lo)
                & (crossing_t < hi)
                & (crossing_local[:, 1] >= bottom)
                & (crossing_local[:, 1] < top)
            )
            frame_count = len(np.unique(crossing_frames[inside]))
            ray_count = int(inside.sum())
            candidate = {
                "surface_id": surface["id"],
                "kind": "door" if floor_connected else "window",
                "tangent_local": tangent.tolist(),
                "interval": [float(lo), float(hi)],
                "height_interval": [float(bottom), float(top)],
                "endpoints_local": [
                    (normal * offset + tangent * lo).tolist(),
                    (normal * offset + tangent * hi).tolist(),
                ],
                "width_pose_units": float(width),
                "surface_residual_median": surface["residual_median"],
                "evidence": {
                    "border_support": [float(value) for value in borders],
                    "rectangularity": float(rectangularity),
                    "representative_ray_count": ray_count,
                    "supporting_frames": frame_count,
                },
            }
            if ray_count < config.min_rays or frame_count < config.min_frames:
                candidate["reason"] = "insufficient_through_plane_sight_lines"
                result["unresolved_gaps"].append(candidate)
            else:
                result["candidates"].append(candidate)
    return result
