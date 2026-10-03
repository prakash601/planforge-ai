"""Extract candidate surfaces and closed regions from Task 3 scene artifacts."""

import argparse
import shutil
import sys
from pathlib import Path

from planforge.diagnostics.artifacts import write_json
from planforge.geometry import GeometryConfig, extract_geometry, load_scene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/geometry"))
    parser.add_argument("--up-vector", nargs=3, type=float, help="Explicit unverified world up direction")
    parser.add_argument("--plane-distance", type=float, default=0.06)
    parser.add_argument("--sample-points", type=int, default=40_000)
    parser.add_argument("--max-planes", type=int, default=24)
    parser.add_argument("--junction-tolerance", type=float, default=0.2)
    parser.add_argument("--viewer-assets", type=Path, default=Path("viewer/dist"))
    args = parser.parse_args()
    if not args.input.is_dir() or args.output.resolve().is_relative_to(args.input.resolve()):
        parser.error("output must be outside the input scene tree")
    try:
        config = GeometryConfig(plane_distance=args.plane_distance, sample_points=args.sample_points,
                                max_planes=args.max_planes, junction_tolerance=args.junction_tolerance)
        paths = [args.input] if (args.input / "spatial_scene.json").is_file() else sorted(
            path for path in args.input.iterdir() if (path / "spatial_scene.json").is_file())
        if not paths:
            raise ValueError("no reconstructed SpatialScene artifacts found")
        entries = []
        for path in paths:
            scene = load_scene(path)
            print(f"Extracting {scene.capture_id}: {len(scene.points)} filtered points", file=sys.stderr)
            geometry = extract_geometry(scene, config, args.up_vector)
            destination = args.output / scene.capture_id
            if destination.resolve().is_relative_to(args.input.resolve()):
                raise ValueError("output must be outside the input scene tree")
            destination.mkdir(parents=True, exist_ok=True)
            write_json(destination / "geometry.json", geometry.to_dict())
            for name in ("scene.json", "cloud.ply"):
                shutil.copy2(path / name, destination / name)
            entries.append({"capture_id": scene.capture_id, "scene": f"{scene.capture_id}/scene.json",
                            "geometry": f"{scene.capture_id}/geometry.json"})
            print(f"{scene.capture_id}: {len(geometry.surfaces)} planes, {len(geometry.walls)} wall runs, {len(geometry.regions)} candidate regions; {', '.join(geometry.flags)}", file=sys.stderr)
        write_json(args.output / "manifest.json", {"captures": entries, "stage": "geometry", "top_candidates": [], "scale_status": "unverified"})
        if (args.viewer_assets / "index.html").is_file():
            shutil.copytree(args.viewer_assets, args.output, dirs_exist_ok=True)
        print(f"Artifacts: {args.output}", file=sys.stderr)
        return 0
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Geometry extraction failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
