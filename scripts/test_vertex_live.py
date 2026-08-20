#!/usr/bin/env python3
"""
scripts/test_vertex_live.py — Vertex AI Live Gate Proof.

Executes a live structured appraisal against Vertex AI on project threebatdrone-prod-420.
Uses a cached image from the gallery (e.g. Edison cylinder lot or July crock) and
validates that the response conforms to APPRAISAL_SCHEMA and parses cleanly into Appraisal.
"""

import os
import sys
import json
import time
from pathlib import Path
from google import genai
from google.genai import types

from src.appraiser.schema import APPRAISAL_SCHEMA, to_vertex
from src.appraiser.prompts import APPRAISAL_SYSTEM, build_appraisal_prompt
from src.appraisal import Appraisal, Confidence

def main():
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "threebatdrone-prod-420")
    location = os.environ.get("VERTEX_LOCATION", "global")
    
    # Priority model: gemini-3.6-flash or gemini-3.5-flash-lite or gemini-2.5-flash fallback
    models_to_try = [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
    ]
    
    print(f"[*] Initializing Google GenAI Client (Vertex AI mode)...")
    print(f"    Project:  {project}")
    print(f"    Location: {location}")
    
    try:
        client = genai.Client(vertexai=True, project=project, location=location)
    except Exception as e:
        print(f"[!] Failed to initialize genai.Client: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Pick a real sample image from our cached gallery
    sample_img_path = Path("data/aug22_gallery_4160518/images/001_838421457.jpg")
    if not sample_img_path.exists():
        sample_img_path = Path("demo/fixtures/crock.jpg")

    image_bytes = sample_img_path.read_bytes() if sample_img_path.exists() else None
    
    vertex_schema = to_vertex(APPRAISAL_SCHEMA)
    prompt_text = build_appraisal_prompt(
        caption="Vintage Topps Baseball Cards - 1960s partial set in plastic sleeves",
        category_hint="vintage toys",
    )
    
    contents = [prompt_text]
    if image_bytes:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
        print(f"[*] Attached sample photo: {sample_img_path} ({len(image_bytes)} bytes)")
    
    success = False
    for model_name in models_to_try:
        print(f"\n[*] Testing live call to {model_name}...")
        start_t = time.time()
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=APPRAISAL_SYSTEM,
                    response_mime_type="application/json",
                    response_schema=vertex_schema,
                    temperature=0.1,
                ),
            )
            elapsed = time.time() - start_t
            print(f"[+] Response received in {elapsed:.2f}s:")
            print("-" * 60)
            print(response.text)
            print("-" * 60)
            
            # Validate JSON
            data = json.loads(response.text)
            assert "identification" in data, "Missing required field: identification"
            assert "category" in data, "Missing required field: category"
            assert "confidence" in data, "Missing required field: confidence"
            assert "questions" in data, "Missing required field: questions"
            
            appraisal = Appraisal(
                lot_id="TEST-001",
                category=data["category"],
                identification=data["identification"],
                confidence=Confidence(data.get("confidence", "medium")),
                est_value_hint=float(data.get("value_magnitude_hint") or 0.0),
            )
            print(f"[✓] Successfully parsed into Appraisal dataclass: {appraisal}")
            print(f"[✓] Questions emitted: {len(data.get('questions', []))}")
            for q in data.get("questions", []):
                print(f"    - [{q.get('kind')}]: {q.get('prompt')}")
                
            print(f"\n[★] PASS: Model {model_name} successfully passed the Vertex Live Gate!")
            success = True
            break
        except Exception as e:
            print(f"[-] Model {model_name} failed: {e}")
            
    if not success:
        print("\n[!] All candidate models failed live gate.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
