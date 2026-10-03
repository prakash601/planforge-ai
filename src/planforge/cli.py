"""The installed `planforge run` entry point."""

import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(prog="planforge")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="Raw LiDAR capture to candidate plan, JSON and evidence"
    )
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument(
        "--calibration",
        type=Path,
        required=True,
        help="Explicit provisional calibration JSON from Task 2",
    )
    run.add_argument(
        "--up-vector",
        nargs=3,
        type=float,
        help="Optional explicit, unverified up direction",
    )
    run.add_argument("--frame-step", type=int, default=1)
    run.add_argument("--pixel-stride", type=int, default=4)
    run.add_argument("--voxel-size", type=float, default=0.05)
    run.add_argument("--max-voxels", type=int, default=500_000)
    args = parser.parse_args()
    # Open3D segmentation repeats serially; set before importing its runtime.
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    from jsonschema import ValidationError

    from planforge.pipeline import run_capture
    from planforge.reconstruction import ReconstructionConfig

    try:
        config = ReconstructionConfig(
            frame_step=args.frame_step,
            pixel_stride=args.pixel_stride,
            voxel_size=args.voxel_size,
            max_voxels=args.max_voxels,
        )
        record = run_capture(
            args.input,
            args.output,
            args.calibration,
            config,
            up_vector=args.up_vector,
            progress=lambda message: print(message, file=sys.stderr),
        )
        print(f"Complete: {args.output / 'index.html'}", file=sys.stderr)
        print(
            f"Scale unverified. Candidate regions only. {record['timings_seconds']['total_compute']:.1f}s",
            file=sys.stderr,
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as error:
        parser.exit(1, f"PlanForge run failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
