"""Stitch per-capture candidate models into one candidate property model."""

import argparse
import json
import platform
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from planforge.diagnostics.artifacts import write_json
from planforge.stitching import StitchingConfig, load_inputs, stitch_measurements
from planforge.stitching.render import render_property


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", type=Path, required=True,
                        help="Per-capture measurements.json files (2+ recommended, 1 allowed)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--property-id", default="property-assumed-single")
    parser.add_argument("--transforms", type=Path, default=None,
                        help="Optional JSON object keyed by capture_id with [rotation_deg, tx, ty] or {rotation_deg, translation}")
    parser.add_argument("--links", type=Path, default=None,
                        help="Optional JSON list of manual room adjacency links")
    args = parser.parse_args()
    try:
        if args.output.exists() and not args.output.is_dir():
            parser.error("output must be a directory")
        for path in args.inputs:
            if not path.is_file():
                parser.error(f"missing input: {path}")
            if args.output.resolve().is_relative_to(path.resolve().parent):
                parser.error("output must be outside the input trees")
        started = perf_counter()
        models = load_inputs(args.inputs)
        transforms = json.loads(args.transforms.read_text()) if args.transforms else None
        links = json.loads(args.links.read_text()) if args.links else None
        prop = stitch_measurements(models, StitchingConfig(args.property_id), transforms, links)
        args.output.mkdir(parents=True, exist_ok=True)
        write_json(args.output / "property.json", prop)
        artifacts = render_property(prop, args.output)
        record = {
            "schema_version": 1,
            "status": "complete",
            "property_id": prop["property_id"],
            "inputs": [str(p) for p in args.inputs],
            "captures": [m["capture_id"] for _, m in models],
            "room_count": len(prop["rooms"]),
            "wall_count": len(prop["walls"]),
            "edge_count": len(prop["room_graph"]["edges"]),
            "overlap_count": len(prop["overlaps"]),
            "flags": prop["flags"],
            "scale_status": "unverified",
            "alignment": "identity_or_manual_2d_rigid_unverified",
            "assumption": "single_property_assumed_per_user_instruction_not_evidence",
            "artifacts": {"property": "property.json", **artifacts},
            "timings_seconds": {"total_compute": perf_counter() - started},
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "packages": {n: version(n) for n in ("planforge-ai", "numpy", "shapely", "jsonschema", "Pillow")},
            },
            "limitations": prop["provenance"]["limitations"],
        }
        write_json(args.output / "run.json", record)
        print(f"{prop['property_id']}: {len(prop['rooms'])} rooms, "
              f"{len(prop['room_graph']['edges'])} edges, {len(prop['overlaps'])} overlaps")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Property stitching failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
