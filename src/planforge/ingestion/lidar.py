"""Read raw capture metadata without guessing units or coordinate conventions."""

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image


class CaptureError(ValueError):
    """A capture violates the ingestion contract."""


@dataclass(frozen=True)
class FrameRecord:
    frame_id: str
    timestamp: float
    position: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float]
    intrinsics_fx_fy_cx_cy: tuple[float, float, float, float]
    depth_path: Path
    confidence_path: Path

    def read_depth(self) -> np.ndarray:
        """Return encoded depth values; no implicit conversion to meters."""
        with Image.open(self.depth_path) as image:
            return np.asarray(image).copy()

    def read_confidence(self) -> np.ndarray:
        with Image.open(self.confidence_path) as image:
            return np.asarray(image).copy()


@dataclass(frozen=True)
class LidarCapture:
    path: Path
    frames: tuple[FrameRecord, ...]
    camera_matrix: tuple[tuple[float, ...], ...]
    imu_rows: tuple[dict[str, str], ...]
    rgb_path: Path


class CaptureLoader(Protocol):
    def load(self, path: str | Path) -> LidarCapture: ...


def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source, skipinitialspace=True)
        if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise CaptureError(f"{path.name}: missing or duplicate header")
        if missing := required - set(reader.fieldnames):
            raise CaptureError(f"{path.name}: missing columns {sorted(missing)}")
        rows = list(reader)
        if not rows:
            raise CaptureError(f"{path.name}: no records")
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise CaptureError(f"{path.name}: inconsistent row width")
        return rows


def number(row: dict[str, str], field: str) -> float:
    value = float(row[field])
    if not math.isfinite(value):
        raise CaptureError(f"non-finite {field}")
    return value


def validate_times(times: list[float], label: str) -> None:
    if any(right <= left for left, right in zip(times, times[1:])):
        raise CaptureError(f"{label}: timestamps must be strictly increasing")


class LidarCaptureLoader:
    """Validate metadata and exact PNG/pose pairing; defer pixel decoding."""

    def load(self, path: str | Path) -> LidarCapture:
        path = Path(path).resolve()
        try:
            return self._load(path)
        except (OSError, ValueError, KeyError) as error:
            raise CaptureError(f"{path.name}: {error}") from error

    def _load(self, path: Path) -> LidarCapture:
        required = {"timestamp", "frame", "x", "y", "z", "qx", "qy", "qz", "qw", "fx", "fy", "cx", "cy"}
        rows = read_csv(path / "odometry.csv", required)
        depth = {p.stem: p for p in (path / "depth").glob("*.png")}
        confidence = {p.stem: p for p in (path / "confidence").glob("*.png")}
        frames = []
        seen = set()
        for row in rows:
            frame_id = row["frame"].strip()
            if not frame_id.isascii() or not frame_id.isdigit() or frame_id in seen:
                raise CaptureError(f"invalid or duplicate frame ID: {frame_id!r}")
            seen.add(frame_id)
            if frame_id not in depth or frame_id not in confidence:
                raise CaptureError(f"frame {frame_id}: missing depth/confidence PNG")
            quaternion = tuple(number(row, key) for key in ("qx", "qy", "qz", "qw"))
            if abs(math.sqrt(sum(x * x for x in quaternion)) - 1) > 0.01:
                raise CaptureError(f"frame {frame_id}: quaternion norm outside 1 +/- 0.01")
            intrinsics = tuple(number(row, key) for key in ("fx", "fy", "cx", "cy"))
            if intrinsics[0] <= 0 or intrinsics[1] <= 0:
                raise CaptureError(f"frame {frame_id}: focal lengths must be positive")
            frames.append(FrameRecord(
                frame_id, number(row, "timestamp"),
                tuple(number(row, key) for key in ("x", "y", "z")),
                quaternion, intrinsics, depth[frame_id], confidence[frame_id],
            ))
        if set(depth) != seen or set(confidence) != seen:
            raise CaptureError("PNG IDs do not exactly match odometry IDs (extra images)")
        validate_times([frame.timestamp for frame in frames], "odometry")
        imu = read_csv(path / "imu.csv", {"timestamp", "a_x", "a_y", "a_z", "alpha_x", "alpha_y", "alpha_z"})
        for row in imu:
            for key in ("timestamp", "a_x", "a_y", "a_z", "alpha_x", "alpha_y", "alpha_z"):
                number(row, key)
        validate_times([number(row, "timestamp") for row in imu], "IMU")
        with (path / "camera_matrix.csv").open(newline="") as source:
            matrix = tuple(tuple(float(value) for value in row) for row in csv.reader(source))
        if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
            raise CaptureError("camera_matrix.csv: expected 3x3 matrix")
        if not all(math.isfinite(value) for row in matrix for value in row):
            raise CaptureError("camera_matrix.csv: non-finite value")
        if matrix[0][0] <= 0 or matrix[1][1] <= 0 or matrix[2] != (0.0, 0.0, 1.0):
            raise CaptureError("camera_matrix.csv: invalid pinhole calibration")
        rgb = path / "rgb.mp4"
        if not rgb.is_file() or rgb.stat().st_size == 0:
            raise CaptureError("missing or empty rgb.mp4")
        return LidarCapture(path, tuple(frames), matrix, tuple(imu), rgb)
