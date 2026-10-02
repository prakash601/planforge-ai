"""Export diagnostic point samples, poses and explicit calibration provenance."""

import json
from pathlib import Path

import cv2
import numpy as np

from .calibration import backproject, camera_transform, depth_intrinsics, transform_points


def rgb_metadata(path):
    video = cv2.VideoCapture(str(path))
    try:
        if not video.isOpened():
            raise ValueError(f"cannot open {path}")
        size = (int(video.get(cv2.CAP_PROP_FRAME_WIDTH)), int(video.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        if min(size) <= 0:
            raise ValueError("invalid RGB dimensions")
        return size
    finally:
        video.release()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def export_scene(capture, rgb_size, hypothesis, output, start=0, frames=36, frame_step=30, pixel_stride=3):
    output = Path(output)
    if output.resolve().is_relative_to(capture.path.resolve()):
        raise ValueError("output must be outside the raw capture directory")
    if start < 0 or start >= len(capture.frames) or min(frames, frame_step, pixel_stride) < 1:
        raise ValueError("invalid frame selection")
    output.mkdir(parents=True, exist_ok=True)
    indices = list(range(start, min(len(capture.frames), start + frames * frame_step), frame_step))
    points, confidence, frame_indices, trajectory = [], [], [], []
    labels = []
    for local_index, index in enumerate(indices):
        frame = capture.frames[index]
        depth, mask = frame.read_depth(), frame.read_confidence()
        if depth.shape != mask.shape or depth.ndim != 2 or not set(np.unique(mask)) <= {0, 1, 2}:
            raise ValueError(f"{frame.frame_id}: invalid depth/confidence layout")
        intrinsics = depth_intrinsics(frame, depth.shape, rgb_size, hypothesis)
        local = backproject(depth, intrinsics, hypothesis.depth_scale)[::pixel_stride, ::pixel_stride]
        valid = depth[::pixel_stride, ::pixel_stride] > 0
        world = transform_points(local[valid], frame, hypothesis)
        points.append(world)
        confidence.append(mask[::pixel_stride, ::pixel_stride][valid])
        frame_indices.append(np.full(len(world), local_index))
        _, center = camera_transform(frame, hypothesis)
        trajectory.append(center.tolist())
        labels.append({"id": frame.frame_id, "timestamp": frame.timestamp})
    cloud = np.concatenate(points).astype(np.float32)
    confidence = np.concatenate(confidence).astype(np.uint8)
    frame_indices = np.concatenate(frame_indices).astype(np.int32)
    if len(cloud) == 0:
        raise ValueError("no nonzero depth samples in selected frames")
    # Binary PLY is a standard inspectable artifact; confidence/frame IDs stay attached.
    dtype = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("confidence", "u1"), ("frame_index", "<i4")])
    records = np.empty(len(cloud), dtype=dtype)
    for axis, name in enumerate(("x", "y", "z")):
        records[name] = cloud[:, axis]
    records["confidence"], records["frame_index"] = confidence, frame_indices
    header = (f"ply\nformat binary_little_endian 1.0\ncomment scale unverified; coordinates in hypothesized pose units\nelement vertex {len(cloud)}\n"
              "property float x\nproperty float y\nproperty float z\nproperty uchar confidence\nproperty int frame_index\nend_header\n")
    with (output / "cloud.ply").open("wb") as file:
        file.write(header.encode("ascii"))
        file.write(records.tobytes())
    scene = {"capture_id": capture.path.name, "hypothesis": hypothesis.to_dict(), "scale_status": "unverified",
             "coordinate_units": "hypothesized pose units, not certified meters", "frames": labels,
             "points": np.round(cloud, 5).ravel().tolist(), "confidence": confidence.tolist(),
             "frame_indices": frame_indices.tolist(), "trajectory": trajectory,
             "point_count": len(cloud), "pixel_stride": pixel_stride}
    write_json(output / "scene.json", scene)
    write_json(output / "calibration.json", hypothesis.to_dict())
    return {"capture_id": capture.path.name, "scene": f"{capture.path.name}/scene.json", "point_count": len(cloud), "frames": len(labels)}
