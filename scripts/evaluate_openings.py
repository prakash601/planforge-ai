"""Score plane-local opening annotations, explicitly counting misses and phantoms."""

import argparse
import json
from pathlib import Path

from planforge.diagnostics.artifacts import write_json
from planforge.openings.evaluation import score_openings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument(
        "--width-tolerance",
        type=float,
        required=True,
        help="Explicit pose-unit tolerance, NOT a centimeter gate",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.detections.resolve(), args.annotations.resolve()):
        parser.error("output cannot overwrite annotations or detections")
    try:
        detection = json.loads(args.detections.read_text())
        annotations = json.loads(args.annotations.read_text())
        result = score_openings(
            detection["candidates"], annotations, args.width_tolerance
        )
        result["capture_id"] = detection["capture_id"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, result)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Opening evaluation failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
