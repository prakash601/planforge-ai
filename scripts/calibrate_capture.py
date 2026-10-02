"""Rank calibration hypotheses and export depth-only diagnostic scenes."""

import argparse
import shutil
import sys
from pathlib import Path

from planforge.diagnostics.artifacts import export_scene, rgb_metadata, write_json
from planforge.diagnostics.calibration import Hypothesis, candidate_hypotheses, rank_hypotheses
from planforge.ingestion import LidarCaptureLoader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/calibration"))
    parser.add_argument("--scales", type=float, nargs="+", default=[0.0005, 0.001, 0.002, 0.01, 1.0])
    parser.add_argument("--config", type=Path, help="Explicit hypothesis JSON instead of automatic selection")
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--frames", type=int, default=36)
    parser.add_argument("--frame-step", type=int, default=30)
    parser.add_argument("--viewer-assets", type=Path, default=Path("viewer/dist"))
    args = parser.parse_args()
    if not args.input.is_dir() or args.output.resolve().is_relative_to(args.input.resolve()):
        parser.error("input must be a directory; output must be outside the input tree")
    try:
        hypotheses = candidate_hypotheses(args.scales)
        paths = [args.input] if (args.input / "odometry.csv").exists() else sorted(path for path in args.input.iterdir() if path.is_dir() and not path.name.startswith("."))
        if not paths:
            raise ValueError("no captures found")
        captures = [LidarCaptureLoader().load(path) for path in paths]
        sizes = [rgb_metadata(capture.rgb_path) for capture in captures]
        print(f"Scoring {len(hypotheses)} hypotheses across {len(captures)} captures", file=sys.stderr)
        rankings = rank_hypotheses(captures, sizes, hypotheses)
        if not any(pair["valid"] for result in rankings for capture in result["captures"] for pair in capture["pairs"]):
            raise ValueError("no supported frame pairs; calibration cannot be ranked")
        best = rankings[0]["hypothesis"]
        config = {key: value for key, value in best.items() if key != "key"}
        if args.config:
            import json
            config = json.loads(args.config.read_text())
            config.pop("key", None)
        selected = Hypothesis(**config)
        args.output.mkdir(parents=True, exist_ok=True)
        per_capture_winners = {capture.path.name: min(rankings, key=lambda row: next(item["score"] for item in row["captures"] if item["capture_id"] == capture.path.name))["hypothesis"]["key"] for capture in captures}
        report = {"schema_version": 1, "selected": selected.to_dict(), "selection": "manual" if args.config else "lowest aggregate diagnostic score",
                  "selection_status": "provisional diagnostic preference",
                  "sampling": {"windows_per_capture": 5, "pair_lags_frames": [30, 90], "symmetric": True, "pixel_stride": 4, "minimum_confidence_label": 2},
                  "export": {"start_frame": args.start_frame, "frames_requested": args.frames, "frame_step": args.frame_step, "pixel_stride": 3},
                  "rgb_resolutions": {capture.path.name: size for capture, size in zip(captures, sizes)},
                  "scale_status": "unverified", "score_definition": "Mean symmetric projective residual score, penalized for unsupported overlap; lower is better, range 0-1",
                  "limitations": ["Relative consistency is not ground-truth accuracy or physical scale validation.", "Only two axis conventions and two pose directions are tested; crop/orientation/pixel-center alternatives remain possible.", "Dynamic surfaces, occlusion, confidence filtering and pose drift can affect ranking.", "RGB projection is not enabled; synchronization is unverified."],
                  "per_capture_winners": per_capture_winners, "rankings": rankings}
        write_json(args.output / "diagnostics.json", report)
        entries = []
        for capture, size in zip(captures, sizes):
            print(f"Exporting {capture.path.name}: {selected.key}", file=sys.stderr)
            entries.append(export_scene(capture, size, selected, args.output / capture.path.name, args.start_frame, args.frames, args.frame_step))
        write_json(args.output / "manifest.json", {"captures": entries, "selected": selected.to_dict(),
                   "top_candidates": [{"hypothesis": row["hypothesis"], "score": row["score"]} for row in rankings[:8]], "scale_status": "unverified"})
        if (args.viewer_assets / "index.html").is_file():
            shutil.copytree(args.viewer_assets, args.output, dirs_exist_ok=True)
        selected_score = next((f"{row['score']:.4f}" for row in rankings if row["hypothesis"]["key"] == selected.key), "not in candidate grid")
        if not (args.viewer_assets / "index.html").is_file():
            print("Viewer assets absent: build viewer/ and rerun to include the browser viewer", file=sys.stderr)
        print(f"Artifacts: {args.output}; selected {selected.key}; score {selected_score}", file=sys.stderr)
        return 0
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, f"Calibration failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
