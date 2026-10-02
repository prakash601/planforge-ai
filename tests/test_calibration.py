import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from planforge.diagnostics.artifacts import export_scene
from planforge.diagnostics.calibration import (
    Hypothesis, backproject, camera_transform, candidate_hypotheses,
    compare_pair, depth_intrinsics, transform_points,
)
from planforge.ingestion import FrameRecord, LidarCapture


def frame(position=(0, 0, 0), frame_id="000000", path=Path("unused")):
    return FrameRecord(frame_id, float(int(frame_id)), position, (0, 0, 0, 1),
                       (240, 240, 128, 96), path / "depth.png", path / "confidence.png")


def tilted_plane(position):
    v, u = np.indices((96, 128))
    rays_x = (u - 64) / 120
    return np.rint((2 + 0.4 * position[0]) / (1 - 0.4 * rays_x) * 1000).astype(np.uint16)


def test_backprojection_uses_scaled_intrinsics_and_explicit_units():
    f = frame()
    hypothesis = Hypothesis()
    k = depth_intrinsics(f, (96, 128), (256, 192), hypothesis)
    np.testing.assert_allclose(k, [120, 120, 64, 48])
    cloud = backproject(np.full((96, 128), 2000, dtype=np.uint16), k, 0.001)
    np.testing.assert_allclose(cloud[48, 64], [0, 0, 2])
    np.testing.assert_allclose(cloud[48, 124], [1, 0, 2])
    np.testing.assert_allclose(transform_points(cloud[48, 64], f, hypothesis), [0, 0, -2])


def test_pose_inversion_includes_rotation_of_translation():
    q = (0, 0, np.sqrt(0.5), np.sqrt(0.5))
    f = FrameRecord("000000", 0, (1, 0, 0), q, (1, 1, 0, 0), Path("d"), Path("c"))
    rotation, translation = camera_transform(f, Hypothesis(camera_axes="opencv", pose_direction="world_to_camera"))
    np.testing.assert_allclose(translation, [0, 1, 0], atol=1e-12)
    np.testing.assert_allclose(rotation @ [1, 0, 0], [0, -1, 0], atol=1e-12)


def test_known_synthetic_motion_favors_correct_hypothesis():
    source_position, target_position = (0, 0, 0), (0.35, 0, 0)
    mask = np.full((96, 128), 2, dtype=np.uint8)
    source = (frame(source_position), tilted_plane(source_position), mask)
    target = (frame(target_position, "000001"), tilted_plane(target_position), mask)
    correct = compare_pair(source, target, (256, 192), Hypothesis())
    assert correct["relative_depth_median"] < 0.002
    assert correct["relative_plane_median"] < 0.002
    assert correct["overlap_fraction"] > 0.7
    for hypothesis in (
        Hypothesis(depth_scale=0.002), Hypothesis(intrinsics="as_recorded"),
        Hypothesis(pose_direction="world_to_camera"),
    ):
        assert compare_pair(source, target, (256, 192), hypothesis)["score"] > correct["score"]


def test_unsupported_depth_is_not_scored_as_a_good_match():
    mask = np.full((96, 128), 2, dtype=np.uint8)
    source = (frame(), tilted_plane((0, 0, 0)), mask)
    target = (frame((1, 0, 0)), np.zeros((96, 128), dtype=np.uint16), mask)
    result = compare_pair(source, target, (256, 192), Hypothesis())
    assert result["score"] == 1
    assert result["relative_plane_median"] is None
    assert not compare_pair(target, source, (256, 192), Hypothesis())["valid"]


@pytest.mark.parametrize("kwargs", [{"depth_scale": 0}, {"depth_scale": float("nan")},
    {"camera_axes": "guessed"}, {"pose_direction": "guessed"}, {"intrinsics": "guessed"}])
def test_invalid_hypotheses_rejected(kwargs):
    with pytest.raises(ValueError):
        Hypothesis(**kwargs)


def test_scene_exports_per_frame_provenance_and_standard_ply(tmp_path):
    root = tmp_path / "capture"
    root.mkdir()
    paths = []
    for index in range(2):
        path = root / str(index)
        path.mkdir()
        Image.fromarray(tilted_plane((index * 0.1, 0, 0))).save(path / "depth.png")
        Image.fromarray(np.full((96, 128), 2, dtype=np.uint8)).save(path / "confidence.png")
        paths.append(frame((index * 0.1, 0, 0), f"{index:06}", path))
    capture = LidarCapture(root, tuple(paths), ((1,0,0),(0,1,0),(0,0,1)), (), root / "rgb.mp4")
    result = export_scene(capture, (256, 192), Hypothesis(), tmp_path / "output", frames=2, frame_step=1)
    data = json.loads((tmp_path / "output/scene.json").read_text())
    assert result["frames"] == 2
    assert data["scale_status"] == "unverified"
    assert set(data["frame_indices"]) == {0, 1}
    assert len(data["points"]) == 3 * data["point_count"]
    assert data["trajectory"] == [[0, 0, 0], [0.1, 0, 0]]
    content = (tmp_path / "output/cloud.ply").read_bytes()
    header, binary = content.split(b"end_header\n", 1)
    assert b"format binary_little_endian 1.0" in header
    assert len(binary) == data["point_count"] * 17
    with pytest.raises(ValueError, match="outside the raw"):
        export_scene(capture, (256, 192), Hypothesis(), root / "output")


def test_hypothesis_grid_preserves_distinct_candidates():
    candidates = candidate_hypotheses()
    assert len(candidates) == 40
    assert len({candidate.key for candidate in candidates}) == 40
