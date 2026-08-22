"""Shared, fail-closed helpers for the submission-video build."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


class VideoBuildError(RuntimeError):
    """Raised when a media input or output violates the video contract."""


def project_path(value: str | os.PathLike[str]) -> Path:
    """Resolve repository-relative configuration paths without changing cwd."""
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def require_file(value: str | os.PathLike[str], label: str = "input") -> Path:
    path = project_path(value)
    if not path.is_file() or path.stat().st_size == 0:
        raise VideoBuildError(f"missing or empty {label}: {display_path(path)}")
    return path


def load_json_object(value: str | os.PathLike[str], label: str = "JSON") -> dict:
    path = require_file(value, label)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoBuildError(f"invalid {label} at {display_path(path)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VideoBuildError(f"{label} must be a JSON object: {display_path(path)}")
    return payload


def require_keys(payload: Mapping, keys: Sequence[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise VideoBuildError(f"{label} is missing required keys: {', '.join(missing)}")


def run(command: Sequence[str], *, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Run one command without a shell and surface the exact failed program."""
    try:
        return subprocess.run(
            list(command),
            check=True,
            text=capture_output,
            capture_output=capture_output,
        )
    except FileNotFoundError as exc:
        raise VideoBuildError(f"required program is not installed: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() if capture_output else ""
        suffix = f": {detail}" if detail else ""
        raise VideoBuildError(f"command failed ({command[0]}){suffix}") from exc


def probe_media(value: str | os.PathLike[str]) -> dict:
    path = require_file(value, "media input")
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VideoBuildError(f"ffprobe returned invalid JSON for {display_path(path)}") from exc
    if not isinstance(payload.get("streams"), list) or not isinstance(payload.get("format"), dict):
        raise VideoBuildError(f"ffprobe returned incomplete metadata for {display_path(path)}")
    return payload


def media_duration(value: str | os.PathLike[str]) -> float:
    path = project_path(value)
    payload = probe_media(path)
    raw = payload["format"].get("duration")
    try:
        duration = float(raw)
    except (TypeError, ValueError) as exc:
        raise VideoBuildError(f"media has no usable duration: {display_path(path)}") from exc
    if duration <= 0:
        raise VideoBuildError(f"media duration must be positive: {display_path(path)}")
    return duration


def sha256_file(value: str | os.PathLike[str]) -> str:
    path = require_file(value)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_verified_facts(video_manifest: Mapping) -> dict:
    """Load facts and reject a snapshot whose declared source files changed."""
    require_keys(video_manifest, ["facts", "sources"], "video manifest")
    facts = load_json_object(video_manifest["facts"], "submission facts")
    require_keys(
        facts,
        ["schema_version", "cycle", "money", "tests", "runtime", "source_sha256"],
        "submission facts",
    )
    if facts["schema_version"] not in {1, 2}:
        raise VideoBuildError(
            f"unsupported submission facts schema_version: {facts['schema_version']}"
        )
    hashes = facts["source_sha256"]
    if not isinstance(hashes, Mapping):
        raise VideoBuildError("submission facts source_sha256 must be an object")
    mismatches: list[str] = []
    for name, value in video_manifest["sources"].items():
        expected = hashes.get(name)
        if not expected or sha256_file(value) != expected:
            mismatches.append(name)
    if mismatches:
        raise VideoBuildError(
            "submission facts are stale for: " + ", ".join(sorted(mismatches))
        )
    return facts


def atomic_write_text(value: str | os.PathLike[str], text: str) -> Path:
    destination = project_path(value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def atomic_write_bytes(value: str | os.PathLike[str], payload: bytes) -> Path:
    destination = project_path(value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


@contextmanager
def atomic_media_output(value: str | os.PathLike[str]) -> Iterator[Path]:
    """Yield a sibling media path and publish it only after the caller succeeds."""
    destination = project_path(value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.stem}.",
        suffix=destination.suffix,
    )
    os.close(fd)
    temporary = Path(temporary_name)
    temporary.unlink(missing_ok=True)
    try:
        yield temporary
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise VideoBuildError(f"media build produced no output: {display_path(temporary)}")
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def validate_video(
    value: str | os.PathLike[str],
    *,
    width: int,
    height: int,
    require_audio: bool,
    expected_duration: float | None = None,
    duration_tolerance: float = 0.75,
    max_bytes: int | None = None,
) -> dict:
    path = project_path(value)
    payload = probe_media(path)
    video_streams = [s for s in payload["streams"] if s.get("codec_type") == "video"]
    audio_streams = [s for s in payload["streams"] if s.get("codec_type") == "audio"]
    if len(video_streams) != 1:
        raise VideoBuildError(
            f"expected exactly one video stream in {display_path(path)}, found {len(video_streams)}"
        )
    video = video_streams[0]
    actual_size = (int(video.get("width", 0)), int(video.get("height", 0)))
    if actual_size != (width, height):
        raise VideoBuildError(
            f"expected {width}x{height}, got {actual_size[0]}x{actual_size[1]} "
            f"in {display_path(path)}"
        )
    if require_audio and not audio_streams:
        raise VideoBuildError(f"final video is silent: {display_path(path)}")
    duration = media_duration(path)
    if expected_duration is not None and abs(duration - expected_duration) > duration_tolerance:
        raise VideoBuildError(
            f"expected duration {expected_duration:.3f}s (+/- {duration_tolerance:.3f}s), "
            f"got {duration:.3f}s in {display_path(path)}"
        )
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise VideoBuildError(
            f"output is {path.stat().st_size:,} bytes; limit is {max_bytes:,}: {display_path(path)}"
        )
    return payload
