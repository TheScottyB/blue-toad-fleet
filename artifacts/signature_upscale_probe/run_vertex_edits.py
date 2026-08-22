"""Run repeated Vertex image edits for the signature upscaling probe."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "source" / "signature_low_168x126.png"
OUTPUT = ROOT / "ai"
PROJECT = "threebatdrone-prod-420"
LOCATION = "global"

PROMPT = """Faithfully upscale this exact evidence crop to a larger raster image.
Do not redraw, reinterpret, beautify, correct, complete, add, remove, or alter any
signature stroke, letter, ink gap, jersey thread, wrinkle, seam, color, boundary,
or geometry. Preserve every ambiguous or blurry mark exactly as ambiguous or
blurry. This is a forensic enlargement, not a recreation. Keep the same 4:3 crop
and return only the enlarged image."""

# Repeat the middle model to expose run-to-run variation, while retaining one
# result from each image model named in the original capability probe.
RUNS = [
    ("gemini-3.1-flash-lite-image", 1),
    ("gemini-3.1-flash-image", 1),
    ("gemini-3.1-flash-image", 2),
    ("gemini-3.1-flash-image", 3),
    ("gemini-3-pro-image", 1),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flash-repetition",
        type=int,
        help="Run only one additional Gemini 3.1 Flash repetition.",
    )
    args = parser.parse_args()
    runs = RUNS
    manifest = ROOT / "vertex_runs.json"
    if args.flash_repetition is not None:
        runs = [("gemini-3.1-flash-image", args.flash_repetition)]
        manifest = ROOT / "vertex_repeat_runs.json"

    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = INPUT.read_bytes()
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    records: list[dict[str, object]] = []

    for model, repetition in runs:
        response = client.models.generate_content(
            model=model,
            contents=[
                PROMPT,
                types.Part.from_bytes(data=source, mime_type="image/png"),
            ],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                temperature=0.0,
                image_config=types.ImageConfig(aspect_ratio="4:3"),
            ),
        )

        image_bytes = None
        response_text: list[str] = []
        for candidate in response.candidates or []:
            if not candidate.content:
                continue
            for part in candidate.content.parts or []:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                elif part.text:
                    response_text.append(part.text)

        if image_bytes is None:
            raise RuntimeError(f"{model} repetition {repetition}: no image returned")

        stem = model.replace("gemini-", "").replace("-image", "")
        output_path = OUTPUT / f"{stem}_r{repetition}.png"
        output_path.write_bytes(image_bytes)
        with Image.open(output_path) as image:
            dimensions = [image.width, image.height]

        records.append(
            {
                "model": model,
                "repetition": repetition,
                "output": str(output_path.relative_to(ROOT)),
                "dimensions": dimensions,
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
                "response_text": "\n".join(response_text),
            }
        )
        print(f"{model} r{repetition}: {dimensions[0]}x{dimensions[1]}", flush=True)

    manifest.write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
