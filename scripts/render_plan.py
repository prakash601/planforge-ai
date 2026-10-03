"""Render an existing Task 5 measurement artifact without rerunning capture stages."""

import argparse
import json
import shutil
from pathlib import Path

from jsonschema import ValidationError

from planforge.rendering import render_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.input / "measurements.json" if args.input.is_dir() else args.input
    if args.output.resolve().is_relative_to(source.parent.resolve()):
        parser.error("output must be outside the source artifact directory")
    try:
        model = json.loads(source.read_text())
        render_plan(model, args.output)
        shutil.copy2(source, args.output / "measurements.json")
        # A render-only record deliberately does not impersonate a full pipeline run.
        (args.output / "run.json").write_text(
            json.dumps(
                {
                    "status": "render_only",
                    "source_measurements": str(source.resolve()),
                    "scale_status": "unverified",
                },
                indent=2,
            )
            + "\n"
        )
        return 0
    except (OSError, ValueError, TypeError, KeyError, ValidationError) as error:
        parser.exit(1, f"Plan rendering failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
