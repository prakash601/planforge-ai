"""Export candidate measurements from one or more Task 4 geometry artifacts."""

import argparse
import json
from pathlib import Path
import sys

from jsonschema import ValidationError

from planforge.diagnostics.artifacts import write_json
from planforge.measurements import measure_geometry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/measurements"))
    args = parser.parse_args()
    if not args.input.is_dir() or args.output.resolve().is_relative_to(
        args.input.resolve()
    ):
        parser.error("output must be outside the input geometry tree")
    try:
        paths = (
            [args.input / "geometry.json"]
            if (args.input / "geometry.json").is_file()
            else sorted(args.input.glob("*/geometry.json"))
        )
        if not paths:
            raise ValueError("no geometry.json artifacts found")
        # Validate the entire batch before publishing any measurement files.
        models = [measure_geometry(json.loads(path.read_text())) for path in paths]
        if len({model["capture_id"] for model in models}) != len(models):
            raise ValueError("duplicate capture IDs")
        entries = []
        for model in models:
            destination = args.output / model["capture_id"]
            if destination.resolve().is_relative_to(args.input.resolve()):
                raise ValueError("output must be outside the input geometry tree")
            destination.mkdir(parents=True, exist_ok=True)
            write_json(destination / "measurements.json", model)
            entries.append(
                {
                    "capture_id": model["capture_id"],
                    "measurements": f"{model['capture_id']}/measurements.json",
                }
            )
            print(
                f"{model['capture_id']}: {len(model['rooms'])} candidate regions, {len(model['measurements'])} measurements; scale unverified",
                file=sys.stderr,
            )
        write_json(
            args.output / "manifest.json",
            {"stage": "measurements", "schema_version": "1.0.0", "captures": entries},
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as error:
        parser.exit(1, f"Measurement extraction failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
