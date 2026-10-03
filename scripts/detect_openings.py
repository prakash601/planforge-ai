"""Detect candidate openings from full reconstructed scene and Task 4 geometry."""

import argparse
import json
from pathlib import Path

from jsonschema import ValidationError

from planforge.diagnostics.artifacts import write_json
from planforge.geometry import load_scene
from planforge.measurements import measure_geometry
from planforge.openings import attach_openings, detect_openings
from planforge.rendering import render_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(
        args.scene.resolve()
    ) or args.output.resolve().is_relative_to(args.geometry.parent.resolve()):
        parser.error("output must be outside the source artifact trees")
    try:
        scene = load_scene(args.scene)
        geometry = json.loads(args.geometry.read_text())
        detection = detect_openings(scene, geometry)
        model = attach_openings(measure_geometry(geometry), detection)
        args.output.mkdir(parents=True, exist_ok=True)
        write_json(args.output / "openings.json", detection)
        write_json(args.output / "measurements.json", model)
        render_plan(model, args.output)
        write_json(
            args.output / "run.json",
            {
                "status": "opening_analysis_only",
                "scene": str(args.scene.resolve()),
                "geometry": str(args.geometry.resolve()),
                "scale_status": "unverified",
            },
        )
        print(
            f"{scene.capture_id}: {len(model['openings'])} associated candidates; {len(detection['unresolved_gaps'])} unresolved gaps"
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as error:
        parser.exit(1, f"Opening detection failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
