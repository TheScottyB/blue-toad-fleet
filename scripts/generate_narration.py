#!/usr/bin/env python3
"""Generate the demo narration from docs/VIDEO_SCRIPT.md via ElevenLabs.

Reads ELEVENLABS_API_KEY from the environment or .env.local (gitignored).
Writes one mp3 per beat into media/vo/.
"""
import json, os, pathlib, re, sys, urllib.error, urllib.request

VOICE = os.environ.get("BTF_VOICE", "iP95p4xoKVk53GoZ742B")   # Chris — down-to-earth
MODEL = os.environ.get("BTF_TTS_MODEL", "eleven_multilingual_v2")
OUT = pathlib.Path("media/vo")


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        env = pathlib.Path(".env.local")
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("ELEVENLABS_API_KEY="):
                    key = line.split("=", 1)[1].strip()
    if not key:
        sys.exit("ELEVENLABS_API_KEY not set (env or .env.local)")
    return key


def beats() -> list[dict]:
    """Pull the > blockquote voiceover out of each ## Beat N section."""
    src = pathlib.Path("docs/VIDEO_SCRIPT.md").read_text()
    parts = re.split(r"^## .*?Beat (\d+):(.*?)$", src, flags=re.M)
    out = []
    for i in range(1, len(parts), 3):
        num, title, body = parts[i], parts[i + 1].strip(), parts[i + 2]
        lines = re.findall(r'^\s*> \*?"?(.*?)"?\*?\s*$', body, flags=re.M)
        text = " ".join(re.sub(r"[*_]", "", v).strip() for v in lines if v.strip())
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append({"beat": int(num), "title": title, "text": text})
    return out


def synthesize(text: str, key: str) -> bytes:
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}",
        data=json.dumps({
            "text": text,
            "model_id": MODEL,
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.0},
        }).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def main() -> None:
    key = api_key()
    OUT.mkdir(parents=True, exist_ok=True)
    for b in beats():
        dest = OUT / f"beat{b['beat']}.mp3"
        try:
            dest.write_bytes(synthesize(b["text"], key))
        except urllib.error.HTTPError as e:
            sys.exit(f"beat {b['beat']}: HTTP {e.code} — {e.read().decode()[:300]}")
        print(f"beat {b['beat']}: {len(b['text'].split()):3d} words -> {dest} "
              f"({dest.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
