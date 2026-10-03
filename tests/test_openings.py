from copy import deepcopy

import numpy as np
import pytest
from jsonschema import ValidationError
from test_measurements import exact_geometry

from planforge.measurements import measure_geometry, validate_model
from planforge.openings import OpeningConfig, attach_openings, detect_openings
from planforge.openings.evaluation import score_openings
from planforge.reconstruction import SpatialScene


def opening_fixture(kind="door", rays=True, frames=2, edge=False, header=True):
    geometry = exact_geometry()
    geometry["regions"] = []
    lo, hi = (0, 0.8) if edge else (1.2, 2.0)
    bottom, top = (0, 2) if kind == "door" else (0.8, 1.6)
    cloud = np.array(
        [
            [x, y, 0]
            for x in np.arange(0.05, 4, 0.1)
            for y in np.arange(0.05, 2.8, 0.1)
            if not (lo < x < hi and bottom < y < (top if header else 3))
        ]
    )
    indices = np.zeros(len(cloud), int)
    if rays:
        hits = np.array(
            [
                [x, y, -1]
                for x in np.arange(lo + 0.15, hi - 0.1, 0.1)
                for y in np.arange(bottom + 0.15, top - 0.1, 0.1)
            ]
        )
        cloud = np.vstack((cloud, hits))
        indices = np.r_[indices, np.arange(len(hits)) % frames]
    if kind == "door":
        wall = geometry["walls"].pop(0)
        geometry["walls"].extend(
            [
                {
                    **wall,
                    "endpoints": [[0, 0], [lo, 0]],
                    "junction_endpoints": [[0, 0], [lo, 0]],
                },
                {
                    **wall,
                    "endpoints": [[hi, 0], [4, 0]],
                    "junction_endpoints": [[hi, 0], [4, 0]],
                },
            ]
        )
    trajectory = np.array([[1.6, 1.4, 1] for _ in range(frames)])
    scene = SpatialScene(
        "synthetic",
        cloud,
        np.full(len(cloud), 2),
        indices,
        np.ones(len(cloud), int),
        trajectory,
        (),
        {},
        {},
    )
    return scene, geometry


@pytest.mark.parametrize(
    "kind,association", [("door", "adjacent_support"), ("window", "contained")]
)
def test_annotated_opening_width_and_wall_association(kind, association):
    scene, geometry = opening_fixture(kind)
    detection = detect_openings(scene, geometry)
    assert len(detection["candidates"]) == 1
    model = attach_openings(measure_geometry(geometry), detection)
    assert model["schema_version"] == "1.1.0"
    assert len(model["openings"]) == 1
    opening = model["openings"][0]
    assert opening["kind"] == kind and opening["association"] == association
    assert opening["evidence"]["supporting_frames"] == 2
    width = next(
        item for item in model["measurements"] if item["kind"] == "opening_width"
    )
    assert width["value"] == pytest.approx(0.8, abs=0.11)
    assert width["uncertainty"]["physical_interval"] is None


@pytest.mark.parametrize("kwargs", [{"rays": False}, {"frames": 1}])
def test_coverage_gap_not_opening_without_sight_line_evidence(kwargs):
    scene, geometry = opening_fixture(**kwargs)
    detection = detect_openings(scene, geometry)
    assert not detection["candidates"]
    assert detection["unresolved_gaps"]


@pytest.mark.parametrize("kwargs", [{"header": False}, {"edge": True}])
def test_missing_header_or_jamb_not_an_opening(kwargs):
    scene, geometry = opening_fixture(**kwargs)
    assert not detect_openings(scene, geometry)["candidates"]


def test_occluding_points_do_not_count_as_through_plane_rays():
    scene, geometry = opening_fixture()
    scene.points[scene.points[:, 2] < 0, 2] = 0.5
    assert not detect_openings(scene, geometry)["candidates"]


def test_solid_wall_has_no_phantom_opening():
    scene, geometry = opening_fixture("window", rays=False)
    fill = np.array(
        [[x, y, 0] for x in np.arange(1.25, 2, 0.1) for y in np.arange(0.85, 1.6, 0.1)]
    )
    from dataclasses import replace

    scene = replace(
        scene,
        points=np.vstack((scene.points, fill)),
        confidence=np.full(len(scene.points) + len(fill), 2),
        frame_indices=np.zeros(len(scene.points) + len(fill), int),
    )
    assert not detect_openings(scene, geometry)["candidates"]


def test_orientation_ambiguity_and_source_mismatch():
    scene, geometry = opening_fixture()
    geometry["orientation"]["status"] = "ambiguous"
    assert (
        detect_openings(scene, geometry)["diagnostics"]["status"]
        == "orientation_unresolved"
    )
    geometry["capture_id"] = "different"
    with pytest.raises(ValueError, match="capture IDs"):
        detect_openings(scene, geometry)


def test_ids_repeat_and_wrong_references_rejected():
    scene, geometry = opening_fixture()
    detection = detect_openings(scene, geometry)
    model = attach_openings(measure_geometry(geometry), detection)
    assert model == attach_openings(
        measure_geometry(geometry), detect_openings(scene, geometry)
    )
    bad = deepcopy(model)
    bad["openings"][0]["wall_id"] = "wall-" + "0" * 20
    with pytest.raises(ValueError):
        validate_model(bad)
    bad = deepcopy(model)
    bad["measurements"][-1]["unit"] = "meters"
    with pytest.raises(ValidationError):
        validate_model(bad)
    bad = deepcopy(detection)
    bad["provenance"]["geometry_sha256"] = "wrong"
    with pytest.raises(ValueError, match="hash mismatch"):
        attach_openings(measure_geometry(geometry), bad)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cell_size": 0},
        {"max_cells": 0},
        {"min_frames": 0},
        {"border_support": 2},
        {"min_width": 4},
        {"min_rays": 1.5},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        OpeningConfig(**kwargs)


def test_annotation_scoring_includes_misses_phantoms_and_width_failures():
    annotation = {
        "surface_id": "wall",
        "kind": "door",
        "interval": [1, 2],
        "height_interval": [0, 2],
    }
    missing = score_openings([], [annotation], 0.1)
    assert (
        missing["misses"] == 1
        and missing["pass_fraction_including_misses_and_phantoms"] == 0
    )
    duplicate = score_openings([annotation, annotation], [annotation], 0.1)
    assert duplicate["matched"] == 1 and duplicate["phantoms"] == 1
    assert duplicate["pass_fraction_including_misses_and_phantoms"] == 0.5
    oversized = {**annotation, "interval": [0.8, 2.2]}
    wrong = score_openings([oversized], [annotation], 0.1)
    assert wrong["matched"] == 1 and not wrong["matches"][0]["passes"]
    assert wrong["pass_fraction_including_misses_and_phantoms"] == 0
    wrong_class = score_openings([{**annotation, "kind": "window"}], [annotation], 0.1)
    assert not wrong_class["matches"][0]["class_matches"]
    assert (
        score_openings([], [], 0.1)["pass_fraction_including_misses_and_phantoms"]
        is None
    )


def test_opening_render_and_annotation_fixture_artifacts(tmp_path):
    import json
    import xml.etree.ElementTree as ET

    from planforge.rendering import render_plan

    scene, geometry = opening_fixture()
    detection = detect_openings(scene, geometry)
    model = attach_openings(measure_geometry(geometry), detection)
    artifacts = render_plan(model, tmp_path)
    assert len(artifacts["displayed_opening_ids"]) == 1
    text = " ".join(ET.parse(tmp_path / "plan.svg").getroot().itertext())
    assert "door candidate" in text and "class unverified" in text
    annotation = {
        "surface_id": "surface-0",
        "kind": "door",
        "interval": [1.2, 2],
        "height_interval": [0, 2],
    }
    evaluation = score_openings(detection["candidates"], [annotation], 0.11)
    assert (
        evaluation["matched"] == 1
        and evaluation["pass_fraction_including_misses_and_phantoms"] == 1
    )
    (tmp_path / "annotations.json").write_text(json.dumps([annotation]))


def test_bounded_grid_and_invalid_frame_provenance():
    scene, geometry = opening_fixture()
    result = detect_openings(scene, geometry, OpeningConfig(max_cells=10))
    assert not result["candidates"]
    assert result["diagnostics"]["skipped_surfaces"]
    scene.frame_indices[0] = 9
    with pytest.raises(ValueError, match="frame provenance"):
        detect_openings(scene, geometry)


def test_rotated_translated_opening_frame():
    from dataclasses import replace

    from scipy.spatial.transform import Rotation

    scene, geometry = opening_fixture("window")
    rotation = Rotation.from_euler("xyz", [24, 37, -11], degrees=True).as_matrix()
    translation = np.array([4, -2, 7])
    scene = replace(
        scene,
        points=scene.points @ rotation.T + translation,
        trajectory=scene.trajectory @ rotation.T + translation,
    )
    geometry["orientation"]["basis_world_to_local"] = rotation.T.tolist()
    geometry["orientation"]["origin_world"] = translation.tolist()
    for surface in geometry["surfaces"]:
        eq = np.array(surface["equation_world"])
        normal = rotation @ eq[:3]
        surface["equation_world"] = [*normal, float(eq[3] - normal @ translation)]
    candidates = detect_openings(scene, geometry)["candidates"]
    assert len(candidates) == 1 and candidates[0]["kind"] == "window"
    assert candidates[0]["width_pose_units"] == pytest.approx(0.8, abs=0.11)


def test_low_confidence_sight_lines_and_source_hash_mismatch():
    scene, geometry = opening_fixture()
    scene.confidence[scene.points[:, 2] < 0] = 0
    assert not detect_openings(scene, geometry)["candidates"]
    scene.provenance["selected_depth_pose_sha256"] = "different"
    with pytest.raises(ValueError, match="source hashes"):
        detect_openings(scene, geometry)
