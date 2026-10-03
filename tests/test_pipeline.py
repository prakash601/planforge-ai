import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_reconstruction import capture_fixture

from planforge.diagnostics.calibration import Hypothesis
from planforge.pipeline import run_capture
from planforge.reconstruction import ReconstructionConfig


def setup_capture(tmp_path, monkeypatch):
    capture = capture_fixture(tmp_path)
    monkeypatch.setattr(
        "planforge.pipeline.LidarCaptureLoader.load", lambda self, path: capture
    )
    monkeypatch.setattr("planforge.pipeline.rgb_metadata", lambda path: (8, 8))
    calibration = tmp_path / "calibration.json"
    calibration.write_text(json.dumps(Hypothesis(camera_axes="opencv").to_dict()))
    return capture, calibration


def test_small_pipeline_artifacts_and_run_record(tmp_path, monkeypatch):
    capture, calibration = setup_capture(tmp_path, monkeypatch)
    output = tmp_path / "result"
    record = run_capture(
        capture.path, output, calibration, ReconstructionConfig(pixel_stride=1)
    )
    assert record["status"] == "complete"
    for name in (
        "run.json",
        "measurements.json",
        "index.html",
        "plan.svg",
        "plan.png",
        "debug/geometry.json",
        "debug/reconstruction/raw.ply",
        "debug/reconstruction/cloud.npz",
        "debug/reconstruction/spatial_scene.json",
    ):
        assert (output / name).is_file()
    assert record["configuration"]["reconstruction"]["pixel_stride"] == 1
    assert record["source_depth_pose_sha256"]
    assert record["timings_seconds"]["total_compute"] >= sum(
        value
        for name, value in record["timings_seconds"].items()
        if name != "total_compute"
    )
    before = (output / "plan.svg").read_bytes()
    run_capture(capture.path, output, calibration, ReconstructionConfig(pixel_stride=1))
    assert before == (output / "plan.svg").read_bytes()
    assert not list(tmp_path.glob(".planforge-*"))


@pytest.mark.parametrize(
    "stage",
    [
        "reconstruction",
        "extract_geometry",
        "measure_geometry",
        "detect_openings",
        "attach_openings",
        "render_plan",
    ],
)
def test_failed_rerun_preserves_entire_previous_run(tmp_path, monkeypatch, stage):
    capture, calibration = setup_capture(tmp_path, monkeypatch)
    output = tmp_path / "result"
    run_capture(capture.path, output, calibration)
    before = {
        path.relative_to(output): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }
    name = "reconstruct" if stage == "reconstruction" else stage

    def fail(*args, **kwargs):
        raise ValueError("test stage failed")

    monkeypatch.setattr(f"planforge.pipeline.{name}", fail)
    with pytest.raises(ValueError, match="test stage failed"):
        run_capture(capture.path, output, calibration)
    assert before == {
        path.relative_to(output): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }
    assert not list(tmp_path.glob(".planforge-*"))


def test_protect_input_and_unrelated_output(tmp_path, monkeypatch):
    capture, calibration = setup_capture(tmp_path, monkeypatch)
    for output in (capture.path, capture.path / "nested", tmp_path):
        with pytest.raises(ValueError, match="separate"):
            run_capture(capture.path, output, calibration)
    output = tmp_path / "unrelated"
    output.mkdir()
    (output / "user.txt").write_text("keep")
    with pytest.raises(ValueError, match="refusing"):
        run_capture(capture.path, output, calibration)
    assert (output / "user.txt").read_text() == "keep"


def test_publication_failure_rolls_back_previous_run(tmp_path, monkeypatch):
    capture, calibration = setup_capture(tmp_path, monkeypatch)
    output = tmp_path / "result"
    run_capture(capture.path, output, calibration)
    before = (output / "run.json").read_bytes()
    rename = Path.rename

    def fail_publication(path, target):
        if path.name == "complete":
            raise OSError("publication failed")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_publication)
    with pytest.raises(OSError, match="publication failed"):
        run_capture(capture.path, output, calibration)
    assert (output / "run.json").read_bytes() == before
    assert (output / "plan.png").is_file()
    assert not list(tmp_path.glob(".planforge-*"))


def test_cli_requires_explicit_calibration_and_rejects_bad_input(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "planforge.cli",
            "run",
            "--input",
            str(tmp_path),
            "--output",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0 and b"--calibration" in result.stderr
    calibration = tmp_path / "calibration.json"
    calibration.write_text(json.dumps(Hypothesis().to_dict()))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "planforge.cli",
            "run",
            "--input",
            str(tmp_path),
            "--output",
            str(tmp_path.parent / "invalid-out"),
            "--calibration",
            str(calibration),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0 and b"PlanForge run failed" in result.stderr
