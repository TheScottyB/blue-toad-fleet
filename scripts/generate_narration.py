#!/usr/bin/env python3
"""Generate facts-resolved demo narration through ElevenLabs.

Audio files are written atomically. No request is made until the video facts
snapshot has been verified against every declared source hash.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from video_common import (
    VideoBuildError,
    atomic_write_bytes,
    load_json_object,
    load_verified_facts,
    project_path,
    require_file,
)


DEFAULT_VOICE = "iP95p4xoKVk53GoZ742B"
DEFAULT_MODEL = "eleven_multilingual_v2"
BEAT_BREAK = '<break time="1.6s" />'
PLACEHOLDER = re.compile(r"{{\s*([a-zA-Z0-9_.]+)(?:\|([a-z]+))?\s*}}")
SPEECH_FIXES = [(r"\bcomps\b", "comparables"), (r"\bCOMP\b", "COMPARABLE")]


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        environment = project_path(".env.local")
        if environment.is_file():
            for line in environment.read_text(encoding="utf-8").splitlines():
                if line.startswith("ELEVENLABS_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise VideoBuildError("ELEVENLABS_API_KEY is not set in the environment or .env.local")
    return key


def _lookup(facts: dict, dotted_key: str):
    value: object = facts
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise VideoBuildError(f"video narration references unknown fact: {dotted_key}")
        value = value[part]
    return value


def render_facts(text: str, facts: dict) -> str:
    def replace(match: re.Match) -> str:
        key, formatter = match.group(1), match.group(2)
        value = _lookup(facts, key)
        if formatter is None:
            return str(value)
        if formatter == "usd":
            try:
                return f"{float(value):,.2f} dollars"
            except (TypeError, ValueError) as exc:
                raise VideoBuildError(f"fact {key} cannot be formatted as USD") from exc
        raise VideoBuildError(f"unsupported narration fact formatter: {formatter}")

    rendered = PLACEHOLDER.sub(replace, text)
    if "{{" in rendered or "}}" in rendered:
        raise VideoBuildError("video narration contains an invalid or unresolved fact placeholder")
    return rendered


def speakify(text: str) -> str:
    for pattern, replacement in SPEECH_FIXES:
        text = re.sub(pattern, replacement, text)
    return text


def parse_beats(script_path: Path, facts: dict) -> list[dict]:
    source = script_path.read_text(encoding="utf-8")
    parts = re.split(r"^## .*?Beat (\d+):(.*?)$", source, flags=re.MULTILINE)
    beats: list[dict] = []
    for index in range(1, len(parts), 3):
        number, title, body = parts[index], parts[index + 1].strip(), parts[index + 2]
        lines = re.findall(r'^\s*> \*?"?(.*?)"?\*?\s*$', body, flags=re.MULTILINE)
        text = " ".join(line.strip() for line in lines if line.strip())
        text = render_facts(text, facts)
        text = re.sub(r"[*_]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            beats.append(
                {
                    "beat": int(number),
                    "title": title,
                    "text": speakify(text),
                }
            )
    if [beat["beat"] for beat in beats] != [1, 2, 3, 4]:
        raise VideoBuildError("video script must contain exactly Beats 1 through 4 with voiceover")
    return beats


def synthesize(text: str, key: str, voice: str, model: str) -> bytes:
    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        data=json.dumps(
            {
                "text": text,
                "model_id": model,
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.8,
                    "style": 0.0,
                },
            }
        ).encode(),
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            content_type = response.headers.get_content_type()
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise VideoBuildError(f"ElevenLabs HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise VideoBuildError(f"ElevenLabs request failed: {exc.reason}") from exc
    if content_type not in {"audio/mpeg", "audio/mp3", "application/octet-stream"}:
        raise VideoBuildError(f"ElevenLabs returned unexpected content type: {content_type}")
    if len(payload) < 1024:
        raise VideoBuildError("ElevenLabs returned an unexpectedly small audio payload")
    return payload


def generate(
    manifest_value: str,
    output_directory_value: str,
    full: bool,
    voice: str,
    model: str,
) -> None:
    manifest = load_json_object(manifest_value, "video manifest")
    facts = load_verified_facts(manifest)
    script = require_file(manifest["sources"]["video_script"], "video script")
    beats = parse_beats(script, facts)
    output_directory = project_path(output_directory_value)
    output_directory.mkdir(parents=True, exist_ok=True)
    key = api_key()
    if full:
        text = f" {BEAT_BREAK} ".join(beat["text"] for beat in beats)
        destination = output_directory / "narration_full.mp3"
        atomic_write_bytes(destination, synthesize(text, key, voice, model))
        print(f"full narration: {len(text.split())} words -> {destination}")
        return
    for beat in beats:
        destination = output_directory / f"beat{beat['beat']}.mp3"
        atomic_write_bytes(destination, synthesize(beat["text"], key, voice, model))
        print(f"beat {beat['beat']}: {len(beat['text'].split())} words -> {destination}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output-dir", default="media/vo")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--voice", default=os.environ.get("BTF_VOICE", DEFAULT_VOICE))
    parser.add_argument("--model", default=os.environ.get("BTF_TTS_MODEL", DEFAULT_MODEL))
    args = parser.parse_args(argv)
    try:
        generate(args.manifest, args.output_dir, args.full, args.voice, args.model)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"narration generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
