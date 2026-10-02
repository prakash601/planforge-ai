"""Count RGB frames through a separate FFmpeg CLI decoding path."""

import argparse
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

from planforge.diagnostics.artifacts import write_json


def count_frames(executable, path, ignore_editlist=False):
    command = [executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "2"]
    if ignore_editlist:
        command += ["-ignore_editlist", "1"]
    command += ["-i", str(path), "-map", "0:v:0", "-an", "-sn", "-vsync", "0", "-progress", "pipe:1", "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise ValueError(f"FFmpeg failed on {path.name}: {result.stderr[-2000:]}")
    counts = re.findall(r"^frame=(\d+)\s*$", result.stdout, flags=re.MULTILINE)
    if not counts:
        raise ValueError("FFmpeg returned no frame count")
    return {"frames": int(counts[-1]), "ignore_editlist": ignore_editlist, "decoder_messages": result.stderr.strip()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/calibration/rgb-check.json"))
    args = parser.parse_args()
    if not args.input.is_dir() or args.output.resolve().is_relative_to(args.input.resolve()):
        parser.error("input must be a directory; output must be outside the input tree")
    paths = [args.input] if (args.input / "rgb.mp4").exists() else sorted(path for path in args.input.iterdir() if path.is_dir() and not path.name.startswith("."))
    if not paths:
        parser.error("no capture directories")
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    report = {"ffmpeg_version": imageio_ffmpeg.get_ffmpeg_version(), "method": "separate CLI path, still FFmpeg-based; not an independent codec implementation", "captures": []}
    for path in paths:
        print(f"Decoding {path.name} with and without MP4 edit lists", flush=True)
        report["captures"].append({"capture_id": path.name, "default": count_frames(executable, path / "rgb.mp4"), "ignore_editlist": count_frames(executable, path / "rgb.mp4", True)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)


if __name__ == "__main__":
    main()
