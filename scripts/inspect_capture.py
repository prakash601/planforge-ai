"""Inspect one capture or a directory of captures and emit JSON diagnostics."""

import argparse
import json
import sys
from importlib.metadata import version
from pathlib import Path

from planforge.ingestion import CaptureError
from planforge.ingestion.inspection import inspect_capture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Capture directory or parent directory")
    parser.add_argument("--samples", type=int, default=8, help="Depth/confidence pixel samples per capture")
    parser.add_argument("--output", type=Path, help="Write JSON report to this path")
    args = parser.parse_args()
    if not args.input.is_dir() or args.samples < 1:
        parser.error("input must be a directory and --samples must be positive")
    captures = [args.input] if (args.input / "odometry.csv").exists() else sorted(p for p in args.input.iterdir() if p.is_dir() and not p.name.startswith("."))
    if not captures:
        parser.error("no capture directories found")
    results = []
    for path in captures:
        print(f"Inspecting {path.name}", file=sys.stderr)
        try:
            results.append(inspect_capture(path, args.samples))
        except (CaptureError, OSError, ValueError) as error:
            results.append({"capture_id": path.name, "status": "error", "error": str(error)})
    report = {"schema_version": 1, "sample_count_requested": args.samples,
              "runtime": {name: version(name) for name in ("planforge-ai", "numpy", "Pillow", "opencv-python-headless")},
              "captures": results}
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        # Keep raw captures immutable, even when the output path is supplied manually.
        output = args.output.resolve()
        if output.is_relative_to(args.input.resolve()):
            parser.error("--output must be outside the input directory")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(f"Report: {args.output}", file=sys.stderr)
    else:
        print(encoded, end="")
    return int(any(result["status"] == "error" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
