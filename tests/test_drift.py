"""Loop-closure drift correction: detection, correction, and metrics."""

import numpy as np
import pytest

from planforge.drift import (
    DriftConfig,
    analyze_trajectory,
    apply_correction,
    cloud_distance,
    correct_frames,
    estimate_correction,
    overlap_residual,
)


def loop_trajectory(n=100, radius=2.0, drift=0.3):
    angle = np.linspace(0, 2 * np.pi, n)
    path = np.stack([radius * np.cos(angle), np.zeros(n), radius * np.sin(angle)], axis=1)
    path += np.linspace(0, drift, n)[:, None] * np.array([1.0, 0, 0])
    return path


def test_loop_detected_and_closure_removed():
    path = loop_trajectory()
    config = DriftConfig(loop_window=1)
    analysis = analyze_trajectory(path, config)
    assert analysis["loop_detected"]
    assert analysis["closure_distance_pose_units"] == pytest.approx(0.3, abs=0.05)
    offsets, provenance = estimate_correction(path, config)
    assert provenance["max_offset_pose_units"] == pytest.approx(0.3, abs=0.05)
    corrected = path + offsets
    after = analyze_trajectory(corrected, config)
    assert after["closure_distance_pose_units"] < 1e-9
    # Deterministic repeat.
    again, _ = estimate_correction(path, config)
    assert np.array_equal(offsets, again)


def test_open_trajectory_yields_exact_zero_correction():
    path = np.stack([np.linspace(0, 5, 50), np.zeros(50), np.zeros(50)], axis=1)
    analysis = analyze_trajectory(path)
    assert not analysis["loop_detected"]
    offsets, provenance = estimate_correction(path)
    assert np.array_equal(offsets, np.zeros_like(path))
    assert provenance["max_offset_pose_units"] == 0.0


def test_short_path_never_claims_loop():
    path = np.array([[0.0, 0, 0], [0.01, 0, 0]])
    assert not analyze_trajectory(path)["loop_detected"]


def test_rejects_invalid_trajectories():
    with pytest.raises(ValueError, match="at least 2"):
        analyze_trajectory([[0.0, 0, 0]])
    with pytest.raises(ValueError, match="finite"):
        analyze_trajectory([[0.0, 0, np.nan], [1.0, 0, 0]])
    with pytest.raises(ValueError, match="positive integer"):
        DriftConfig(loop_window=0)
    with pytest.raises(ValueError, match="between 0 and 1"):
        DriftConfig(loop_ratio_threshold=2.0)


def test_correct_frames_preserves_identity_and_shifts_positions():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class FakeFrame:
        frame_id: str
        position: tuple
        quaternion_xyzw: tuple = (0, 0, 0, 1)

    frames = [FakeFrame(f"{i}", (float(i), 0.0, 0.0)) for i in range(4)]
    offsets = np.array([[0, 0, 0], [0, 0.1, 0], [0, 0.2, 0], [0, 0.3, 0]])
    corrected = correct_frames(frames, offsets)
    assert [f.frame_id for f in corrected] == ["0", "1", "2", "3"]
    assert corrected[3].position == pytest.approx((3.0, 0.3, 0.0))
    assert corrected[0].quaternion_xyzw == (0, 0, 0, 1)
    with pytest.raises(ValueError, match="matching the frame count"):
        correct_frames(frames, offsets[:2])
    with pytest.raises(ValueError, match="finite"):
        correct_frames(frames, np.full((4, 3), np.inf))


def test_cloud_distance_zero_for_identical_shifted_for_offset():
    rng = np.random.default_rng(7)
    cloud = rng.normal(size=(500, 3))
    assert cloud_distance(cloud, cloud.copy())["median_pose_units"] == 0.0
    shifted = cloud + np.array([0.25, 0, 0])
    result = cloud_distance(cloud, shifted)
    assert result["median_pose_units"] == pytest.approx(0.25, abs=0.05)
    with pytest.raises(ValueError, match="nonempty"):
        cloud_distance(np.zeros((0, 3)), cloud)


def test_overlap_residual_finite_and_sensitive_to_shift():
    rng = np.random.default_rng(11)
    base = rng.normal(size=(400, 3))
    points = np.vstack([base, base + np.array([0.02, 0, 0])])
    indices = np.array([0] * 400 + [100] * 400)
    tight = overlap_residual(points, indices)
    assert tight["median_pose_units"] < 0.05
    spread = overlap_residual(np.vstack([base, base + np.array([1.0, 0, 0])]), indices)
    assert spread["median_pose_units"] > tight["median_pose_units"]
    with pytest.raises(ValueError, match="both trajectory halves"):
        overlap_residual(base, np.zeros(len(base), dtype=int))


def test_apply_correction_shifts_by_supporting_frame():
    points = np.array([[0.0, 0, 0], [1.0, 0, 0], [2.0, 0, 0]])
    indices = np.array([0, 1, 2])
    offsets = np.array([[0, 0, 0], [0, 1, 0], [0, 2, 0], [0, 3, 0]])
    moved = apply_correction(points, indices, offsets)
    assert moved.tolist() == [[0.0, 0, 0], [1.0, 1, 0], [2.0, 2, 0]]
    with pytest.raises(ValueError, match="exceed the correction length"):
        apply_correction(points, np.array([0, 1, 99]), offsets)
