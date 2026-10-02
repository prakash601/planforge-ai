"""Reconstruct full captures using an explicit provisional calibration file."""

import argparse
import json
import shutil
import sys
from pathlib import Path

from planforge.diagnostics.artifacts import rgb_metadata, write_json
from planforge.diagnostics.calibration import Hypothesis
from planforge.ingestion import LidarCaptureLoader
from planforge.reconstruction import ReconstructionConfig, reconstruct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/reconstruction"))
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--pixel-stride", type=int, default=4)
    parser.add_argument("--voxel-size", type=float, default=0.05, help="Hypothesized pose units, NOT certified meters")
    parser.add_argument("--min-confidence", type=int, default=2)
    parser.add_argument("--max-voxels", type=int, default=500_000)
    parser.add_argument("--outlier-neighbors", type=int, default=8)
    parser.add_argument("--outlier-std-ratio", type=float, default=2)
    parser.add_argument("--preview-points", type=int, default=150_000)
    parser.add_argument("--viewer-assets", type=Path, default=Path("viewer/dist"))
    args = parser.parse_args()
    if not args.input.is_dir() or args.output.resolve().is_relative_to(args.input.resolve()):
        parser.error("input must be a directory; output must be outside the input tree")
    try:
        payload = json.loads(args.calibration.read_text())
        payload.pop("key", None)
        hypothesis = Hypothesis(**payload)
        config = ReconstructionConfig(**{name: getattr(args, name) for name in ReconstructionConfig.__dataclass_fields__})
        paths = [args.input] if (args.input / "odometry.csv").exists() else sorted(
            path for path in args.input.iterdir() if path.is_dir() and not path.name.startswith("."))
        if not paths:
            raise ValueError("no captures found")
        args.output.mkdir(parents=True, exist_ok=True)
        entries = []
        for path in paths:
            capture = LidarCaptureLoader().load(path)
            scene = reconstruct(capture, rgb_metadata(capture.rgb_path), hypothesis, args.output / path.name,
                                config, str(args.calibration.resolve()), lambda message: print(message, file=sys.stderr))
            entries.append({"capture_id": scene.capture_id, "scene": f"{scene.capture_id}/scene.json",
                            "raw_scene": f"{scene.capture_id}/raw_scene.json",
                            "point_count": len(scene.points), "diagnostics": scene.diagnostics})
            print(json.dumps({"capture_id": scene.capture_id, **scene.diagnostics}), file=sys.stderr)
        write_json(args.output / "manifest.json", {"captures": entries, "selected": hypothesis.to_dict(),
                   "top_candidates": [], "scale_status": "unverified", "stage": "reconstruction"})
        if (args.viewer_assets / "index.html").is_file():
            shutil.copytree(args.viewer_assets, args.output, dirs_exist_ok=True)
        print(f"Artifacts: {args.output}", file=sys.stderr)
        return 0
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, f"Reconstruction failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
