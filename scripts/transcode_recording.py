#!/usr/bin/env python3
"""Normalize a declared Playwright recording for the final video assembler."""

from __future__ import annotations

import argparse
import sys

from video_common import (
    VideoBuildError,
    atomic_media_output,
    display_path,
    load_json_object,
    media_duration,
    project_path,
    require_file,
    require_keys,
    run,
    validate_video,
)


def transcode(manifest_value: str, recording_name: str, output_value: str | None) -> None:
    manifest = load_json_object(manifest_value, "video manifest")
    recording = manifest.get("recordings", {}).get(recording_name)
    if not isinstance(recording, dict):
        raise VideoBuildError(f"unknown recording in video manifest: {recording_name}")
    require_keys(recording, ["output", "composited_output"], f"{recording_name} recording")
    contract = manifest.get("final_contract", {})
    require_keys(contract, ["width", "height", "fps"], "final contract")
    source = require_file(recording["output"], f"{recording_name} recording")
    duration = media_duration(source)
    width, height, fps = int(contract["width"]), int(contract["height"]), float(contract["fps"])
    output = project_path(output_value or recording["composited_output"])
    with atomic_media_output(output) as temporary:
        run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vf",
                f"scale={width}:{height}:flags=lanczos,fps={fps:g},setsar=1,format=yuv420p",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "18",
                "-preset",
                "slow",
                str(temporary),
            ]
        )
        validate_video(
            temporary,
            width=width,
            height=height,
            require_audio=False,
            expected_duration=duration,
        )
    print(f"built {display_path(output)} ({duration:.3f}s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", choices=["beat2", "terminal"])
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        transcode(args.manifest, args.recording, args.output)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"recording transcode failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
