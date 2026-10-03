"""Plane evidence and conservative polygonization, without a rectangle prior."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import shapely
from scipy.spatial import ConvexHull, QhullError
from shapely import LineString, Point, contains_xy, get_parts, node, polygonize_full, union_all

from planforge.reconstruction import SpatialScene


@dataclass(frozen=True)
class GeometryConfig:
    plane_distance: float = 0.06
    sample_points: int = 40_000
    max_planes: int = 24
    ransac_iterations: int = 500
    min_plane_points: int = 120
    merge_angle_degrees: float = 5
    orientation_angle_degrees: float = 12
    min_horizontal_area: float = 1.5
    min_camera_clearance: float = 0.3
    min_wall_height: float = 1.2
    min_wall_length: float = 0.8
    floor_contact: float = 0.3
    support_gap: float = 0.3
    junction_tolerance: float = 0.2
    min_region_area: float = 1.0
    seed: int = 17

    def __post_init__(self):
        for name in ("sample_points", "max_planes", "ransac_iterations", "min_plane_points"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 3:
                raise ValueError(f"{name} must be an integer >= 3")
        if type(self.seed) is not int or not 0 <= self.seed < 2**31:
            raise ValueError("seed must be a nonnegative 32-bit integer")
        for name in ("plane_distance", "min_horizontal_area", "min_camera_clearance", "min_wall_height",
                     "min_wall_length", "floor_contact", "support_gap", "junction_tolerance", "min_region_area"):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("merge_angle_degrees", "orientation_angle_degrees"):
            if not np.isfinite(getattr(self, name)) or not 0 < getattr(self, name) < 45:
                raise ValueError(f"{name} must be between 0 and 45")
        if self.floor_contact >= self.min_wall_height:
            raise ValueError("floor_contact must be below min_wall_height")


@dataclass(frozen=True)
class RoomGeometry:
    capture_id: str
    orientation: dict
    surfaces: tuple
    walls: tuple
    regions: tuple
    flags: tuple
    diagnostics: dict
    provenance: dict

    def to_dict(self):
        return {"schema_version": 1, **asdict(self)}


def load_scene(directory):
    """Read the Task 3 contract, not the downsampled browser preview."""
    directory = Path(directory)
    metadata = json.loads((directory / "spatial_scene.json").read_text())
    if metadata.get("schema_version") != 1 or metadata.get("scale_status") != "unverified":
        raise ValueError("unsupported SpatialScene schema or scale status")
    capture_id = metadata.get("capture_id")
    if not isinstance(capture_id, str) or not capture_id or capture_id in (".", "..") or Path(capture_id).name != capture_id:
        raise ValueError("invalid scene capture_id")
    with np.load(directory / "cloud.npz", allow_pickle=False) as arrays:
        points = arrays["points"].copy()
        confidence = arrays["confidence"].copy()
        indices = arrays["frame_indices"].copy()
        counts = arrays["observation_counts"].copy()
    trajectory = np.asarray(metadata["trajectory"], dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all() or len(points) < 3:
        raise ValueError("scene must contain finite Nx3 points")
    if trajectory.ndim != 2 or trajectory.shape[1] != 3 or not len(trajectory) or not np.isfinite(trajectory).all():
        raise ValueError("scene must contain a finite trajectory")
    if any(array.shape != (len(points),) for array in (confidence, indices, counts)):
        raise ValueError("scene array lengths differ")
    if not np.issubdtype(indices.dtype, np.integer) or not np.issubdtype(counts.dtype, np.integer):
        raise ValueError("frame indices and observation counts must be integers")
    if not set(np.unique(confidence)) <= {0, 1, 2} or np.any(counts < 1):
        raise ValueError("invalid confidence or observation support")
    if len(metadata["frames"]) != len(trajectory) or np.any(indices < 0) or np.any(indices >= len(trajectory)):
        raise ValueError("invalid scene frame provenance")
    return SpatialScene(metadata["capture_id"], points, confidence, indices, counts, trajectory,
                        tuple(metadata["frames"]), metadata, metadata["diagnostics"])


def plane_basis(normal):
    axis = np.eye(3)[np.argmin(np.abs(normal))]
    x = axis - np.dot(axis, normal) * normal
    x /= np.linalg.norm(x)
    return np.array([x, normal, np.cross(x, normal)])


def fit_plane(points):
    center = points.mean(axis=0)
    _, _, vectors = np.linalg.svd(points - center, full_matrices=False)
    normal = vectors[-1]
    if normal[np.argmax(np.abs(normal))] < 0:
        normal = -normal
    return np.r_[normal, -np.dot(normal, center)]


def plane_patch(points, equation):
    basis = plane_basis(equation[:3])
    origin = -equation[3] * equation[:3]
    projected = (points - origin) @ basis[[0, 2]].T
    try:
        hull = ConvexHull(projected)
        polygon = projected[hull.vertices]
        world = origin + polygon @ basis[[0, 2]]
        return world.tolist(), float(hull.volume)
    except QhullError:
        return [], 0.0


def detect_planes(points, config):
    selected = np.linspace(0, len(points) - 1, min(config.sample_points, len(points)), dtype=int)
    sample = points[selected].astype(float)
    remaining = np.arange(len(sample))
    planes = []
    o3d.utility.random.seed(config.seed)
    normal_cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points.astype(float)))
    normal_cloud.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(knn=30))
    normals = np.asarray(normal_cloud.normals)[selected].copy()
    # Stratify by local normal so cross-sections through walls cannot dominate.
    directions = normals.copy()
    for index in range(len(directions)):
        if directions[index, np.argmax(np.abs(directions[index]))] < 0:
            directions[index] *= -1
    ungrouped = np.arange(len(sample))
    pools = []
    for _ in range(12):
        if len(ungrouped) < config.min_plane_points:
            break
        bins, labels, counts = np.unique(np.rint(directions[ungrouped] / 0.2).astype(int), axis=0, return_inverse=True, return_counts=True)
        winner = np.argmax(counts)
        axis = directions[ungrouped[labels == winner]].mean(axis=0)
        axis /= np.linalg.norm(axis)
        mask = np.abs(normals[ungrouped] @ axis) > np.cos(np.deg2rad(20))
        pools.append(ungrouped[mask])
        ungrouped = ungrouped[~mask]
    iterations = 0
    for _ in range(config.max_planes):
        iterations += 1
        if len(remaining) < config.min_plane_points:
            break
        candidates = []
        for pool in pools:
            available = np.intersect1d(remaining, pool, assume_unique=True)
            if len(available) < config.min_plane_points:
                continue
            cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(sample[available]))
            equation, inliers = cloud.segment_plane(config.plane_distance, 3, config.ransac_iterations, probability=0.999)
            indices = available[np.asarray(inliers)]
            supported = np.abs(normals[indices] @ np.asarray(equation[:3])) > np.cos(np.deg2rad(20))
            indices = indices[supported]
            if len(indices) >= config.min_plane_points:
                candidates.append(indices)
        if not candidates:
            break
        indices = max(candidates, key=len)
        equation = fit_plane(sample[indices])
        merged = False
        for plane in planes:
            other = plane["equation"]
            sign = 1 if np.dot(other[:3], equation[:3]) >= 0 else -1
            if abs(np.dot(other[:3], equation[:3])) >= np.cos(np.deg2rad(config.merge_angle_degrees)) and abs(other[3] - sign * equation[3]) <= config.plane_distance:
                plane["indices"] = np.union1d(plane["indices"], indices)
                plane["equation"] = fit_plane(sample[plane["indices"]])
                merged = True
                break
        if not merged:
            planes.append({"equation": equation, "indices": indices})
        remaining = np.setdiff1d(remaining, indices, assume_unique=True)
    for index, plane in enumerate(planes):
        plane["normal_support"] = len(plane.pop("indices"))
        equation = plane["equation"]
        plane["points"] = sample[np.abs(sample @ equation[:3] + equation[3]) <= config.plane_distance]
        plane["id"] = f"surface-{index:03}"
        plane["patch"], plane["area"] = plane_patch(plane["points"], plane["equation"])
    return planes, len(sample), len(remaining), iterations == config.max_planes


def infer_orientation(planes, points, trajectory, config, up_vector=None):
    if up_vector is not None:
        up = np.asarray(up_vector, dtype=float)
        if up.shape != (3,) or not np.isfinite(up).all() or np.linalg.norm(up) < 1e-8:
            raise ValueError("up_vector must be a finite nonzero 3-vector")
        return up / np.linalg.norm(up), {"status": "explicit_unverified", "method": "user supplied up vector", "candidates": [], "gravity_verified": False}
    candidates = []
    for plane in planes:
        n, d = plane["equation"][:3].copy(), plane["equation"][3]
        camera = trajectory @ n + d
        if np.median(camera) < 0:
            n, d, camera = -n, -d, -camera
        clearance = float(np.median(camera))
        above = float(np.mean(points @ n + d >= -config.plane_distance * 2))
        if plane["area"] < config.min_horizontal_area or clearance < config.min_camera_clearance or above < 0.85 or np.mean(camera > 0) < 0.95:
            continue
        score = float(np.std(camera) / clearance + 0.1 * (1 - above))
        candidates.append({"surface_id": plane["id"], "normal": n.tolist(), "score": score,
                           "camera_clearance": clearance, "cloud_above_fraction": above})
    candidates.sort(key=lambda row: row["score"])
    if not candidates or candidates[0]["score"] > 0.25:
        return None, {"status": "unresolved", "method": "surface/path evidence insufficient", "candidates": candidates}
    best = candidates[0]
    up = np.asarray(best["normal"])
    competing = [row for row in candidates[1:] if np.dot(up, row["normal"]) < 0.95]
    ambiguous = bool(competing and competing[0]["score"] - best["score"] < 0.05)
    return up, {"status": "ambiguous" if ambiguous else "provisional", "method": "broad one-sided plane with stable camera clearance; sign preference is not gravity validation",
                "candidates": candidates, "up_world": up.tolist(), "gravity_verified": False}


def wall_runs(plane, basis, origin, config):
    local = (plane["points"] - origin) @ basis.T
    normal = basis @ plane["equation"][:3]
    normal2 = normal[[0, 2]]
    normal2 /= np.linalg.norm(normal2)
    tangent = np.array([-normal2[1], normal2[0]])
    xy = local[:, [0, 2]]
    offset = float(np.median(xy @ normal2))
    positions = xy @ tangent
    # Floor/ceiling seams and door headers alone do not support a wall footprint.
    structural = np.flatnonzero((local[:, 1] >= config.floor_contact) & (local[:, 1] <= config.min_wall_height))
    order = structural[np.argsort(positions[structural])]
    groups = np.split(order, np.flatnonzero(np.diff(positions[order]) > config.support_gap) + 1)
    runs = []
    for group in groups:
        if not len(group):
            continue
        lo, hi = float(positions[group].min()), float(positions[group].max())
        group = np.flatnonzero((positions >= lo) & (positions <= hi))
        bottom, top = np.percentile(local[group, 1], [2, 98])
        if hi - lo < config.min_wall_length or top - bottom < config.min_wall_height or bottom > config.floor_contact:
            continue
        runs.append({"surface_id": plane["id"], "normal": normal2.tolist(), "offset": offset,
                     "tangent": tangent.tolist(), "interval": [lo, hi], "height_interval": [float(bottom), float(top)],
                     "endpoints": [(normal2 * offset + tangent * lo).tolist(), (normal2 * offset + tangent * hi).tolist()]})
    return runs


def build_regions(walls, floor_points, trajectory2, config):
    """Close only nearby observed line junctions; never bridge an absent wall."""
    junctions = [[] for _ in walls]
    for left in range(len(walls)):
        for right in range(left + 1, len(walls)):
            a, b = walls[left], walls[right]
            matrix = np.array([a["normal"], b["normal"]])
            if abs(np.linalg.det(matrix)) < 0.1:
                continue
            point = np.linalg.solve(matrix, [a["offset"], b["offset"]])
            supported = True
            for wall in (a, b):
                t = np.dot(point, wall["tangent"])
                lo, hi = wall["interval"]
                supported &= lo - config.junction_tolerance <= t <= hi + config.junction_tolerance
            if supported:
                junctions[left].append(point)
                junctions[right].append(point)
    lines = []
    for wall, intersections in zip(walls, junctions):
        endpoints = np.array(wall["endpoints"])
        tangent = np.asarray(wall["tangent"])
        if intersections:
            intersections = np.array(intersections)
            t = intersections @ tangent
            for end, value in enumerate(wall["interval"]):
                closest = np.argmin(np.abs(t - value))
                if abs(t[closest] - value) <= config.junction_tolerance:
                    endpoints[end] = intersections[closest]
        wall["junction_endpoints"] = np.round(endpoints, 6).tolist()
        lines.append(LineString(wall["junction_endpoints"]))
    polygons, cuts, dangles, invalid = polygonize_full(get_parts(node(union_all(lines)))) if lines else (None,) * 4
    regions, rejected = [], []
    for polygon in get_parts(polygons) if polygons is not None else []:
        support = int(contains_xy(polygon.buffer(config.plane_distance), floor_points[:, 0], floor_points[:, 1]).sum()) if len(floor_points) else 0
        visits = int(contains_xy(polygon, trajectory2[:, 0], trajectory2[:, 1]).sum())
        if not polygon.is_valid or polygon.area < config.min_region_area or support < 20 or visits < 1:
            rejected.append({"reason": "invalid/small region or insufficient floor/path support", "floor_samples": support, "camera_samples": visits})
            continue
        regions.append({"id": f"region-{len(regions):03}", "status": "candidate_closed_region",
                        "polygon": np.asarray(polygon.exterior.coords).tolist(),
                        "holes": [np.asarray(ring.coords).tolist() for ring in polygon.interiors],
                        "floor_samples": support, "camera_samples": visits})
        edges = np.asarray(polygon.exterior.coords)
        regions[-1]["edge_evidence"] = []
        for index, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
            middle = (a + b) / 2
            supporting = [wall.get("surface_id", f"wall-{wall_index}") for wall_index, wall in enumerate(walls)
                          if LineString(wall["junction_endpoints"]).distance(Point(middle)) < 1e-5]
            regions[-1]["edge_evidence"].append({"edge_index": index, "surface_ids": sorted(set(supporting))})
    topology = {"closed_regions": len(regions), "rejected_regions": rejected,
                "cut_edges": len(get_parts(cuts)) if cuts is not None else 0,
                "dangling_edges": len(get_parts(dangles)) if dangles is not None else 0,
                "invalid_rings": len(get_parts(invalid)) if invalid is not None else 0}
    return regions, topology


def extract_geometry(scene, config=GeometryConfig(), up_vector=None):
    points, trajectory = np.asarray(scene.points, dtype=float), np.asarray(scene.trajectory, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3 or not np.isfinite(points).all():
        raise ValueError("finite Nx3 scene points required")
    if trajectory.ndim != 2 or trajectory.shape[1] != 3 or not len(trajectory) or not np.isfinite(trajectory).all():
        raise ValueError("finite camera trajectory required")
    planes, sample_count, remaining, budget_reached = detect_planes(points, config)
    up, orientation = infer_orientation(planes, points, trajectory, config, up_vector)
    flags, surfaces, walls, regions = ["scale_unverified", "raw_pose_drift_uncorrected", "surface_roles_and_regions_are_candidates"], [], [], []
    basis, origin, floor_plane = None, None, None
    if up is not None and orientation["status"] != "ambiguous":
        basis = plane_basis(up)
        horizontal = [p for p in planes if abs(np.dot(p["equation"][:3], up)) >= np.cos(np.deg2rad(config.orientation_angle_degrees)) and p["area"] >= config.min_horizontal_area]
        below = [p for p in horizontal if np.mean(trajectory @ up > np.median(p["points"] @ up) + config.min_camera_clearance) >= 0.95
                 and np.mean(points @ up >= np.median(p["points"] @ up) - 2 * config.plane_distance) >= 0.85]
        if below:
            floor_plane = min(below, key=lambda p: np.median(p["points"] @ up))
            origin = up * np.median(floor_plane["points"] @ up)
            orientation.update(up_world=up.tolist(), basis_world_to_local=basis.tolist(), origin_world=origin.tolist())
    if up is None or orientation["status"] == "ambiguous":
        flags.append("orientation_unresolved" if up is None else "orientation_ambiguous")
    if floor_plane is None:
        flags.append("floor_role_unresolved" if orientation["status"] == "ambiguous" else "floor_unobserved")
    ceiling_ids = []
    for plane in planes:
        role = "unclassified"
        alignment = abs(np.dot(plane["equation"][:3], up)) if up is not None else None
        if floor_plane is not None:
            if plane is floor_plane:
                role = "floor_candidate"
            elif alignment >= np.cos(np.deg2rad(config.orientation_angle_degrees)):
                if plane["area"] >= config.min_horizontal_area and np.mean(trajectory @ up < np.median(plane["points"] @ up) - config.min_camera_clearance) >= 0.95:
                    role = "ceiling_candidate"
                    ceiling_ids.append(plane["id"])
                else:
                    role = "horizontal_other"
            elif alignment <= np.sin(np.deg2rad(config.orientation_angle_degrees)):
                runs = wall_runs(plane, basis, origin, config)
                role = "wall_candidate" if runs else "vertical_small_or_unsupported"
                walls.extend(runs)
            else:
                role = "sloped_other"
        surfaces.append({"id": plane["id"], "role": role, "equation_world": plane["equation"].tolist(),
                         "normal_consistent_fit_support": plane["normal_support"],
                         "sample_support": len(plane["points"]), "residual_median": float(np.median(np.abs(plane["points"] @ plane["equation"][:3] + plane["equation"][3]))),
                         "patch_world": plane["patch"], "patch_policy": "convex display envelope, not observed filled surface", "envelope_area_pose_units_squared": plane["area"]})
    if not ceiling_ids:
        flags.append("ceiling_role_unresolved" if orientation["status"] == "ambiguous" else "ceiling_unobserved")
    topology = {}
    if floor_plane is not None and orientation["status"] != "ambiguous":
        local_floor = (floor_plane["points"] - origin) @ basis.T
        local_path = (trajectory - origin) @ basis.T
        regions, topology = build_regions(walls, local_floor[:, [0, 2]], local_path[:, [0, 2]], config)
        for wall in walls:
            wall["support_endpoints_world"] = (origin + np.array(wall["endpoints"]) @ basis[[0, 2]]).tolist()
            wall["junction_endpoints_world"] = (origin + np.array(wall["junction_endpoints"]) @ basis[[0, 2]]).tolist()
        for region in regions:
            region["boundary_world"] = (origin + np.array(region["polygon"]) @ basis[[0, 2]]).tolist()
            region["holes_world"] = [(origin + np.array(hole) @ basis[[0, 2]]).tolist() for hole in region["holes"]]
    if not regions:
        flags.append("no_supported_closed_boundary")
    if topology.get("dangling_edges", 0) or topology.get("cut_edges", 0):
        flags.append("partial_wall_coverage")
    if len(regions) > 1:
        flags.append("multiple_closed_regions_not_verified_rooms")
    if budget_reached:
        flags.append("plane_search_budget_reached")
    diagnostics = {"sampled_points": sample_count, "unassigned_sample_points": remaining, "planes": len(surfaces),
                   "wall_runs": len(walls), "plane_search_budget_reached": budget_reached, "topology": topology, "room_count_status": "candidate_regions_only" if regions else "undetermined"}
    provenance = {"config": asdict(config), "coordinate_units": "hypothesized pose units, not certified meters",
                  "scale_status": "unverified", "source_depth_pose_sha256": scene.provenance.get("selected_depth_pose_sha256"),
                  "hypothesis": scene.provenance.get("hypothesis"), "gravity_source": "geometry/path heuristic; IMU coordinate semantics unknown",
                  "normal_policy": {"knn": 30, "normal_bin_width": 0.2, "max_direction_groups": 12, "alignment_angle_degrees": 20},
                  "libraries": {"open3d": o3d.__version__, "shapely": shapely.__version__}, "limitations": ["No ground-truth accuracy", "No drift correction",
                    "Tall furniture can resemble a wall", "Convex plane envelopes may span holes or disconnected patches",
                    "No room identity, adjacency or opening inference", "Floor/path support is evidence, not complete floor coverage"]}
    return RoomGeometry(scene.capture_id, orientation, tuple(surfaces), tuple(walls), tuple(regions), tuple(flags), diagnostics, provenance)
