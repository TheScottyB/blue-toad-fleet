#!/usr/bin/env python3
"""Run the release Vertex gate against the exact production model and image."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google import genai
from google.genai import types

from src.appraisal import Appraisal, Confidence
from src.appraiser.images import assert_appraisal_grade, image_mime_type
from src.appraiser.prompts import APPRAISAL_SYSTEM, build_appraisal_prompt
from src.appraiser.routing import APPRAISAL_MODEL
from src.appraiser.schema import APPRAISAL_SCHEMA, to_vertex


DEFAULT_IMAGE = ROOT / "data/aug22_gallery_4160518/images/001_838421457.jpg"


def prepare_live_image(path: Path) -> tuple[bytes, str]:
    """Return verified appraisal-grade bytes and their detected MIME type."""
    if not path.is_file():
        raise FileNotFoundError(
            f"release gate requires a real sample image; not found: {path}")
    image = assert_appraisal_grade(path.read_bytes(), lot_id="LIVE-GATE")
    mime_type = image_mime_type(image)
    if mime_type is None:  # Explicit even though the grade guard catches it.
        raise ValueError(f"release gate cannot detect image MIME type: {path}")
    return image, mime_type


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    args = parser.parse_args(argv)

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "threebatdrone-prod-420")
    location = os.environ.get("VERTEX_LOCATION", "global")

    print("[*] Initializing Google GenAI Client (Vertex AI mode)...")
    print(f"    Project:  {project}")
    print(f"    Location: {location}")
    print(f"    Model:    {APPRAISAL_MODEL} (exact production route)")

    try:
        image_bytes, mime_type = prepare_live_image(args.image)
        client = genai.Client(vertexai=True, project=project, location=location)
    except Exception as exc:
        print(f"[!] Live gate setup failed: {exc}", file=sys.stderr)
        return 1

    contents = [
        build_appraisal_prompt(
            caption="Vintage Topps Baseball Cards - 1960s partial set in plastic sleeves",
            category_hint="vintage toys",
        ),
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
    ]
    print(f"[*] Attached sample photo: {args.image} ({mime_type}, {len(image_bytes)} bytes)")

    start = time.time()
    try:
        response = client.models.generate_content(
            model=APPRAISAL_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=APPRAISAL_SYSTEM,
                response_mime_type="application/json",
                response_schema=to_vertex(APPRAISAL_SCHEMA),
                temperature=0.1,
            ),
        )
        data = json.loads(response.text)
        for field in ("identification", "category", "confidence", "questions"):
            if field not in data:
                raise ValueError(f"response missing required field: {field}")
        appraisal = Appraisal(
            lot_id="LIVE-GATE",
            category=data["category"],
            identification=data["identification"],
            confidence=Confidence(data.get("confidence", "medium")),
            est_value_hint=float(data.get("value_magnitude_hint") or 0.0),
        )
    except Exception as exc:
        print(f"[!] FAIL: {APPRAISAL_MODEL} did not pass the multimodal gate: {exc}",
              file=sys.stderr)
        return 1

    print(f"[+] Response received in {time.time() - start:.2f}s")
    print(f"[+] Parsed appraisal: {appraisal}")
    print(f"[+] Questions emitted: {len(data.get('questions', []))}")
    print(f"[✓] PASS: {APPRAISAL_MODEL} passed with verified {mime_type} input")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
