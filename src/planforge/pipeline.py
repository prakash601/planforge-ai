"""One-capture LiDAR pipeline with staged publication and reproducible settings."""

import json
import platform
import tempfile
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from planforge.diagnostics.artifacts import rgb_metadata, write_json
from planforge.diagnostics.calibration import Hypothesis
from planforge.geometry import GeometryConfig, extract_geometry
from planforge.ingestion import LidarCaptureLoader
from planforge.measurements import measure_geometry
from planforge.openings import OpeningConfig, attach_openings, detect_openings
from planforge.reconstruction import ReconstructionConfig, reconstruct
from planforge.rendering import render_plan


def run_capture(
    input_path,
    output,
    calibration,
    reconstruction=None,
    geometry=None,
    up_vector=None,
    progress=None,
    openings=None,
):
    reconstruction = (
        ReconstructionConfig() if reconstruction is None else reconstruction
    )
    geometry = GeometryConfig() if geometry is None else geometry
    openings = OpeningConfig() if openings is None else openings
    input_path, output, calibration = (
        Path(path).resolve() for path in (input_path, output, calibration)
    )
    if output.is_relative_to(input_path) or input_path.is_relative_to(output):
        raise ValueError("output must be separate from the raw input tree")
    if not input_path.is_dir():
        raise ValueError("input must be one raw LiDAR capture directory")
    if output.exists():
        marker = output / "run.json"
        prior = json.loads(marker.read_text()) if marker.is_file() else {}
        if (
            not output.is_dir()
            or prior.get("status") != "complete"
            or prior.get("schema_version") != 1
            or prior.get("input_path") != str(input_path)
        ):
            raise ValueError(
                "refusing to replace output without a matching PlanForge run record"
            )
    payload = json.loads(calibration.read_text())
    payload.pop("key", None)
    hypothesis = Hypothesis(**payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    timings = {}
    started = perf_counter()

    def stage(name, operation):
        if progress:
            progress(name)
        before = perf_counter()
        result = operation()
        timings[name] = perf_counter() - before
        return result

    with tempfile.TemporaryDirectory(
        prefix=".planforge-", dir=output.parent
    ) as temporary:
        workspace = Path(temporary) / "complete"
        workspace.mkdir()
        capture = stage("ingestion", lambda: LidarCaptureLoader().load(input_path))
        rgb_size = stage("rgb_metadata", lambda: rgb_metadata(capture.rgb_path))
        scene = stage(
            "reconstruction",
            lambda: reconstruct(
                capture,
                rgb_size,
                hypothesis,
                workspace / "debug" / "reconstruction",
                reconstruction,
                str(calibration),
                progress,
            ),
        )
        room_geometry = stage(
            "geometry", lambda: extract_geometry(scene, geometry, up_vector)
        )
        write_json(workspace / "debug" / "geometry.json", room_geometry.to_dict())
        model = stage("measurements", lambda: measure_geometry(room_geometry.to_dict()))
        detection = stage(
            "openings", lambda: detect_openings(scene, room_geometry, openings)
        )
        write_json(workspace / "debug" / "openings.json", detection)
        model = attach_openings(model, detection)
        write_json(workspace / "measurements.json", model)
        artifacts = stage("rendering", lambda: render_plan(model, workspace))
        timings["total_compute"] = perf_counter() - started
        record = {
            "schema_version": 1,
            "status": "complete",
            "capture_id": scene.capture_id,
            "input_path": str(input_path),
            "calibration_path": str(calibration),
            "calibration": hypothesis.to_dict(),
            "configuration": {
                "reconstruction": asdict(reconstruction),
                "geometry": asdict(geometry),
                "openings": asdict(openings),
                "up_vector": None if up_vector is None else list(up_vector),
            },
            "timings_seconds": timings,
            "scale_status": "unverified",
            "flags": model["flags"],
            "source_depth_pose_sha256": scene.provenance["selected_depth_pose_sha256"],
            "artifacts": {
                "measurements": "measurements.json",
                "geometry": "debug/geometry.json",
                "openings": "debug/openings.json",
                "reconstruction": "debug/reconstruction/spatial_scene.json",
                **artifacts,
            },
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "packages": {
                    name: version(name)
                    for name in (
                        "planforge-ai",
                        "numpy",
                        "Pillow",
                        "scipy",
                        "open3d",
                        "shapely",
                        "jsonschema",
                    )
                },
            },
            "limitations": [
                "Provisional calibration; physical scale unknown",
                "Supplied poses, no drift correction",
                "Candidate regions, not verified rooms or property footprint",
                "Sensitivity ranges uncalibrated",
                "Opening classes geometry-only and unverified; no RGB alignment",
                "No damage, stitching or non-LiDAR input tier",
            ],
        }
        write_json(workspace / "run.json", record)
        backup = Path(temporary) / "previous"
        if output.exists():
            output.rename(backup)
        try:
            workspace.rename(output)
        except OSError:
            if backup.exists():
                backup.rename(output)
            raise
    return record
