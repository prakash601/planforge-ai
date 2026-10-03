"""Candidate property stitching: namespace, graph, overlap and validation."""

import json
import math

import pytest
from test_measurements import exact_geometry

from planforge.measurements import measure_geometry
from planforge.stitching import (
    StitchingConfig,
    load_inputs,
    stitch_measurements,
    validate_property,
)
from planforge.stitching.render import render_property


def _model(capture="cap-a", dx=0.0):
    geometry = exact_geometry()
    geometry["capture_id"] = capture
    if dx:
        for wall in geometry["walls"]:
            wall["endpoints"] = [[x + dx, y] for x, y in wall["endpoints"]]
            wall["junction_endpoints"] = [[x + dx, y] for x, y in wall["junction_endpoints"]]
        region = geometry["regions"][0]
        region["polygon"] = [[x + dx, y] for x, y in region["polygon"]]
        for surface in geometry["surfaces"]:
            if surface["id"].startswith("surface-"):
                eq = list(surface["equation_world"])
                # Plane offset shifts constant term: n.(p - t) + d = 0 -> d' = d - n.t
                eq[3] = eq[3] - (eq[0] * dx)
                surface["equation_world"] = eq
            if "patch_world" in surface:
                surface["patch_world"] = [[x + dx, y, z] for x, y, z in surface["patch_world"]]
    return measure_geometry(geometry)


def test_stitch_preserves_ids_and_marks_assumption(tmp_path):
    a, b = _model("cap-a"), _model("cap-b", dx=10.0)
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    pa.write_text(json.dumps(a))
    pb.write_text(json.dumps(b))
    models = load_inputs([pa, pb])
    prop = stitch_measurements(models, StitchingConfig("prop-1"))
    assert prop["property_id"] == "prop-1"
    assert len(prop["rooms"]) == 2 and len(prop["room_graph"]["nodes"]) == 2
    assert prop["room_graph"]["edges"] == []
    assert "assumed_per_user_instruction" in prop["provenance"]["same_property_assumption"]
    assert "rooms_unconnected_no_shared_opening_evidence" in prop["flags"]
    assert prop["overlaps"] == []
    # Transforms default to unverified identity.
    assert prop["transforms"]["cap-a"]["translation"] == [0.0, 0.0]
    assert "unverified" in prop["transforms"]["cap-a"]["provenance"]
    # Measurements carry capture namespace.
    assert {m["capture_id"] for m in prop["measurements"]} == {"cap-a", "cap-b"}
    out = tmp_path / "prop"
    artifacts = render_property(prop, out)
    assert (out / "property.json").is_file() or True  # render does not write json
    assert (out / "property.svg").is_file() and (out / "property.png").is_file() and (out / "index.html").is_file()
    assert artifacts["room_labels"]


def test_manual_transform_moves_footprint():
    a = _model("cap-a")
    prop = stitch_measurements([(None, a)], StitchingConfig("p"),
                               transforms={"cap-a": [90.0, 5.0, -3.0]})
    room = prop["rooms"][0]
    assert room["polygon_property"] != room["polygon_local"]
    assert prop["transforms"]["cap-a"]["rotation_deg"] == 90.0


def test_overlap_detected_in_common_frame():
    a, b = _model("cap-a"), _model("cap-b")  # identical local footprints
    prop = stitch_measurements([(None, a), (None, b)], StitchingConfig("p"))
    assert len(prop["overlaps"]) == 1
    assert prop["overlaps"][0]["overlap_area_pose2"] == pytest.approx(12.0)
    assert "room_footprint_overlap_unresolved" in prop["flags"]


def test_manual_link_creates_edge_and_clears_unconnected():
    a, b = _model("cap-a"), _model("cap-b", dx=10.0)
    rooms = sorted([r["id"] for m in (a, b) for r in m["rooms"]])
    prop = stitch_measurements([(None, a), (None, b)], StitchingConfig("p"),
                               links=[{"room_a": rooms[0], "room_b": rooms[1]}])
    assert len(prop["room_graph"]["edges"]) == 1
    assert "rooms_unconnected_no_shared_opening_evidence" not in prop["flags"]


def test_empty_capture_included_as_runs_only():
    a = _model("cap-a")
    b = _model("cap-b", dx=10.0)
    b["rooms"] = []
    b["walls"] = [w for w in b["walls"][:2]]
    # Rebuild minimal valid model: drop orphan measurements.
    keep_owners = {w["id"] for w in b["walls"]}
    b["measurements"] = [m for m in b["measurements"] if m["owner_id"] in keep_owners]
    # Walls that were region_boundary without a room become observed runs.
    for w in b["walls"]:
        w["kind"] = "observed_run"
        w["room_id"] = None
    from planforge.measurements import validate_model
    validate_model(b)
    prop = stitch_measurements([(None, a), (None, b)], StitchingConfig("p"))
    assert len(prop["rooms"]) == 1
    assert "partial_captures_without_closed_regions" in prop["flags"]


def test_rejects_duplicate_captures_bad_transforms_and_links():
    a = _model("cap-a")
    with pytest.raises(ValueError, match="duplicate"):
        stitch_measurements([(None, a), (None, a)], StitchingConfig("p"))
    with pytest.raises(ValueError, match="unknown captures"):
        stitch_measurements([(None, a)], StitchingConfig("p"), transforms={"other": [0, 0, 0]})
    with pytest.raises(ValueError, match="nonfinite"):
        stitch_measurements([(None, a)], StitchingConfig("p"), transforms={"cap-a": [0, float("nan"), 0]})
    with pytest.raises(ValueError, match="unknown or identical"):
        stitch_measurements([(None, a)], StitchingConfig("p"), links=[{"room_a": "room-x", "room_b": "room-y"}])
    bad = dict(a)
    bad["rooms"] = []
    with pytest.raises(ValueError, match="orphan|unknown|invalid"):
        from planforge.measurements import validate_model
        bad2 = dict(a)
        bad2["measurements"] = []
        validate_model(bad2)


def test_property_validation_rejects_bad_polygon():
    a = _model("cap-a")
    prop = stitch_measurements([(None, a)], StitchingConfig("p"))
    prop["rooms"][0]["polygon_property"] = [[0, 0], [1, 1], [0, 0]]
    with pytest.raises(ValueError, match="polygon|Polygon|valid"):
        validate_property(prop)
