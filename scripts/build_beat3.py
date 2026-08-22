#!/usr/bin/env python3
"""Composite the recorded Gate Console walkthrough with declared lower thirds."""

from __future__ import annotations

import argparse
import json
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
    walkthrough = manifest.get("recordings", {}).get("walkthrough", {})
    contract = manifest.get("final_contract", {})
    require_keys(
        walkthrough,
        ["output", "markers", "composited_output", "overlays"],
        "walkthrough recording",
    )
    require_keys(contract, ["width", "height", "fps"], "final contract")
    source = require_file(walkthrough["output"], "walkthrough recording")
    marker_path = require_file(walkthrough["markers"], "walkthrough markers")
    try:
        raw_markers = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VideoBuildError(f"invalid walkthrough markers: {exc}") from exc
    if not isinstance(raw_markers, list):
        raise VideoBuildError("walkthrough markers must be a list")
    markers = {
        item.get("label"): float(item["t"])
        for item in raw_markers
        if isinstance(item, dict) and item.get("label") and "t" in item
    }
    duration = media_duration(source)
    if "end" not in markers:
        raise VideoBuildError("walkthrough markers are missing end")
    offset = duration - markers["end"]
    if offset < -0.25:
        raise VideoBuildError(
            f"walkthrough end marker ({markers['end']:.3f}s) exceeds video ({duration:.3f}s)"
        )
    adjusted = {name: timestamp + max(0.0, offset) for name, timestamp in markers.items()}

    overlays = walkthrough["overlays"]
    if not isinstance(overlays, list) or not overlays:
        raise VideoBuildError("walkthrough must declare at least one lower-third overlay")
    inputs = ["-i", str(source)]
    windows: list[tuple[str, float, float]] = []
    for index, overlay in enumerate(overlays, 1):
        require_keys(
            overlay,
            ["card", "start", "start_offset", "end", "end_offset"],
            f"walkthrough overlay {index}",
        )
        if overlay["start"] not in adjusted or overlay["end"] not in adjusted:
            raise VideoBuildError(
                f"overlay {overlay['card']} references a missing walkthrough marker"
            )
        start = adjusted[overlay["start"]] + float(overlay["start_offset"])
        end = adjusted[overlay["end"]] + float(overlay["end_offset"])
        if start < 0 or end <= start or end > duration + 0.1:
            raise VideoBuildError(
                f"invalid overlay window for {overlay['card']}: {start:.3f}s..{end:.3f}s"
            )
        card = require_file(f"media/cards/{overlay['card']}.png", "lower-third card")
        inputs.extend(["-loop", "1", "-i", str(card)])
        windows.append((str(overlay["card"]), start, end))

    width, height, fps = int(contract["width"]), int(contract["height"]), float(contract["fps"])
    filters = [f"[0:v]scale={width}:{height}:flags=lanczos,fps={fps:g},setsar=1[base]"]
    previous = "base"
    for index, (_, start, end) in enumerate(windows, 1):
        fade = min(0.45, (end - start) / 3)
        filters.append(
            f"[{index}:v]format=rgba,fade=in:st={start:.3f}:d={fade:.3f}:alpha=1,"
            f"fade=out:st={end - fade:.3f}:d={fade:.3f}:alpha=1[card{index}]"
        )
        filters.append(
            f"[{previous}][card{index}]overlay=0:0:enable='between(t,{start - 0.1:.3f},"
            f"{end:.3f})'[video{index}]"
        )
        previous = f"video{index}"
    filters.append(
        f"[{previous}]trim=duration={duration:.6f},setpts=PTS-STARTPTS[main]"
    )

    output = project_path(output_value or walkthrough["composited_output"])
    with atomic_media_output(output) as temporary:
        run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                *inputs,
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[main]",
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
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        build(args.manifest, args.output)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"Beat 3 build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
