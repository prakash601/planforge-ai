from copy import deepcopy
from importlib.resources import files
import json
import subprocess
import sys

from jsonschema import Draft202012Validator, ValidationError
import numpy as np
import pytest

from planforge.geometry import extract_geometry
from planforge.measurements import measure_geometry, validate_model
from test_geometry import synthetic_room


def exact_geometry(outline=((0, 0), (4, 0), (4, 3), (0, 3)), holes=(), ceiling=True):
    rings = [list(outline) + [outline[0]], *[list(hole) + [hole[0]] for hole in holes]]
    surfaces = [
        {
            "id": "floor",
            "role": "floor_candidate",
            "equation_world": [0, 1, 0, 0],
            "residual_median": 0,
        }
    ]
    if ceiling:
        surfaces.append(
            {
                "id": "ceiling",
                "role": "ceiling_candidate",
                "equation_world": [0, 1, 0, -2.8],
                "residual_median": 0,
                "patch_world": [[-1, 2.8, -1], [5, 2.8, -1], [5, 2.8, 4], [-1, 2.8, 4]],
            }
        )
    walls = []
    for ring in rings:
        for a, b in zip(ring[:-1], ring[1:]):
            name = f"surface-{len(walls)}"
            direction = np.array(b) - a
            normal = np.array([direction[1], -direction[0]]) / np.linalg.norm(direction)
            surfaces.append(
                {
                    "id": name,
                    "role": "wall_candidate",
                    "equation_world": [normal[0], 0, normal[1], -float(normal @ a)],
                    "residual_median": 0,
                }
            )
            walls.append(
                {"surface_id": name, "endpoints": [a, b], "junction_endpoints": [a, b]}
            )
    return {
        "schema_version": 1,
        "capture_id": "synthetic",
        "orientation": {
            "status": "explicit_unverified",
            "basis_world_to_local": np.eye(3).tolist(),
            "origin_world": [0, 0, 0],
        },
        "surfaces": surfaces,
        "walls": walls,
        "regions": [
            {
                "id": "region-0",
                "polygon": rings[0],
                "holes": rings[1:],
                "floor_samples": 100,
                "camera_samples": 5,
            }
        ],
        "flags": ["scale_unverified"],
        "provenance": {
            "scale_status": "unverified",
            "config": {"plane_distance": 0.06, "junction_tolerance": 0.2},
        },
    }


def measurement(model, kind, owner=None):
    return [
        item
        for item in model["measurements"]
        if item["kind"] == kind and (owner is None or item["owner_id"] == owner)
    ]


def test_exact_rectangle_and_schema():
    model = measure_geometry(exact_geometry())
    assert measurement(model, "floor_area")[0]["value"] == 12
    assert measurement(model, "ceiling_height")[0]["value"] == pytest.approx(2.8)
    lengths = measurement(model, "wall_length")
    assert sorted(item["value"] for item in lengths) == [3, 3, 3, 3, 4, 4, 4, 4]
    assert model["scale"]["meters_per_pose_unit"] is None
    assert not model["openings"]
    for item in model["measurements"]:
        assert item["uncertainty"]["physical_interval"] is None
        assert item["uncertainty"]["confidence_level"] is None
        assert (
            item["uncertainty"]["conditional_interval"][0]
            <= item["value"]
            <= item["uncertainty"]["conditional_interval"][1]
        )
    Draft202012Validator.check_schema(
        json.loads(
            files("planforge.measurements").joinpath("schema-v1.json").read_text()
        )
    )


@pytest.mark.parametrize(
    "outline,area",
    [
        (((0, 0), (4, 0), (4, 1.4), (2, 1.4), (2, 3), (0, 3)), 8.8),
        (((0, 0), (4, 0), (3.3, 3), (0.6, 3)), 10.05),
    ],
)
def test_general_polygon_measurements(outline, area):
    assert measurement(measure_geometry(exact_geometry(outline)), "floor_area")[0][
        "value"
    ] == pytest.approx(area)


def test_holes_subtracted_and_boundaries_measured():
    model = measure_geometry(exact_geometry(holes=(((1, 1), (2, 1), (2, 2), (1, 2)),)))
    assert measurement(model, "floor_area")[0]["value"] == 11
    assert len(model["rooms"][0]["wall_ids"]) == 8
    assert len(model["rooms"][0]["holes_local"]) == 1


def test_synthetic_cloud_end_to_end_dimensions():
    model = measure_geometry(
        extract_geometry(synthetic_room(), up_vector=(0, 1, 0)).to_dict()
    )
    assert measurement(model, "floor_area")[0]["value"] == pytest.approx(12, abs=0.15)
    assert measurement(model, "ceiling_height")[0]["value"] == pytest.approx(
        2.8, abs=0.02
    )
    boundary = [wall for wall in model["walls"] if wall["kind"] == "region_boundary"]
    assert sorted(
        measurement(model, "wall_length", wall["id"])[0]["value"] for wall in boundary
    ) == pytest.approx([3, 3, 4, 4], abs=0.03)


def test_missing_ceiling_unavailable_not_wall_top():
    model = measure_geometry(exact_geometry(ceiling=False))
    height = measurement(model, "ceiling_height")[0]
    assert height["status"] == "unavailable"
    assert height["value"] is None
    assert height["uncertainty"]["conditional_interval"] is None
    assert height["unavailable_reason"] == "no_supported_ceiling"


def test_multiple_ceilings_and_nonoverlapping_ceiling():
    geometry = exact_geometry()
    other = deepcopy(geometry["surfaces"][1])
    other["id"] = "other-ceiling"
    geometry["surfaces"].append(other)
    assert (
        measurement(measure_geometry(geometry), "ceiling_height")[0][
            "unavailable_reason"
        ]
        == "multiple_ceiling_candidates"
    )
    geometry["surfaces"].pop()
    geometry["surfaces"][1]["patch_world"] = [
        [10, 2.8, 10],
        [11, 2.8, 10],
        [11, 2.8, 11],
        [10, 2.8, 11],
    ]
    assert measurement(measure_geometry(geometry), "ceiling_height")[0]["value"] is None


def test_sloped_ceiling_reports_range_not_constant_height():
    geometry = exact_geometry()
    normal = np.array([-0.1, 1, 0]) / np.sqrt(1.01)
    ceiling = geometry["surfaces"][1]
    ceiling["equation_world"] = [*normal, -2.8 / np.sqrt(1.01)]
    ceiling["patch_world"] = [
        [x, 2.8 + 0.1 * x, z] for x, z in [(-1, -1), (5, -1), (5, 4), (-1, 4)]
    ]
    height = measurement(measure_geometry(geometry), "ceiling_height")[0]
    assert height["value"] == pytest.approx(3)
    assert height["evidence"]["height_range_pose_units"] == pytest.approx([2.8, 3.2])


def test_ids_stable_under_order_winding_and_start_changes():
    geometry = exact_geometry()
    first = measure_geometry(geometry)
    geometry["surfaces"].reverse()
    geometry["walls"].reverse()
    for wall in geometry["walls"]:
        wall["endpoints"].reverse()
        wall["junction_endpoints"].reverse()
    ring = geometry["regions"][0]["polygon"][:-1]
    ring = list(reversed(ring[2:] + ring[:2]))
    geometry["regions"][0]["polygon"] = ring + [ring[0]]
    second = measure_geometry(geometry)
    assert first["rooms"] == second["rooms"]
    assert first["walls"] == second["walls"]
    assert first["measurements"] == second["measurements"]
    assert (
        first["provenance"]["geometry_sha256"]
        != second["provenance"]["geometry_sha256"]
    )


def test_uncertainty_widens_with_tolerances_not_sample_count():
    geometry = exact_geometry()
    first = measure_geometry(geometry)
    geometry["regions"][0]["floor_samples"] *= 100
    second = measure_geometry(geometry)
    assert (
        measurement(first, "floor_area")[0]["uncertainty"]
        == measurement(second, "floor_area")[0]["uncertainty"]
    )
    geometry["provenance"]["config"]["junction_tolerance"] = 0.4
    third = measure_geometry(geometry)
    a = measurement(first, "floor_area")[0]["uncertainty"]["conditional_interval"]
    b = measurement(third, "floor_area")[0]["uncertainty"]["conditional_interval"]
    assert b[0] < a[0] < a[1] < b[1]


def test_partial_and_ambiguous_no_invented_rooms():
    geometry = exact_geometry()
    geometry["regions"] = []
    model = measure_geometry(geometry)
    assert not model["rooms"]
    assert len(measurement(model, "wall_length")) == 4
    geometry["orientation"] = {"status": "ambiguous"}
    geometry["walls"] = []
    assert not measure_geometry(geometry)["measurements"]


@pytest.mark.parametrize(
    "mutation",
    [
        "scale",
        "nan",
        "tolerance",
        "unsupported",
        "unclosed",
        "plane",
        "basis",
        "duplicate",
    ],
)
def test_invalid_geometry_rejected(mutation):
    geometry = exact_geometry()
    if mutation == "scale":
        geometry["provenance"]["scale_status"] = "verified"
    if mutation == "nan":
        geometry["walls"][0]["endpoints"][0] = [float("nan"), 0]
    if mutation == "tolerance":
        geometry["provenance"]["config"]["plane_distance"] = 0
    if mutation == "unsupported":
        geometry["walls"].pop()
    if mutation == "unclosed":
        geometry["regions"][0]["polygon"].pop()
    if mutation == "plane":
        geometry["surfaces"][0]["equation_world"] = [0, 2, 0, 0]
    if mutation == "basis":
        geometry["orientation"]["basis_world_to_local"] = np.zeros((3, 3)).tolist()
    if mutation == "duplicate":
        geometry["surfaces"].append(geometry["surfaces"][0])
    with pytest.raises(ValueError):
        measure_geometry(geometry)


@pytest.mark.parametrize(
    "mutation",
    ["unit", "confidence", "interval", "reference", "duplicate", "physical", "status"],
)
def test_invalid_model_rejected(mutation):
    model = measure_geometry(exact_geometry())
    item = model["measurements"][0]
    if mutation == "unit":
        item["unit"] = "meters"
    if mutation == "confidence":
        item["uncertainty"]["confidence_level"] = 0.95
    if mutation == "interval":
        item["uncertainty"]["conditional_interval"] = [100, 1]
    if mutation == "reference":
        model["rooms"][0]["measurement_ids"] = [model["walls"][0]["measurement_ids"][0]]
    if mutation == "duplicate":
        model["measurements"].append(item)
    if mutation == "physical":
        item["uncertainty"]["physical_interval"] = [1, 2]
    if mutation == "status":
        item["status"] = "unavailable"
    with pytest.raises((ValueError, ValidationError)):
        validate_model(model)


def test_cli_repeat_and_no_input_overwrite(tmp_path):
    source, output = tmp_path / "input", tmp_path / "output"
    source.mkdir()
    (source / "geometry.json").write_text(json.dumps(exact_geometry()))
    command = [
        sys.executable,
        "scripts/measure_geometry.py",
        str(source),
        "--output",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True)
    artifact = output / "synthetic" / "measurements.json"
    first = artifact.read_bytes()
    subprocess.run(command, check=True, capture_output=True)
    assert artifact.read_bytes() == first
    result = subprocess.run(
        command[:-1] + [str(source / "nested")], capture_output=True
    )
    assert result.returncode != 0
    assert not (source / "nested").exists()


def test_batch_validation_preserves_previous_outputs(tmp_path):
    source, output = tmp_path / "input", tmp_path / "output"
    for name in ("a", "b"):
        directory = source / name
        directory.mkdir(parents=True)
        geometry = exact_geometry()
        geometry["capture_id"] = name
        if name == "b":
            geometry["walls"].pop()
        (directory / "geometry.json").write_text(json.dumps(geometry))
    prior = output / "a" / "measurements.json"
    prior.parent.mkdir(parents=True)
    prior.write_text("previous complete output")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/measure_geometry.py",
            str(source),
            "--output",
            str(output),
        ],
        capture_output=True,
    )
    assert result.returncode != 0
    assert prior.read_text() == "previous complete output"
    assert not (output / "b").exists()


def test_schema_evidence_and_room_reference_required():
    model = measure_geometry(exact_geometry())
    broken = deepcopy(model)
    broken["measurements"][0]["evidence"] = {}
    with pytest.raises(ValidationError):
        validate_model(broken)
    broken = deepcopy(model)
    boundary = next(
        wall for wall in broken["walls"] if wall["kind"] == "region_boundary"
    )
    boundary["room_id"] = None
    with pytest.raises(ValueError, match="room reference"):
        validate_model(broken)
