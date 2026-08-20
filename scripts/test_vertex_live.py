#!/usr/bin/env python3
"""
The Aug 20 gate, as an executable.

One real Vertex call, from threebatdrone-prod-420, on a 3.5+ model, returning
structured output that validates against APPRAISAL_SCHEMA, for one real photo.
Nothing here is mocked. If it prints PASS, the integration exists; if it prints
anything else, it does not.

    python scripts/test_vertex_live.py --photo <path|https://...|gs://...> \
                                       --caption "Red Wing 5 gallon crock"

Exit codes: 0 pass · 1 gate failed · 2 preflight failed (deps/auth/photo).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.appraiser.prompts import APPRAISAL_SYSTEM, build_appraisal_prompt  # noqa: E402
from src.appraiser.routing import APPRAISAL_MODEL  # noqa: E402
from src.appraiser.schema import APPRAISAL_SCHEMA, CATEGORIES, CONFIDENCE, to_vertex  # noqa: E402

MAX_LATENCY_S = 5.0


def die(code: int, *lines: str) -> None:
    for ln in lines:
        print(ln, file=sys.stderr)
    sys.exit(code)


def preflight() -> tuple[str, str]:
    """Fail on the boring things before spending a token."""
    try:
        from google import genai  # noqa: F401
    except ImportError:
        die(2, "PREFLIGHT FAIL: google-genai is not installed.",
               "    pip install google-genai")

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        # gcloud's own config is the fallback, so the script works with no .env.
        import subprocess
        project = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True,
        ).stdout.strip()
    if not project or project == "(unset)":
        die(2, "PREFLIGHT FAIL: no project.",
               "    gcloud config set project threebatdrone-prod-420")

    adc = Path.home() / ".config/gcloud/application_default_credentials.json"
    if not adc.exists() and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        die(2, f"PREFLIGHT FAIL: no ADC at {adc}",
               "    gcloud auth application-default login")

    # gemini-3.5+ is not in every regional endpoint; global is the one that has it.
    return project, os.environ.get("VERTEX_LOCATION", "global")


def load_photo(ref: str) -> tuple[bytes, str]:
    """Local path, https URL, or gs:// URI -> (bytes, mime_type)."""
    if ref.startswith("gs://"):
        try:
            from google.cloud import storage
        except ImportError:
            die(2, "PREFLIGHT FAIL: gs:// needs google-cloud-storage, or pass a "
                   "local path / https URL instead.")
        bucket, _, blob = ref[5:].partition("/")
        data = storage.Client().bucket(bucket).blob(blob).download_as_bytes()
    elif ref.startswith("http://") or ref.startswith("https://"):
        req = urllib.request.Request(ref, headers={"User-Agent": "blue-toad-fleet/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    else:
        p = Path(ref)
        if not p.exists():
            die(2, f"PREFLIGHT FAIL: no photo at {p}")
        data = p.read_bytes()

    if not data:
        die(2, f"PREFLIGHT FAIL: {ref} is empty")
    mime = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    return data, mime


def validate(data: dict) -> list[str]:
    """Check the payload against APPRAISAL_SCHEMA — required keys, types, enums."""
    problems: list[str] = []
    for key in APPRAISAL_SCHEMA["required"]:
        if key not in data:
            problems.append(f"missing required field: {key}")

    if data.get("category") not in CATEGORIES:
        problems.append(f"category {data.get('category')!r} not in CATEGORIES")
    if data.get("confidence") not in CONFIDENCE:
        problems.append(f"confidence {data.get('confidence')!r} not in CONFIDENCE")

    for key in ("marks_observed", "condition_notes", "questions"):
        if key in data and not isinstance(data[key], list):
            problems.append(f"{key} is {type(data[key]).__name__}, expected list")

    pen = data.get("condition_penalty")
    if isinstance(pen, (int, float)) and not 0.0 <= pen <= 1.0:
        problems.append(f"condition_penalty {pen} outside [0, 1]")

    for i, q in enumerate(data.get("questions") or []):
        if not isinstance(q, dict):
            problems.append(f"questions[{i}] is not an object")
            continue
        for key in APPRAISAL_SCHEMA["properties"]["questions"]["items"]["required"]:
            if key not in q:
                problems.append(f"questions[{i}] missing {key}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", required=True,
                    help="local path, https:// URL, or gs:// URI of ONE real photo")
    ap.add_argument("--caption", default="",
                    help="the gallery caption, as the pipeline would pass it")
    ap.add_argument("--model", default=APPRAISAL_MODEL)
    args = ap.parse_args()

    project, location = preflight()
    photo, mime = load_photo(args.photo)

    from google import genai
    from google.genai import types

    print(f"[*] project={project} location={location} model={args.model}")
    print(f"[*] photo={args.photo} ({len(photo):,} bytes, {mime})")

    client = genai.Client(vertexai=True, project=project, location=location)

    t0 = time.perf_counter()
    resp = client.models.generate_content(
        model=args.model,
        contents=[
            types.Part.from_bytes(data=photo, mime_type=mime),
            build_appraisal_prompt(caption=args.caption),
        ],
        config=types.GenerateContentConfig(
            system_instruction=APPRAISAL_SYSTEM,
            response_mime_type="application/json",
            response_schema=to_vertex(APPRAISAL_SCHEMA),
            temperature=0.1,
        ),
    )
    elapsed = time.perf_counter() - t0

    text = (resp.text or "").strip()
    if not text:
        die(1, f"GATE FAIL: empty response after {elapsed:.2f}s", repr(resp))

    print(text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        die(1, f"GATE FAIL: response is not JSON ({e})")

    problems = validate(data)

    usage = getattr(resp, "usage_metadata", None)
    print(f"\n[*] latency {elapsed:.2f}s (budget {MAX_LATENCY_S}s)")
    if usage:
        print(f"[*] tokens in={usage.prompt_token_count} "
              f"out={usage.candidates_token_count}")

    if problems:
        die(1, "GATE FAIL: schema violations:", *(f"    - {p}" for p in problems))

    # Latency is reported, not enforced — a slow pass is still a pass, and the
    # fan-out budget is a separate problem from whether the call works at all.
    if elapsed > MAX_LATENCY_S:
        print(f"[!] over the {MAX_LATENCY_S}s budget — fine for the gate, "
              f"revisit before the 304-photo fan-out")

    print(f"[PASS] live Vertex call, {args.model}, schema-valid against "
          f"APPRAISAL_SCHEMA, {len(data.get('questions') or [])} question(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
