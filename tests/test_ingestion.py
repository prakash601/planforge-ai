import csv
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from planforge.ingestion import CaptureError, LidarCaptureLoader
from planforge.ingestion.inspection import inspect_capture, inspect_rgb


@pytest.fixture
def capture(tmp_path):
    path = tmp_path / "capture"
    (path / "depth").mkdir(parents=True)
    (path / "confidence").mkdir()
    for index in range(3):
        Image.fromarray(np.full((6, 8), 1000 + index, dtype=np.uint16)).save(path / "depth" / f"{index:06}.png")
        Image.fromarray(np.full((6, 8), 2, dtype=np.uint8)).save(path / "confidence" / f"{index:06}.png")
    with (path / "odometry.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["timestamp", "frame", "x", "y", "z", "qx", "qy", "qz", "qw", "fx", "fy", "cx", "cy", "distortion_center_x", "distortion_center_y"])
        for index in range(3):
            writer.writerow([index / 30, f"{index:06}", index, 0, 0, 0, 0, 0, 1, 40, 40, 16, 12, "", ""])
    (path / "imu.csv").write_text("timestamp, a_x, a_y, a_z, alpha_x, alpha_y, alpha_z\n0, 0, 0, 1, 0, 0, 0\n0.01, 0, 0, 1, 0, 0, 0\n")
    (path / "camera_matrix.csv").write_text("40,0,16\n0,40,12\n0,0,1\n")
    video = cv2.VideoWriter(str(path / "rgb.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (32, 24))
    assert video.isOpened()
    for index in range(3):
        video.write(np.full((24, 32, 3), index * 60, dtype=np.uint8))
    video.release()
    return path


def change_cell(path, row, column, value):
    with path.open(newline="") as source:
        rows = list(csv.reader(source))
    rows[row][column] = value
    with path.open("w", newline="") as output:
        csv.writer(output).writerows(rows)


def test_loader_preserves_encoded_depth_and_raw_calibration(capture):
    loaded = LidarCaptureLoader().load(capture)
    assert len(loaded.frames) == 3
    assert loaded.frames[0].frame_id == "000000"
    assert loaded.frames[0].read_depth()[0, 0] == 1000
    assert loaded.frames[0].intrinsics_fx_fy_cx_cy == (40, 40, 16, 12)
    assert loaded.frames[0].quaternion_xyzw == (0, 0, 0, 1)


@pytest.mark.parametrize("row,column,value,match", [
    (2, 1, "000000", "duplicate frame"),
    (2, 0, "0", "strictly increasing"),
    (1, 2, "nan", "non-finite"),
    (1, 8, "2", "quaternion norm"),
    (1, 9, "0", "focal lengths"),
])
def test_invalid_odometry_rejected(capture, row, column, value, match):
    change_cell(capture / "odometry.csv", row, column, value)
    with pytest.raises(CaptureError, match=match):
        LidarCaptureLoader().load(capture)


def test_missing_pair_rejected(capture):
    (capture / "confidence" / "000001.png").unlink()
    with pytest.raises(CaptureError, match="missing depth/confidence"):
        LidarCaptureLoader().load(capture)


def test_extra_images_rejected(capture):
    Image.fromarray(np.zeros((6, 8), dtype=np.uint16)).save(capture / "depth" / "999999.png")
    with pytest.raises(CaptureError, match="extra images"):
        LidarCaptureLoader().load(capture)


def test_report_checks_images_video_and_warns_about_intrinsics(capture):
    result = inspect_capture(capture, sample_count=2)
    assert result["images"]["headers_checked"] == 3
    assert [item["frame_id"] for item in result["images"]["samples"]] == ["000000", "000002"]
    assert result["images"]["samples"][0]["confidence_counts"] == {"2": 48}
    assert result["rgb"]["frame_count_reported"] == 3
    assert result["rgb"]["width"] == 32
    assert any("principal points" in warning for warning in result["warnings"])
    assert result["odometry"]["median_rate_hz"] == 30


def test_invalid_confidence_rejected(capture):
    Image.fromarray(np.full((6, 8), 255, dtype=np.uint8)).save(capture / "confidence" / "000000.png")
    with pytest.raises(CaptureError, match="confidence labels"):
        inspect_capture(capture)


def test_layout_mismatch_rejected(capture):
    Image.fromarray(np.zeros((8, 8), dtype=np.uint8)).save(capture / "confidence" / "000001.png")
    with pytest.raises(CaptureError, match="layout"):
        inspect_capture(capture)


def test_bad_camera_matrix_rejected(capture):
    (capture / "camera_matrix.csv").write_text("1,0\n0,1\n")
    with pytest.raises(CaptureError, match="3x3"):
        LidarCaptureLoader().load(capture)


def test_bad_imu_rejected(capture):
    change_cell(capture / "imu.csv", 2, 0, "0")
    with pytest.raises(CaptureError, match="IMU: timestamps"):
        LidarCaptureLoader().load(capture)


def test_cli_reports_invalid_capture_and_returns_failure(capture, tmp_path):
    (capture / "depth" / "000000.png").unlink()
    output = tmp_path / "report.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "inspect_capture.py"
    result = subprocess.run([sys.executable, str(script), str(capture), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(output.read_text())["captures"][0]["status"] == "error"


def test_cli_refuses_output_inside_raw_capture(capture):
    script = Path(__file__).resolve().parents[1] / "scripts" / "inspect_capture.py"
    result = subprocess.run([sys.executable, str(script), str(capture), "--output", str(capture / "report.json")], capture_output=True, text=True)
    assert result.returncode == 2
    assert not (capture / "report.json").exists()


def test_report_retains_rgb_count_discrepancy(capture, monkeypatch):
    original = cv2.VideoCapture

    class OverreportedVideo:
        def __init__(self, path):
            self.video = original(path)

        def get(self, key):
            value = self.video.get(key)
            return value + 1 if key == cv2.CAP_PROP_FRAME_COUNT else value

        def __getattr__(self, key):
            return getattr(self.video, key)

    monkeypatch.setattr(cv2, "VideoCapture", OverreportedVideo)
    result = inspect_rgb(capture / "rgb.mp4")
    assert result["frame_count_reported"] == 4
    assert result["frame_count_sequential"] == 3
    assert result["decoded_sample_indices"] == [0, 2]
    assert any("Sequential RGB count" in warning for warning in inspect_capture(capture)["warnings"])
