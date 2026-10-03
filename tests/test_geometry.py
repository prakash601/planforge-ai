from dataclasses import replace

import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from shapely import Point, Polygon

from planforge.geometry import GeometryConfig, extract_geometry, load_scene
from planforge.geometry.rooms import build_regions
from planforge.reconstruction import SpatialScene


def synthetic_room(outline=((0, 0), (4, 0), (4, 3), (0, 3)), ceiling=True, missing_wall=None):
    polygon = Polygon(outline)
    grid = np.array([(x, z) for x in np.arange(0.05, 4.01, 0.12) for z in np.arange(0.05, 3.01, 0.12) if polygon.contains(Point(x, z))])
    points = [np.column_stack((grid[:, 0], np.zeros(len(grid)), grid[:, 1]))]
    if ceiling:
        points.append(np.column_stack((grid[:, 0], np.full(len(grid), 2.8), grid[:, 1])))
    for index, (left, right) in enumerate(zip(outline, (*outline[1:], outline[0]))):
        if index == missing_wall:
            continue
        left, right = np.array(left), np.array(right)
        t = np.linspace(0, 1, int(np.linalg.norm(right - left) / 0.12) + 1)
        horizontal = left + t[:, None] * (right - left)
        points.append(np.array([[x, y, z] for x, z in horizontal for y in np.arange(0, 2.81, 0.12)]))
    points = np.concatenate(points)
    points += np.random.default_rng(4).normal(0, 0.002, points.shape)
    trajectory = np.array([[0.8, 1.4, 0.8], [1.4, 1.42, 1], [2.5, 1.38, 1.6], [1.8, 1.4, 2]])
    return SpatialScene("synthetic", points, np.full(len(points), 2), np.zeros(len(points), int),
                        np.ones(len(points), int), trajectory, (), {"scale_status": "unverified"}, {})


def test_room_surface_roles_and_supported_polygon():
    geometry = extract_geometry(synthetic_room(), up_vector=(0, 1, 0))
    roles = [plane["role"] for plane in geometry.surfaces]
    assert roles.count("floor_candidate") == 1
    assert roles.count("ceiling_candidate") == 1
    assert roles.count("wall_candidate") == 4
    assert len(geometry.regions) == 1
    polygon = Polygon(geometry.regions[0]["polygon"])
    assert polygon.is_valid
    assert polygon.area == pytest.approx(12, abs=0.15)
    assert all(edge["surface_ids"] for edge in geometry.regions[0]["edge_evidence"])
    assert geometry.orientation["status"] == "explicit_unverified"
    assert "scale_unverified" in geometry.flags


def test_missing_ceiling_and_wall_are_not_invented():
    geometry = extract_geometry(synthetic_room(ceiling=False, missing_wall=1))
    assert "ceiling_unobserved" in geometry.flags
    assert "no_supported_closed_boundary" in geometry.flags
    assert not geometry.regions


def test_rotated_non_rectangular_room():
    outline = ((0, 0), (4, 0), (4, 1.4), (2, 1.4), (2, 3), (0, 3))
    scene = synthetic_room(outline)
    rotation = Rotation.from_euler("xyz", [22, 31, -17], degrees=True).as_matrix()
    translation = np.array([8, -3, 4])
    scene = replace(scene, points=scene.points @ rotation.T + translation,
                    trajectory=scene.trajectory @ rotation.T + translation)
    geometry = extract_geometry(scene, up_vector=rotation[:, 1])
    assert np.dot(geometry.orientation["up_world"], rotation[:, 1]) > 0.98
    assert len(geometry.regions) == 1
    assert Polygon(geometry.regions[0]["polygon"]).area == pytest.approx(8.8, abs=0.2)
    assert len(geometry.regions[0]["polygon"]) >= 7


def test_small_furniture_is_not_a_wall():
    scene = synthetic_room()
    furniture = np.array([[x, y, 1.5] for x in np.arange(1, 1.6, 0.035) for y in np.arange(0, 0.8, 0.035)])
    geometry = extract_geometry(replace(scene, points=np.vstack((scene.points, furniture))), up_vector=(0, 1, 0))
    assert len(geometry.walls) == 4
    assert any(plane["role"] == "vertical_small_or_unsupported" for plane in geometry.surfaces)


def test_no_floor_evidence_reports_unresolved_orientation():
    rng = np.random.default_rng(42)
    scene = synthetic_room()
    geometry = extract_geometry(replace(scene, points=rng.normal(size=(100, 3))))
    assert geometry.orientation["status"] == "unresolved"
    assert "floor_unobserved" in geometry.flags
    assert not geometry.regions


def test_symmetric_floor_ceiling_sign_is_ambiguous():
    geometry = extract_geometry(synthetic_room())
    assert geometry.orientation["status"] == "ambiguous"
    assert "orientation_ambiguous" in geometry.flags
    assert not geometry.regions


def test_non_orthogonal_room_without_manhattan_prior():
    outline = ((0, 0), (4, 0), (3.3, 3), (0.6, 3))
    geometry = extract_geometry(synthetic_room(outline), up_vector=(0, 1, 0))
    assert len(geometry.regions) == 1
    assert Polygon(geometry.regions[0]["polygon"]).area == pytest.approx(10.05, abs=0.15)


def wall(a, b):
    a, b = np.array(a, float), np.array(b, float)
    tangent = (b - a) / np.linalg.norm(b - a)
    normal = np.array([tangent[1], -tangent[0]])
    return {"normal": normal.tolist(), "offset": float(a @ normal), "tangent": tangent.tolist(),
            "interval": [float(a @ tangent), float(b @ tangent)], "endpoints": [a.tolist(), b.tolist()]}


def test_disconnected_rooms_and_unvisited_region():
    outlines = [((0, 0), (3, 0), (3, 3), (0, 3)), ((5, 0), (8, 0), (8, 3), (5, 3))]
    walls = [wall(a, b) for outline in outlines for a, b in zip(outline, (*outline[1:], outline[0]))]
    floor = np.array([[x, z] for x in np.arange(0.1, 8, 0.1) for z in np.arange(0.1, 3, 0.1)])
    regions, diagnostics = build_regions(walls, floor, np.array([[1, 1], [6, 1]]), GeometryConfig())
    assert len(regions) == 2
    assert diagnostics["invalid_rings"] == 0
    regions, diagnostics = build_regions(walls, floor, np.array([[1, 1]]), GeometryConfig())
    assert len(regions) == 1
    assert len(diagnostics["rejected_regions"]) == 1


def test_large_junction_gap_is_not_closed():
    walls = [wall((0, 0), (3, 0)), wall((3, 0.8), (3, 3)), wall((3, 3), (0, 3)), wall((0, 3), (0, 0))]
    regions, diagnostics = build_regions(walls, np.array([[1, 1]] * 30), np.array([[1, 1]]), GeometryConfig())
    assert not regions
    assert diagnostics["dangling_edges"] > 0


def test_scene_contract_load_and_invalid_frame_indices(tmp_path):
    from planforge.diagnostics.artifacts import write_json
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1]], dtype=np.float32)
    write_json(tmp_path / "spatial_scene.json", {"schema_version": 1, "capture_id": "test",
               "scale_status": "unverified", "trajectory": [[0, 1, 0]], "frames": [{"id": "000000"}], "diagnostics": {}})
    values = dict(points=points, confidence=np.full(3, 2, dtype=np.uint8), frame_indices=np.zeros(3, int), observation_counts=np.ones(3, int))
    np.savez(tmp_path / "cloud.npz", **values)
    scene = load_scene(tmp_path)
    np.testing.assert_array_equal(scene.points, points)
    values["frame_indices"] = np.full(3, 2, int)
    np.savez(tmp_path / "cloud.npz", **values)
    with pytest.raises(ValueError, match="frame provenance"):
        load_scene(tmp_path)


def test_coplanar_wall_fragments_merge_and_gap_stays_open():
    scene = synthetic_room(ceiling=False)
    mask = ~((np.abs(scene.points[:, 2]) < 0.02) & (scene.points[:, 0] > 1.4) & (scene.points[:, 0] < 2.5) & (scene.points[:, 1] > 0.05))
    geometry = extract_geometry(replace(scene, points=scene.points[mask]), up_vector=(0, 1, 0))
    roles = [surface["role"] for surface in geometry.surfaces]
    assert roles.count("wall_candidate") == 4
    assert len(geometry.walls) >= 5
    assert not geometry.regions


def test_bad_up_vector_rejected():
    with pytest.raises(ValueError, match="up_vector"):
        extract_geometry(synthetic_room(), up_vector=(0, 0, 0))


@pytest.mark.parametrize("kwargs", [{"plane_distance": 0}, {"sample_points": 1}, {"max_planes": 0},
    {"seed": -1}, {"merge_angle_degrees": 90}, {"junction_tolerance": float("nan")}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        GeometryConfig(**kwargs)
