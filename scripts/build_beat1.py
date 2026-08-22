#!/usr/bin/env python3
"""Prepend the opening card to the recorded gallery and build Beat 1 footage."""

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


def build(manifest_value: str, output_value: str | None) -> None:
    manifest = load_json_object(manifest_value, "video manifest")
    gallery = manifest.get("recordings", {}).get("gallery", {})
    contract = manifest.get("final_contract", {})
    require_keys(
        gallery,
        ["output", "composited_output", "title_card", "title_duration_seconds"],
        "gallery recording",
    )
    require_keys(contract, ["width", "height", "fps"], "final contract")
    recording = require_file(gallery["output"], "gallery recording")
    title = require_file(gallery["title_card"], "opening title card")
    recording_duration = media_duration(recording)
    title_duration = float(gallery["title_duration_seconds"])
    if title_duration <= 0:
        raise VideoBuildError("gallery title_duration_seconds must be positive")
    width, height, fps = int(contract["width"]), int(contract["height"]), float(contract["fps"])
    output = project_path(output_value or gallery["composited_output"])
    filters = [
        f"[0:v]scale={width}:{height}:flags=lanczos,fps={fps:g},setsar=1,format=yuv420p,"
        f"fade=in:st=0:d=0.6,fade=out:st={max(0.0, title_duration - 0.6):.3f}:d=0.6,"
        f"trim=duration={title_duration:.6f},setpts=PTS-STARTPTS[title]",
        f"[1:v]scale={width}:{height}:flags=lanczos,fps={fps:g},setsar=1,format=yuv420p,"
        f"trim=duration={recording_duration:.6f},setpts=PTS-STARTPTS[gallery]",
        "[title][gallery]concat=n=2:v=1:a=0[out]",
    ]
    expected = title_duration + recording_duration
    with atomic_media_output(output) as temporary:
        run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-t",
                str(title_duration),
                "-i",
                str(title),
                "-i",
                str(recording),
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[out]",
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
            expected_duration=expected,
        )
    print(f"built {display_path(output)} ({expected:.3f}s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        build(args.manifest, args.output)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"Beat 1 build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
