"""Attach opening evidence without inventing a wall across an observed gap."""

from copy import deepcopy

import numpy as np
from shapely import LineString, Point

from planforge.measurements import validate_model
from planforge.measurements.model import stable_id


def attach_openings(model, detection):
    validate_model(model)
    if (
        detection["schema_version"] != 1
        or detection["capture_id"] != model["capture_id"]
    ):
        raise ValueError("opening detection capture/schema mismatch")
    if (
        detection["provenance"]["geometry_sha256"]
        != model["provenance"]["geometry_sha256"]
    ):
        raise ValueError("opening detection geometry hash mismatch")
    if model["openings"]:
        raise ValueError(
            "opening detection must attach to a base model without openings"
        )
    result = deepcopy(model)
    result["schema_version"] = "1.1.0"
    result["provenance"]["opening_detection"] = deepcopy(detection["provenance"])
    result["flags"] = sorted(
        (set(result["flags"]) - {"openings_not_inferred"})
        | {
            "openings_geometry_candidates_only",
            "opening_semantic_classes_unverified",
            "rgb_alignment_unverified",
        }
    )
    config = detection["provenance"]["config"]
    unmatched = 0
    for candidate in detection["candidates"]:
        endpoints = np.asarray(candidate["endpoints_local"], float)
        eligible = [
            wall
            for wall in result["walls"]
            if candidate["surface_id"] in wall["source_surface_ids"]
        ]
        edge = LineString(endpoints)
        contained = [
            wall
            for wall in eligible
            if LineString(wall["endpoints_local"])
            .buffer(config["plane_distance"])
            .covers(edge)
        ]
        if contained:
            supporting = [
                min(
                    contained,
                    key=lambda wall: (wall["kind"] != "region_boundary", wall["id"]),
                )
            ]
            association = "contained"
        else:
            # A doorway can separate two observed runs. Associate the jamb runs;
            # do not fabricate a continuous physical wall through the opening.
            supporting = []
            for endpoint in endpoints:
                nearby = sorted(
                    eligible,
                    key=lambda wall: (
                        LineString(wall["endpoints_local"]).distance(Point(endpoint)),
                        wall["id"],
                    ),
                )
                if (
                    nearby
                    and LineString(nearby[0]["endpoints_local"]).distance(
                        Point(endpoint)
                    )
                    <= 2 * config["cell_size"] + config["plane_distance"]
                ):
                    supporting.append(nearby[0])
            if len(supporting) != 2 or supporting[0]["id"] == supporting[1]["id"]:
                unmatched += 1
                continue
            association = "adjacent_support"
        support_ids = sorted({wall["id"] for wall in supporting})
        opening_id = stable_id(
            "opening",
            model["capture_id"],
            [
                candidate["surface_id"],
                sorted(np.round(endpoints, 6).tolist()),
                candidate["height_interval"],
            ],
        )
        opening = {
            "id": opening_id,
            "wall_id": support_ids[0],
            "support_wall_ids": support_ids,
            "association": association,
            "kind": candidate["kind"],
            "status": "candidate",
            "source_surface_id": candidate["surface_id"],
            "endpoints_local": endpoints.tolist(),
            "height_interval": list(candidate["height_interval"]),
            "evidence": deepcopy(candidate["evidence"]),
            "measurement_ids": [],
        }
        width = float(np.linalg.norm(endpoints[1] - endpoints[0]))
        allowance = 2 * (
            config["cell_size"]
            + config["plane_distance"]
            + candidate["surface_residual_median"]
        )
        measurement_id = stable_id(
            "measurement", model["capture_id"], [opening_id, "opening_width"]
        )
        opening["measurement_ids"].append(measurement_id)
        result["openings"].append(opening)
        result["measurements"].append(
            {
                "id": measurement_id,
                "owner_id": opening_id,
                "kind": "opening_width",
                "status": "candidate",
                "value": width,
                "unit": "pose_unit",
                "unavailable_reason": None,
                "evidence": {
                    "surface_ids": [candidate["surface_id"]],
                    "raster_cell_pose_units": config["cell_size"],
                    "representative_ray_count": candidate["evidence"][
                        "representative_ray_count"
                    ],
                    "supporting_frames": candidate["evidence"]["supporting_frames"],
                },
                "uncertainty": {
                    "status": "uncalibrated",
                    "method": "opening_grid_sensitivity_v1",
                    "confidence_level": None,
                    "conditional_interval": [
                        max(0.0, width - allowance),
                        width + allowance,
                    ],
                    "physical_interval": None,
                    "assumptions": [
                        "Raster edges, fixed candidate plane and gap identity",
                        "Geometry and representative sight lines only; door/window class unverified",
                        "Unknown scale, drift, missing/phantom detection and sensor bias excluded",
                    ],
                },
            }
        )
    result["provenance"]["opening_detection"]["unassociated_candidates"] = unmatched
    if detection["unresolved_gaps"] or unmatched:
        result["flags"].append("unresolved_wall_gaps")
    result["openings"].sort(key=lambda opening: opening["id"])
    result["measurements"].sort(key=lambda measurement: measurement["id"])
    return validate_model(result)
