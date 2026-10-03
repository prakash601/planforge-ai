"""Measure the Task 4 contract without asserting physical scale or room identity."""

import hashlib
import json
from importlib.resources import files
from itertools import pairwise

import numpy as np
from jsonschema import Draft202012Validator
from shapely import LineString, Polygon


def stable_id(kind, capture, identity):
    """IDs survive array reordering, not changes to the underlying geometry."""
    payload = json.dumps(
        [capture, identity], sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return f"{kind}-{hashlib.sha256(payload.encode()).hexdigest()[:20]}"


def canonical_ring(ring):
    points = np.asarray(ring, dtype=float)
    if (
        points.ndim != 2
        or points.shape[1] != 2
        or len(points) < 4
        or not np.isfinite(points).all()
    ):
        raise ValueError("finite closed polygon ring required")
    if not np.array_equal(points[0], points[-1]):
        raise ValueError("polygon ring must be closed")
    coordinates = [tuple(row) for row in np.round(points[:-1], 6).tolist()]
    variants = []
    for sequence in (coordinates, list(reversed(coordinates))):
        start = min(
            range(len(sequence)), key=lambda index: sequence[index:] + sequence[:index]
        )
        variants.append(sequence[start:] + sequence[:start])
    result = min(variants)
    return [list(row) for row in (*result, result[0])]


def validate_model(model):
    schema_file = {"1.0.0": "schema-v1.json", "1.1.0": "schema-v1.1.json"}.get(
        model.get("schema_version")
    )
    if schema_file is None:
        raise ValueError("unsupported measurement schema version")
    schema = json.loads(
        files("planforge.measurements").joinpath(schema_file).read_text()
    )
    Draft202012Validator(schema).validate(model)
    # JSON Schema cannot express foreign keys, numeric ordering or finiteness.
    json.dumps(model, allow_nan=False)
    entities = (
        model["rooms"] + model["walls"] + model["openings"] + model["measurements"]
    )
    ids = [entity["id"] for entity in entities]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate model IDs")
    measurements = {item["id"]: item for item in model["measurements"]}
    owners = {
        item["id"] for item in model["rooms"] + model["walls"] + model["openings"]
    }
    walls = {item["id"] for item in model["walls"]}
    rooms = {item["id"]: item for item in model["rooms"]}
    for kind, collection in (
        ("room", model["rooms"]),
        ("wall", model["walls"]),
        ("opening", model["openings"]),
        ("measurement", model["measurements"]),
    ):
        if any(not entity["id"].startswith(kind + "-") for entity in collection):
            raise ValueError("wrong entity ID prefix")
    for wall in model["walls"]:
        if wall["kind"] == "observed_run" and wall["room_id"] is not None:
            raise ValueError("observed runs cannot assert room identity")
        if wall["kind"] == "region_boundary" and (
            wall["room_id"] not in rooms
            or wall["id"] not in rooms[wall["room_id"]]["wall_ids"]
        ):
            raise ValueError("invalid boundary wall room reference")
    for room in model["rooms"]:
        if not set(room["wall_ids"]) <= walls:
            raise ValueError("unknown room wall reference")
        polygon = Polygon(
            canonical_ring(room["polygon_local"]),
            [canonical_ring(ring) for ring in room["holes_local"]],
        )
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError("invalid model room polygon")
    for opening in model["openings"]:
        if opening["wall_id"] not in walls:
            raise ValueError("unknown opening wall reference")
        if "support_wall_ids" in opening:
            if (
                not set(opening["support_wall_ids"]) <= walls
                or opening["wall_id"] not in opening["support_wall_ids"]
            ):
                raise ValueError("invalid opening support wall references")
            by_id = {wall["id"]: wall for wall in model["walls"]}
            if any(
                opening["source_surface_id"] not in by_id[wall_id]["source_surface_ids"]
                for wall_id in opening["support_wall_ids"]
            ):
                raise ValueError("opening and supporting walls have different surfaces")
            if opening["height_interval"][0] >= opening["height_interval"][1]:
                raise ValueError("invalid opening height interval")
            endpoints = np.asarray(opening["endpoints_local"], float)
            if np.linalg.norm(endpoints[1] - endpoints[0]) <= 0:
                raise ValueError("nonzero opening width required")
    referenced = set()
    for entity in model["rooms"] + model["walls"] + model["openings"]:
        for reference in entity["measurement_ids"]:
            if (
                reference not in measurements
                or measurements[reference]["owner_id"] != entity["id"]
            ):
                raise ValueError("invalid measurement reference or owner")
            referenced.add(reference)
    if referenced != set(measurements):
        raise ValueError("orphan measurement")
    for item in measurements.values():
        if item["owner_id"] not in owners:
            raise ValueError("unknown measurement owner")
        if (item["kind"] == "wall_length") != (item["owner_id"] in walls):
            raise ValueError("measurement kind does not match owner")
        if (item["kind"] == "opening_width") != (
            item["owner_id"] in {opening["id"] for opening in model["openings"]}
        ):
            raise ValueError("opening measurement kind does not match owner")
        value = item["value"]
        interval = item["uncertainty"]["conditional_interval"]
        if value is not None and (
            interval is None or not interval[0] <= value <= interval[1]
        ):
            raise ValueError("measurement must lie in its conditional interval")
        if value is None and interval is not None:
            raise ValueError("unavailable measurement cannot have an interval")
    return model


def measure_geometry(geometry):
    """Return version 1 dimensions conditional on the supplied geometry hypothesis."""
    if (
        geometry.get("schema_version") != 1
        or geometry["provenance"].get("scale_status") != "unverified"
    ):
        raise ValueError("unsupported geometry schema or scale status")
    capture = geometry["capture_id"]
    if (
        not isinstance(capture, str)
        or not capture
        or capture in (".", "..")
        or "/" in capture
        or "\\" in capture
    ):
        raise ValueError("invalid capture_id")
    config = geometry["provenance"]["config"]
    distance, junction = (
        float(config["plane_distance"]),
        float(config["junction_tolerance"]),
    )
    if not np.isfinite([distance, junction]).all() or min(distance, junction) <= 0:
        raise ValueError("positive finite geometry tolerances required")
    surfaces = {surface["id"]: surface for surface in geometry["surfaces"]}
    if len(surfaces) != len(geometry["surfaces"]):
        raise ValueError("duplicate source surface IDs")
    for surface in surfaces.values():
        equation = np.asarray(surface["equation_world"], float)
        residual = surface["residual_median"]
        if (
            equation.shape != (4,)
            or not np.isfinite(equation).all()
            or not np.isclose(np.linalg.norm(equation[:3]), 1, atol=1e-5)
        ):
            raise ValueError("normalized finite plane equation required")
        if not np.isfinite(residual) or residual < 0:
            raise ValueError("nonnegative finite residual required")
    model = {
        "schema_version": "1.0.0",
        "capture_id": capture,
        "scale": {
            "status": "unverified",
            "length_unit": "pose_unit",
            "area_unit": "pose_unit_squared",
            "meters_per_pose_unit": None,
            "physical_interval_status": "unbounded_unknown_scale",
        },
        "rooms": [],
        "walls": [],
        "openings": [],
        "measurements": [],
        "flags": sorted(
            set(
                list(geometry["flags"])
                + ["uncertainty_uncalibrated", "openings_not_inferred"]
            )
        ),
        "provenance": {
            "geometry_sha256": hashlib.sha256(
                json.dumps(
                    geometry, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest(),
            "source_depth_pose_sha256": geometry["provenance"].get(
                "source_depth_pose_sha256"
            ),
            "hypothesis": geometry["provenance"].get("hypothesis"),
            "orientation_status": geometry["orientation"]["status"],
            "id_policy": "capture and exact geometry rounded to six decimals; stable under array reordering, not geometry revisions",
            "uncertainty_method": "deterministic geometry sensitivity, not a confidence interval",
            "excluded_errors": [
                "unknown physical scale",
                "pose drift",
                "wrong surface roles or topology",
                "sensor bias",
                "unobserved geometry",
            ],
            "geometry_tolerances": {
                "plane_distance": distance,
                "junction_tolerance": junction,
            },
        },
    }

    def radius(source_ids, boundary=False):
        if not source_ids or not set(source_ids) <= set(surfaces):
            raise ValueError("measurement needs known surface evidence")
        return (
            distance
            + max(surfaces[s]["residual_median"] for s in source_ids)
            + (junction if boundary else 0)
        )

    def add_measurement(
        owner, kind, value, interval, evidence, assumptions, reason=None
    ):
        item = {
            "id": stable_id("measurement", capture, [owner["id"], kind]),
            "owner_id": owner["id"],
            "kind": kind,
            "status": "unavailable" if value is None else "candidate",
            "value": value,
            "unit": "pose_unit_squared" if kind == "floor_area" else "pose_unit",
            "evidence": evidence,
            "unavailable_reason": reason,
            "uncertainty": {
                "status": "uncalibrated",
                "method": "geometry_sensitivity_v1",
                "confidence_level": None,
                "conditional_interval": interval,
                "physical_interval": None,
                "assumptions": assumptions,
            },
        }
        owner["measurement_ids"].append(item["id"])
        model["measurements"].append(item)

    def add_wall(endpoints, source_ids, kind, room_id=None):
        endpoints = np.asarray(endpoints, float)
        if endpoints.shape != (2, 2) or not np.isfinite(endpoints).all():
            raise ValueError("finite wall endpoints required")
        ordered = sorted(np.round(endpoints, 6).tolist())
        length = float(np.linalg.norm(endpoints[1] - endpoints[0]))
        if length <= 0:
            raise ValueError("nonzero wall required")
        wall = {
            "id": stable_id("wall", capture, [kind, room_id, ordered]),
            "kind": kind,
            "room_id": room_id,
            "endpoints_local": ordered,
            "source_surface_ids": sorted(set(source_ids)),
            "measurement_ids": [],
        }
        if any(item["id"] == wall["id"] for item in model["walls"]):
            return wall["id"]
        displacement = radius(source_ids, boundary=kind == "region_boundary")
        add_measurement(
            wall,
            "wall_length",
            length,
            [max(0.0, length - 2 * displacement), length + 2 * displacement],
            {
                "surface_ids": sorted(set(source_ids)),
                "endpoint_displacement_pose_units": displacement,
            },
            [
                "Each endpoint may move within the stated displacement; wall identity and orientation fixed",
                "Observed support extent is not necessarily a complete physical wall"
                if kind == "observed_run"
                else "Candidate junction topology fixed",
            ],
        )
        model["walls"].append(wall)
        return wall["id"]

    orientation = geometry["orientation"]
    if orientation["status"] not in ("provisional", "explicit_unverified"):
        if geometry["walls"] or geometry["regions"]:
            raise ValueError(
                "unresolved orientation cannot contain measurable walls or regions"
            )
        return validate_model(model)
    for wall in geometry["walls"]:
        add_wall(wall["endpoints"], [wall["surface_id"]], "observed_run")
    floor_ids = [s["id"] for s in surfaces.values() if s["role"] == "floor_candidate"]
    if geometry["regions"] and len(floor_ids) != 1:
        raise ValueError("regions require one candidate floor")
    basis = np.asarray(orientation.get("basis_world_to_local"), float)
    origin = np.asarray(orientation.get("origin_world"), float)
    if geometry["regions"] and (
        basis.shape != (3, 3)
        or origin.shape != (3,)
        or not np.isfinite(basis).all()
        or not np.isfinite(origin).all()
        or not np.allclose(basis @ basis.T, np.eye(3), atol=1e-5)
    ):
        raise ValueError("finite orthonormal local frame required")
    for region in geometry["regions"]:
        outer = canonical_ring(region["polygon"])
        holes = sorted(canonical_ring(hole) for hole in region.get("holes", []))
        polygon = Polygon(outer, holes)
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError("valid nonzero region polygon required")
        room = {
            "id": stable_id("room", capture, [outer, holes]),
            "status": "candidate_region",
            "source_region_id": region["id"],
            "polygon_local": outer,
            "holes_local": holes,
            "wall_ids": [],
            "measurement_ids": [],
        }
        source_ids = set(floor_ids)
        for ring in (outer, *holes):
            for a, b in pairwise(ring):
                edge = LineString([a, b])
                supported = sorted(
                    {
                        wall["surface_id"]
                        for wall in geometry["walls"]
                        if LineString(wall["junction_endpoints"])
                        .buffer(1e-5)
                        .covers(edge)
                    }
                )
                if not supported:
                    raise ValueError("region boundary lacks full wall evidence")
                source_ids.update(supported)
                room["wall_ids"].append(
                    add_wall([a, b], supported, "region_boundary", room["id"])
                )
        displacement = radius(source_ids, boundary=True)
        add_measurement(
            room,
            "floor_area",
            float(polygon.area),
            [
                float(polygon.buffer(-displacement).area),
                float(polygon.buffer(displacement, quad_segs=32).area),
            ],
            {
                "surface_ids": sorted(source_ids),
                "boundary_displacement_pose_units": displacement,
                "floor_samples": region["floor_samples"],
                "camera_samples": region["camera_samples"],
            },
            [
                "Eroded/dilated footprint sensitivity envelope including holes; not a guaranteed error bound",
                "Candidate floor, orientation and boundary topology fixed; not whole-property area",
            ],
        )
        candidates = []
        for ceiling in surfaces.values():
            if ceiling["role"] != "ceiling_candidate":
                continue
            patch = np.asarray(ceiling["patch_world"], float)
            if (
                patch.ndim != 2
                or patch.shape[1] != 3
                or len(patch) < 3
                or not np.isfinite(patch).all()
            ):
                raise ValueError("finite ceiling patch required")
            local = (patch - origin) @ basis.T
            envelope = Polygon(local[:, [0, 2]])
            if not envelope.is_valid:
                raise ValueError("invalid ceiling envelope")
            overlap = polygon.intersection(envelope)
            if overlap.area / polygon.area < 0.5:
                continue
            pieces = list(overlap.geoms) if hasattr(overlap, "geoms") else [overlap]
            coords = np.concatenate(
                [
                    np.asarray(piece.exterior.coords)
                    for piece in pieces
                    if isinstance(piece, Polygon)
                ]
            )
            world = origin + coords @ basis[[0, 2]]
            heights = []
            for surface_id in (floor_ids[0], ceiling["id"]):
                eq = np.asarray(surfaces[surface_id]["equation_world"])
                denominator = float(eq[:3] @ basis[1])
                if abs(denominator) < 0.9:
                    raise ValueError("floor/ceiling plane not aligned to up")
                heights.append(-(world @ eq[:3] + eq[3]) / denominator)
            gap = heights[1] - heights[0]
            if gap.min() > 0:
                candidates.append((ceiling["id"], gap, overlap.area / polygon.area))
        if len(candidates) == 1:
            ceiling_id, gap, coverage = candidates[0]
            displacement = 2 * radius([floor_ids[0], ceiling_id])
            value = float((gap.min() + gap.max()) / 2)
            add_measurement(
                room,
                "ceiling_height",
                value,
                [
                    max(0.0, float(gap.min()) - displacement),
                    float(gap.max()) + displacement,
                ],
                {
                    "surface_ids": [floor_ids[0], ceiling_id],
                    "envelope_overlap_fraction": float(coverage),
                    "height_range_pose_units": [float(gap.min()), float(gap.max())],
                },
                [
                    "Height along provisional up, midrange over overlapping plane envelopes",
                    "Ceiling envelope is a coverage proxy, not proof of a filled observed surface",
                    "Floor and ceiling residual/tolerance allowances applied without dividing by sample count",
                ],
            )
        else:
            add_measurement(
                room,
                "ceiling_height",
                None,
                None,
                {"surface_ids": floor_ids},
                [],
                "no_supported_ceiling"
                if not candidates
                else "multiple_ceiling_candidates",
            )
        model["rooms"].append(room)
    model["rooms"].sort(key=lambda item: item["id"])
    model["walls"].sort(key=lambda item: item["id"])
    model["measurements"].sort(key=lambda item: item["id"])
    return validate_model(model)
