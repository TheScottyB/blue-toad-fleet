#!/usr/bin/env python3
"""Build and verify the one authoritative narrated submission video.

Every input and output comes from ``media/video_manifest.json``. Audio and
video durations are probed at build time, short footage is padded only within
its declared allowance, and the prior final cut remains untouched unless the
new file passes the stream, dimensions, duration, and size contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from video_common import (
    VideoBuildError,
    atomic_media_output,
    display_path,
    load_json_object,
    load_verified_facts,
    media_duration,
    project_path,
    require_file,
    require_keys,
    run,
    sha256_file,
    validate_video,
)


DEFAULT_MANIFEST = "media/video_manifest.json"


def _canonical_facts(manifest: dict, output: Path) -> tuple[str, dict] | None:
    configured = project_path(manifest["final_output"])
    # The authoritative path must come from the repository manifest, not the
    # caller's --manifest: reading it from `manifest` would make every build
    # look canonical, and hardcoding it here would duplicate the declaration.
    declared = load_json_object(project_path(DEFAULT_MANIFEST), "video manifest")
    authoritative = project_path(declared["final_output"])
    if (
        configured.resolve() != authoritative.resolve()
        or output.resolve() != configured.resolve()
    ):
        return None
    facts = load_verified_facts(manifest)
    if facts.get("schema_version") != 2:
        raise VideoBuildError("canonical final requires schema-2 submission facts")
    publication = facts.get("publication") or {}
    if publication.get("release_eligible") is not True:
        raise VideoBuildError(
            "canonical final requires a release-eligible published artifact manifest"
        )
    return sha256_file(manifest["facts"]), facts


def _input_identity(manifest: dict, facts_sha256: str) -> str:
    paths = [manifest["close"]["card"]]
    for beat in manifest["beats"]:
        paths.extend((beat["video"], beat["audio"]))
    payload = {
        "facts_sha256": facts_sha256,
        "inputs": {str(path): sha256_file(path) for path in paths},
    }
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def _embedded_comment(payload: dict) -> str:
    tags = (payload.get("format") or {}).get("tags") or {}
    return str(tags.get("comment") or tags.get("COMMENT") or "")


def _require_embedded_facts(payload: dict, facts_sha256: str) -> None:
    comment = _embedded_comment(payload)
    if f"blue-toad-facts-sha256={facts_sha256}" not in comment:
        raise VideoBuildError("final video is not bound to the current facts")


def _require_embedded_identity(payload: dict, facts_sha256: str, inputs_sha256: str) -> None:
    expected = f"blue-toad-facts-sha256={facts_sha256};inputs-sha256={inputs_sha256}"
    if _embedded_comment(payload) != expected:
        raise VideoBuildError("final video is not bound to the current facts and inputs")


def _source_paths(manifest: dict) -> list[str]:
    paths = [manifest["close"]["card"]]
    for beat in manifest["beats"]:
        paths.extend((beat["video"], beat["audio"]))
    return paths


def _sources_present(manifest: dict) -> bool:
    return all(
        (path := project_path(value)).is_file() and path.stat().st_size > 0
        for value in _source_paths(manifest)
    )


def _positive_number(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VideoBuildError(f"{label} must be a number") from exc
    if number <= 0:
        raise VideoBuildError(f"{label} must be positive")
    return number


def verify(manifest_path: str, output_override: str | None = None) -> None:
    manifest = load_json_object(manifest_path, "video manifest")
    require_keys(
        manifest,
        ["beats", "close", "final_contract", "final_output"],
        "video manifest",
    )
    contract = manifest["final_contract"]
    require_keys(
        contract,
        ["width", "height", "max_bytes", "duration_tolerance_seconds"],
        "final contract",
    )
    beats = manifest["beats"]
    if not isinstance(beats, list) or not beats:
        raise VideoBuildError("video manifest must declare at least one beat")
    expected_duration = sum(
        media_duration(require_file(beat["audio"], f"{beat.get('name', 'beat')} audio"))
        for beat in beats
    ) + _positive_number(manifest["close"]["duration_seconds"], "close.duration_seconds")
    output = require_file(output_override or manifest["final_output"], "final video")
    canonical = _canonical_facts(manifest, output)
    payload = validate_video(
        output,
        width=int(contract["width"]),
        height=int(contract["height"]),
        require_audio=True,
        expected_duration=expected_duration,
        duration_tolerance=float(contract["duration_tolerance_seconds"]),
        max_bytes=int(contract["max_bytes"]),
    )
    if canonical:
        facts_sha256, _facts = canonical
        if _sources_present(manifest):
            _require_embedded_identity(
                payload, facts_sha256, _input_identity(manifest, facts_sha256),
            )
        else:
            # Clone verify: gitignored raw beat videos are not on disk.
            # Still require the published file to carry the current facts hash.
            _require_embedded_facts(payload, facts_sha256)
    print(
        f"verified {display_path(output)}: {expected_duration:.3f}s expected, "
        f"{output.stat().st_size:,} bytes, video+audio present"
    )


def build(manifest_path: str, output_override: str | None = None) -> None:
    manifest = load_json_object(manifest_path, "video manifest")
    require_keys(
        manifest,
        ["schema_version", "beats", "close", "encoder", "final_contract", "final_output"],
        "video manifest",
    )
    if manifest["schema_version"] != 1:
        raise VideoBuildError(
            f"unsupported video manifest schema_version: {manifest['schema_version']}"
        )
    beats = manifest["beats"]
    if not isinstance(beats, list) or not beats:
        raise VideoBuildError("video manifest must declare at least one beat")

    close = manifest["close"]
    encoder = manifest["encoder"]
    contract = manifest["final_contract"]
    require_keys(close, ["card", "duration_seconds"], "close-card configuration")
    require_keys(
        encoder,
        ["video_codec", "crf", "preset", "audio_codec", "audio_bitrate"],
        "encoder configuration",
    )
    require_keys(
        contract,
        ["width", "height", "fps", "max_bytes", "duration_tolerance_seconds"],
        "final contract",
    )

    width = int(contract["width"])
    height = int(contract["height"])
    fps = _positive_number(contract["fps"], "final_contract.fps")
    close_duration = _positive_number(close["duration_seconds"], "close.duration_seconds")
    close_card = require_file(close["card"], "close card")
    output = project_path(output_override or manifest["final_output"])
    canonical = _canonical_facts(manifest, output)

    inputs: list[str] = []
    filters: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []
    probed: list[dict] = []

    for index, beat in enumerate(beats):
        if not isinstance(beat, dict):
            raise VideoBuildError(f"beat {index + 1} must be an object")
        require_keys(
            beat,
            ["name", "video", "audio", "max_video_pad_seconds"],
            f"beat {index + 1}",
        )
        video = require_file(beat["video"], f"{beat['name']} video")
        audio = require_file(beat["audio"], f"{beat['name']} audio")
        video_duration = media_duration(video)
        audio_duration = media_duration(audio)
        allowance = float(beat["max_video_pad_seconds"])
        if allowance < 0:
            raise VideoBuildError(f"{beat['name']} max_video_pad_seconds cannot be negative")
        deficit = max(0.0, audio_duration - video_duration)
        if deficit > allowance + 0.02:
            raise VideoBuildError(
                f"{beat['name']} footage is {deficit:.3f}s shorter than its narration; "
                f"declared allowance is {allowance:.3f}s"
            )
        probed.append(
            {
                "name": beat["name"],
                "video": video,
                "audio": audio,
                "video_duration": video_duration,
                "audio_duration": audio_duration,
                "pad": deficit,
            }
        )
    work_directory = tempfile.TemporaryDirectory(
        dir=output.parent, prefix=".video-build-"
    )
    try:
        # Normalize every beat before concatenation. Screen recordings can change
        # color metadata midstream; feeding those files directly to concat makes
        # FFmpeg rebuild the graph and can silently discard the close card.
        for beat in probed:
            normalized = Path(work_directory.name) / f"{beat['name']}.mp4"
            video_filters = [
                f"scale={width}:{height}:flags=lanczos",
                f"fps={fps:g}",
                "setsar=1",
                "format=yuv420p",
            ]
            if beat["pad"] > 0:
                video_filters.append(
                    f"tpad=stop_mode=clone:stop_duration={beat['pad'] + 0.1:.6f}"
                )
            video_filters.extend(
                [
                    f"trim=duration={beat['audio_duration']:.6f}",
                    "setpts=PTS-STARTPTS",
                ]
            )
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-reinit_filter",
                    "0",
                    "-i",
                    str(beat["video"]),
                    "-vf",
                    ",".join(video_filters),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-crf",
                    "18",
                    "-preset",
                    "fast",
                    str(normalized),
                ]
            )
            if media_duration(normalized) + 0.05 < beat["audio_duration"]:
                raise VideoBuildError(
                    f"failed to normalize {beat['name']} footage to its narration duration"
                )
            beat["video"] = normalized

        close_video = Path(work_directory.name) / "close.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-i",
                str(close_card),
                "-t",
                str(close_duration),
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
                "fast",
                str(close_video),
            ]
        )
        if abs(media_duration(close_video) - close_duration) > 0.1:
            raise VideoBuildError("failed to materialize the declared close-card duration")
    except BaseException:
        work_directory.cleanup()
        raise

    for beat in probed:
        inputs.extend(["-i", str(beat["video"])])

    inputs.extend(["-i", str(close_video)])
    for beat in probed:
        inputs.extend(["-i", str(beat["audio"])])
    inputs.extend(
        [
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=stereo:d={close_duration}",
        ]
    )

    count = len(probed)
    for index, beat in enumerate(probed):
        duration = beat["audio_duration"]
        filters.append(
            f"[{index}:v]scale={width}:{height}:flags=lanczos,fps={fps:g},"
            f"setsar=1,format=yuv420p,trim=duration={duration:.6f},"
            f"setpts=PTS-STARTPTS[v{index}]"
        )
        audio_index = count + 1 + index
        filters.append(
            f"[{audio_index}:a]aresample=44100,aformat=channel_layouts=stereo,"
            f"atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[a{index}]"
        )
        video_labels.append(f"[v{index}]")
        audio_labels.append(f"[a{index}]")

    close_video_index = count
    close_audio_index = count + 1 + count
    fade_duration = min(0.6, close_duration / 3)
    filters.append(
        f"[{close_video_index}:v]scale={width}:{height}:flags=lanczos,fps={fps:g},"
        f"setsar=1,format=yuv420p,fade=in:st=0:d={fade_duration:.3f},"
        f"fade=out:st={close_duration - fade_duration:.3f}:d={fade_duration:.3f},"
        f"trim=duration={close_duration:.6f},setpts=PTS-STARTPTS[v{count}]"
    )
    filters.append(
        f"[{close_audio_index}:a]aresample=44100,aformat=channel_layouts=stereo,"
        f"atrim=duration={close_duration:.6f},asetpts=PTS-STARTPTS[a{count}]"
    )
    video_labels.append(f"[v{count}]")
    audio_labels.append(f"[a{count}]")
    pairs = "".join(v + a for v, a in zip(video_labels, audio_labels))
    filters.append(f"{pairs}concat=n={count + 1}:v=1:a=1[outv][outa]")

    expected_duration = sum(item["audio_duration"] for item in probed) + close_duration
    facts_sha256 = canonical[0] if canonical else None
    inputs_sha256 = _input_identity(manifest, facts_sha256) if facts_sha256 else None
    try:
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
                    "[outv]",
                    "-map",
                    "[outa]",
                    "-c:v",
                    str(encoder["video_codec"]),
                    "-pix_fmt",
                    "yuv420p",
                    "-crf",
                    str(encoder["crf"]),
                    "-preset",
                    str(encoder["preset"]),
                    "-c:a",
                    str(encoder["audio_codec"]),
                    "-b:a",
                    str(encoder["audio_bitrate"]),
                    "-movflags",
                    "+faststart",
                    *( ["-metadata", (
                        f"comment=blue-toad-facts-sha256={facts_sha256};"
                        f"inputs-sha256={inputs_sha256}"
                    )] if facts_sha256 else [] ),
                    str(temporary),
                ]
            )
            payload = validate_video(
                temporary,
                width=width,
                height=height,
                require_audio=True,
                expected_duration=expected_duration,
                duration_tolerance=float(contract["duration_tolerance_seconds"]),
                max_bytes=int(contract["max_bytes"]),
            )
            if facts_sha256:
                _require_embedded_identity(payload, facts_sha256, inputs_sha256)
    finally:
        work_directory.cleanup()

    print(
        f"built {display_path(output)}: {expected_duration:.3f}s, "
        f"{output.stat().st_size:,} bytes, video+audio verified"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--output", help="override final_output for a verification build")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.verify_only:
            verify(args.manifest, args.output)
        else:
            build(args.manifest, args.output)
    except VideoBuildError as exc:
        print(f"video build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
