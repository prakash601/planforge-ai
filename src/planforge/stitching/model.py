"""Stitch per-capture candidate models into one candidate property model.

The user instructed us to assume all sample captures come from the same
property. That assumption is recorded in provenance; it is not evidence of
shared rooms, shared openings, or measured alignment. Transforms default to
identity with unverified status. Adjacency edges exist only from explicit
manual links or shared opening evidence, neither of which the samples provide.
"""

import json
import math
from copy import deepcopy
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator
from shapely import Polygon

from planforge.measurements import validate_model
from planforge.measurements.model import canonical_ring


PROPERTY_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class StitchingConfig:
    property_id: str = "property-assumed-single"

    def __post_init__(self):
        pid = self.property_id
        if not isinstance(pid, str) or not pid:
            raise ValueError("property_id must be a nonempty string")
        if len(pid) > 64 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in pid.lower()) or pid.strip() != pid:
            # Keep permissive but reject path-like or empty ids.
            if "/" in pid or "\\" in pid or pid in (".", ".."):
                raise ValueError("invalid property_id")


def _load_schema():
    text = files("planforge.stitching").joinpath("schema-property-v1.json").read_text()
    return json.loads(text)


def _apply_transform(points, rotation_deg, translation):
    pts = np.asarray(points, dtype=float)
    theta = math.radians(float(rotation_deg))
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    rot = np.array([[cos_t, -sin_t], [sin_t, cos_t]])
    out = pts @ rot.T + np.asarray(translation, dtype=float)
    return [[float(x), float(y)] for x, y in out]


def _parse_transforms(raw, capture_ids):
    """Normalize optional manual transforms; default is unverified identity."""
    parsed = {}
    provenance = {}
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("transforms must be an object keyed by capture_id")
    unknown = set(raw) - set(capture_ids)
    if unknown:
        raise ValueError(f"transforms reference unknown captures: {sorted(unknown)}")
    for cap in capture_ids:
        entry = raw.get(cap, None)
        if entry is None:
            parsed[cap] = {"rotation_deg": 0.0, "translation": [0.0, 0.0]}
            provenance[cap] = "default_identity_unverified_no_alignment_evidence"
            continue
        if isinstance(entry, (list, tuple)) and len(entry) == 3:
            rotation, tx, ty = entry
        elif isinstance(entry, dict):
            rotation = entry.get("rotation_deg", 0.0)
            tr = entry.get("translation", [0.0, 0.0])
            tx, ty = tr[0], tr[1]
        else:
            raise ValueError(f"invalid transform for {cap}")
        rotation = float(rotation)
        tx, ty = float(tx), float(ty)
        if not np.isfinite([rotation, tx, ty]).all():
            raise ValueError(f"nonfinite transform for {cap}")
        parsed[cap] = {"rotation_deg": rotation, "translation": [tx, ty]}
        provenance[cap] = "manual_unverified_not_measured_alignment"
    return parsed, provenance


def _parse_links(raw, room_ids):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("links must be a list")
    edges = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each link must be an object")
        a, b = item.get("room_a"), item.get("room_b")
        kind = item.get("kind", "manual_adjacency_unverified")
        evidence = item.get("evidence", "manual_link_without_measured_shared_opening")
        if a not in room_ids or b not in room_ids or a == b:
            raise ValueError("link references unknown or identical rooms")
        key = tuple(sorted((a, b)))
        if key in seen:
            raise ValueError("duplicate link")
        seen.add(key)
        edges.append({"room_a": a, "room_b": b, "kind": kind, "evidence": evidence, "status": "manual_candidate_unverified"})
    return sorted(edges, key=lambda e: (e["room_a"], e["room_b"]))


def load_inputs(paths):
    models = []
    for path in paths:
        path = Path(path)
        model = json.loads(path.read_text())
        validate_model(model)
        if model["scale"].get("status") != "unverified":
            raise ValueError("only unverified-scale candidate models can be stitched")
        models.append((str(path), model))
    capture_ids = [m["capture_id"] for _, m in models]
    if len(set(capture_ids)) != len(capture_ids):
        raise ValueError("duplicate capture_id inputs")
    return models


def stitch_measurements(models_with_paths, config=None, transforms=None, links=None):
    """Combine validated per-capture models into a candidate property model."""
    config = StitchingConfig() if config is None else config
    if not models_with_paths:
        raise ValueError("at least one input model required")
    for _, model in models_with_paths:
        validate_model(model)
    capture_ids = [m["capture_id"] for _, m in models_with_paths]
    if len(set(capture_ids)) != len(capture_ids):
        raise ValueError("duplicate capture_id inputs")

    parsed_tf, tf_provenance = _parse_transforms(transforms, capture_ids)

    # Collect rooms first so links can be validated.
    rooms = []
    walls = []
    openings = []
    measurements = []
    for _, model in models_with_paths:
        cap = model["capture_id"]
        tf = parsed_tf[cap]
        for room in model["rooms"]:
            entry = deepcopy(room)
            entry["capture_id"] = cap
            entry["polygon_property"] = _apply_transform(room["polygon_local"], tf["rotation_deg"], tf["translation"])
            entry["holes_property"] = [
                _apply_transform(h, tf["rotation_deg"], tf["translation"]) for h in room["holes_local"]
            ]
            # Validate transformed polygon.
            poly = Polygon(canonical_ring(entry["polygon_property"]),
                           [canonical_ring(h) for h in entry["holes_property"]] or None)
            if not poly.is_valid or poly.area <= 0:
                raise ValueError("invalid transformed room polygon")
            rooms.append(entry)
        for wall in model["walls"]:
            entry = deepcopy(wall)
            entry["capture_id"] = cap
            entry["endpoints_property"] = _apply_transform(wall["endpoints_local"], tf["rotation_deg"], tf["translation"])
            walls.append(entry)
        for opening in model["openings"]:
            entry = deepcopy(opening)
            entry["capture_id"] = cap
            entry["endpoints_property"] = _apply_transform(opening["endpoints_local"], tf["rotation_deg"], tf["translation"])
            openings.append(entry)
        for item in model["measurements"]:
            entry = deepcopy(item)
            entry["capture_id"] = cap
            measurements.append(entry)

    room_ids = [r["id"] for r in rooms]
    if len(set(room_ids)) != len(room_ids):
        raise ValueError("room ID collision across captures")
    wall_ids = [w["id"] for w in walls]
    if len(set(wall_ids)) != len(wall_ids):
        raise ValueError("wall ID collision across captures")

    edges = _parse_links(links, set(room_ids))

    # Overlap detection in the common property frame.
    overlaps = []
    polys = {}
    for room in rooms:
        polys[room["id"]] = Polygon(canonical_ring(room["polygon_property"]),
                                    [canonical_ring(h) for h in room["holes_property"]] or None)
    ids_sorted = sorted(polys)
    for i in range(len(ids_sorted)):
        for j in range(i + 1, len(ids_sorted)):
            a, b = ids_sorted[i], ids_sorted[j]
            inter = polys[a].intersection(polys[b])
            area = float(inter.area) if inter.is_valid else 0.0
            if area > 1e-9:
                overlaps.append({"room_a": a, "room_b": b, "overlap_area_pose2": area,
                                 "status": "overlap_unresolved_no_alignment_evidence"})

    flags = [
        "scale_unverified_pose_units_not_meters",
        "single_property_assumed_per_user_instruction_not_evidence",
        "transforms_unverified_identity_or_manual",
        "drift_uncorrected",
        "uncertainty_uncalibrated",
    ]
    if any(len(m["rooms"]) == 0 for _, m in models_with_paths):
        flags.append("partial_captures_without_closed_regions")
    if any("orientation_ambiguous" in m.get("flags", []) for _, m in models_with_paths):
        flags.append("orientation_unresolved_in_some_captures")
    if any("ceiling_unobserved" in m.get("flags", []) or "ceiling_role_unresolved" in m.get("flags", []) for _, m in models_with_paths):
        flags.append("ceiling_unobserved_or_unresolved_in_some_captures")
    if len(rooms) > 1 and not edges:
        flags.append("rooms_unconnected_no_shared_opening_evidence")
    if len(rooms) <= 1:
        flags.append("single_connected_room_only_no_property_layout_proven")
    if overlaps:
        flags.append("room_footprint_overlap_unresolved")
    if any(m["openings"] for _, m in models_with_paths):
        flags.append("openings_geometry_candidates_only")
    else:
        flags.append("no_associated_openings_in_inputs")
    flags = sorted(set(flags))

    prop = {
        "schema_version": PROPERTY_SCHEMA_VERSION,
        "property_id": config.property_id,
        "scale": {
            "status": "unverified",
            "length_unit": "pose_unit",
            "area_unit": "pose_unit_squared",
            "meters_per_pose_unit": None,
            "physical_interval_status": "unbounded_unknown_scale",
        },
        "rooms": sorted(rooms, key=lambda r: r["id"]),
        "walls": sorted(walls, key=lambda w: w["id"]),
        "openings": sorted(openings, key=lambda o: o["id"]),
        "measurements": sorted(measurements, key=lambda m: m["id"]),
        "room_graph": {
            "nodes": sorted(
                [{"room_id": r["id"], "capture_id": r["capture_id"],
                  "source_region_id": r.get("source_region_id"),
                  "status": r.get("status")} for r in rooms],
                key=lambda n: n["room_id"],
            ),
            "edges": edges,
        },
        "transforms": {
            cap: {"rotation_deg": parsed_tf[cap]["rotation_deg"],
                  "translation": list(parsed_tf[cap]["translation"]),
                  "provenance": tf_provenance[cap],
                  "status": "unverified"}
            for cap in capture_ids
        },
        "overlaps": sorted(overlaps, key=lambda o: (o["room_a"], o["room_b"])),
        "flags": flags,
        "provenance": {
            "inputs": [
                {"path": path, "capture_id": m["capture_id"],
                 "schema_version": m["schema_version"],
                 "geometry_sha256": m["provenance"].get("geometry_sha256"),
                 "source_depth_pose_sha256": m["provenance"].get("source_depth_pose_sha256")}
                for path, m in models_with_paths
            ],
            "same_property_assumption": "assumed_per_user_instruction_2026_10_03_not_evidence; capture room identities and shared openings unresolved",
            "alignment_method": "identity_or_manual_2d_rigid_unverified; no measured inter_capture_alignment",
            "adjacency_method": "explicit_manual_links_only; no_automatic_shared_opening_matching",
            "id_policy": "per_capture_stable_ids_preserved; not_cross_capture_physical_room_identifiers",
            "limitations": [
                "Unverified scale, orientation and supplied poses",
                "No drift correction or loop closure",
                "No measured inter-capture alignment",
                "No shared opening evidence in current samples",
                "Partial captures without closed regions included as observed runs only",
            ],
        },
    }
    return validate_property(prop)


def validate_property(prop):
    schema = _load_schema()
    Draft202012Validator(schema).validate(prop)
    json.dumps(prop, allow_nan=False)
    if prop.get("schema_version") != PROPERTY_SCHEMA_VERSION:
        raise ValueError("unsupported property schema version")
    rooms = {r["id"]: r for r in prop["rooms"]}
    walls = {w["id"]: w for w in prop["walls"]}
    openings = {o["id"]: o for o in prop["openings"]}
    measurements = {m["id"]: m for m in prop["measurements"]}
    if len(rooms) != len(prop["rooms"]) or len(walls) != len(prop["walls"]):
        raise ValueError("duplicate room or wall IDs")
    if len(openings) != len(prop["openings"]) or len(measurements) != len(prop["measurements"]):
        raise ValueError("duplicate opening or measurement IDs")
    # Foreign keys: wall room refs, room wall refs, measurement owners.
    for wall in prop["walls"]:
        if wall.get("room_id") is not None and wall["room_id"] not in rooms:
            raise ValueError("wall references unknown room")
    for room in prop["rooms"]:
        if not set(room["wall_ids"]) <= set(walls):
            raise ValueError("room references unknown wall")
        poly = Polygon(canonical_ring(room["polygon_property"]),
                       [canonical_ring(h) for h in room["holes_property"]] or None)
        if not poly.is_valid or poly.area <= 0:
            raise ValueError("invalid property room polygon")
        for ring in (room["polygon_property"], *room["holes_property"]):
            pts = np.asarray(ring, float)
            if pts.ndim != 2 or pts.shape[1] != 2 or not np.isfinite(pts).all():
                raise ValueError("nonfinite property polygon")
    for edge in prop["room_graph"]["edges"]:
        if edge["room_a"] not in rooms or edge["room_b"] not in rooms:
            raise ValueError("graph edge references unknown room")
    for item in prop["measurements"]:
        if item["owner_id"] not in {**rooms, **walls, **openings}:
            raise ValueError("measurement references unknown owner")
    for cap, tf in prop["transforms"].items():
        vals = [tf["rotation_deg"], *tf["translation"]]
        if len(tf["translation"]) != 2 or not np.isfinite(vals).all():
            raise ValueError("nonfinite transform")
    return prop
