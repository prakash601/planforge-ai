import json

import numpy as np
import pytest
from PIL import Image

from planforge.diagnostics.calibration import Hypothesis, backproject
from planforge.ingestion import FrameRecord, LidarCapture
from planforge.reconstruction import ReconstructionConfig, reconstruct
from planforge.reconstruction.scene import statistical_inliers


def capture_fixture(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    frames = []
    for index in range(3):
        depth = np.full((8, 8), 2000, dtype=np.uint16)
        depth[0, 0] = 0
        mask = np.full((8, 8), 2, dtype=np.uint8)
        mask[0, 1] = 0
        d, c = root / f"d{index}.png", root / f"c{index}.png"
        Image.fromarray(depth).save(d)
        Image.fromarray(mask).save(c)
        frames.append(FrameRecord(f"{index:06}", index, (0, 0, 0), (0, 0, 0, 1), (8, 8, 4, 4), d, c))
    return LidarCapture(root, tuple(frames), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (), root / "rgb.mp4")


def test_stream_fusion_provenance_and_repeatability(tmp_path):
    capture = capture_fixture(tmp_path)
    config = ReconstructionConfig(pixel_stride=1, voxel_size=0.1)
    hypothesis = Hypothesis(camera_axes="opencv")
    scene = reconstruct(capture, (8, 8), hypothesis, tmp_path / "out", config)
    assert scene.diagnostics["raw_points"] == 189
    assert scene.diagnostics["invalid_depth"] == 3
    assert scene.diagnostics["confidence_rejected"] == 3
    assert scene.diagnostics["voxels_before_outlier"] == 62
    assert np.all(scene.observation_counts == 3)
    assert np.all(scene.frame_indices == 0)
    assert scene.provenance["scale_status"] == "unverified"
    assert scene.provenance["pose_correction"].startswith("none")
    second = reconstruct(capture, (8, 8), hypothesis, tmp_path / "again", config)
    np.testing.assert_array_equal(scene.points, second.points)
    assert scene.diagnostics == second.diagnostics
    assert (tmp_path / "out/cloud.ply").read_bytes() == (tmp_path / "again/cloud.ply").read_bytes()
    raw = (tmp_path / "out/raw.ply").read_bytes()
    header, binary = raw.split(b"end_header\n", 1)
    assert b"element vertex 00000000000000000189" in header
    assert len(binary) == 189 * 17
    arrays = np.load(tmp_path / "out/cloud.npz")
    np.testing.assert_array_equal(arrays["points"], scene.points)
    metadata = json.loads((tmp_path / "out/spatial_scene.json").read_text())
    assert metadata["frames"][2]["source_index"] == 2


def test_cap_and_raw_write_guard(tmp_path):
    capture = capture_fixture(tmp_path)
    with pytest.raises(ValueError, match="max_voxels"):
        reconstruct(capture, (8, 8), Hypothesis(), tmp_path / "out", ReconstructionConfig(pixel_stride=1, max_voxels=1))
    assert not (tmp_path / "out/raw.partial.ply").exists()
    assert not (tmp_path / "out/spatial_scene.json").exists()
    with pytest.raises(ValueError, match="outside the raw"):
        reconstruct(capture, (8, 8), Hypothesis(), capture.path / "out")


def test_frame_sampling_and_bounded_preview(tmp_path):
    capture = capture_fixture(tmp_path)
    config = ReconstructionConfig(frame_step=2, pixel_stride=1, preview_points=5)
    scene = reconstruct(capture, (8, 8), Hypothesis(), tmp_path / "out", config)
    assert [frame["source_index"] for frame in scene.frames] == [0, 2]
    preview = json.loads((tmp_path / "out/scene.json").read_text())
    assert len(preview["points"]) == 15
    assert preview["full_point_count"] == len(scene.points)
    raw = json.loads((tmp_path / "out/raw_scene.json").read_text())
    assert raw["point_count"] == 5
    assert scene.provenance["selected_depth_pose_sha256"]


def test_failed_rerun_preserves_previous_artifacts(tmp_path):
    capture = capture_fixture(tmp_path)
    output = tmp_path / "out"
    reconstruct(capture, (8, 8), Hypothesis(), output)
    previous = (output / "spatial_scene.json").read_bytes()
    with pytest.raises(ValueError, match="max_voxels"):
        reconstruct(capture, (8, 8), Hypothesis(), output, ReconstructionConfig(max_voxels=1))
    assert (output / "spatial_scene.json").read_bytes() == previous
    assert not list(tmp_path.glob(".reconstruction-*"))


def test_no_supported_observations(tmp_path):
    capture = capture_fixture(tmp_path)
    for frame in capture.frames:
        Image.fromarray(np.zeros((8, 8), dtype=np.uint8)).save(frame.confidence_path)
    with pytest.raises(ValueError, match="no supported"):
        reconstruct(capture, (8, 8), Hypothesis(), tmp_path / "out")


def test_statistical_filter_rejects_isolated_point():
    points = np.column_stack((np.arange(100) * 0.01, np.zeros(100), np.zeros(100)))
    keep, threshold = statistical_inliers(np.vstack((points, [20, 20, 20])), 8, 2)
    assert not keep[-1]
    assert keep[:100].all()
    assert threshold > 0
    assert statistical_inliers(points[:2], 8, 2)[0].all()


def test_centroids_weight_observations_not_frame_centroids(tmp_path):
    capture = capture_fixture(tmp_path)
    reference = []
    for index, frame in enumerate(capture.frames):
        depth = frame.read_depth()
        depth[depth > 0] += index * 10
        Image.fromarray(depth).save(frame.depth_path)
        mask = frame.read_confidence()
        if index == 1:
            mask[:, :4] = 0
            Image.fromarray(mask).save(frame.confidence_path)
        reference.append(backproject(depth, (8, 8, 4, 4), 0.001)[(depth > 0) & (mask == 2)])
    points = np.concatenate(reference)
    keys, inverse, counts = np.unique(np.floor(points / 0.5).astype(int), axis=0, return_inverse=True, return_counts=True)
    sums = np.zeros((len(keys), 3))
    np.add.at(sums, inverse, points)
    scene = reconstruct(capture, (8, 8), Hypothesis(camera_axes="opencv"), tmp_path / "out",
                        ReconstructionConfig(pixel_stride=1, voxel_size=0.5, outlier_std_ratio=100))
    np.testing.assert_allclose(scene.points, sums / counts[:, None], atol=1e-6)
    np.testing.assert_array_equal(scene.observation_counts, counts)


def test_unknown_confidence_label_rejected(tmp_path):
    capture = capture_fixture(tmp_path)
    Image.fromarray(np.full((8, 8), 3, dtype=np.uint8)).save(capture.frames[-1].confidence_path)
    with pytest.raises(ValueError, match="invalid depth/confidence"):
        reconstruct(capture, (8, 8), Hypothesis(), tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("kwargs", [{"frame_step": 0}, {"pixel_stride": 1.5}, {"voxel_size": 0},
    {"voxel_size": float("nan")}, {"min_confidence": 3}, {"max_voxels": -1},
    {"outlier_neighbors": 0}, {"outlier_std_ratio": -1}, {"preview_points": 0}])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        ReconstructionConfig(**kwargs)
