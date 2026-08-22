#!/usr/bin/env python3
"""One-time Vertex embed of a gallery drop.

Cloud Run GET / never calls this. It writes embeddings.json next to the
manifest so load_reshoot_edges can fire return-pass merges (seq 2 ↔ 181).

One image per embed_content call — a list of images fuses to one vector.
Resume-safe: existing photo_ids are skipped. 429 backs off.

    GOOGLE_CLOUD_PROJECT=threebatdrone-prod-420 \\
      .venv/bin/python scripts/embed_gallery.py data/aug22_gallery_4160518
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.appraiser.images import image_mime_type, read_local_image
from src.intake.embed import (
    EMBED_MODEL, load_vectors, publish_embedding_pair, sha256_file, sidecar_path,
)
from src.intake.spatial import reshoot_edges

def _client(project: str, location: str):
    from google import genai
    return genai.Client(vertexai=True, project=project, location=location)


def embed_one(client, data: bytes) -> list[float]:
    from google.genai import types
    mime = image_mime_type(data) or "image/jpeg"
    delay = 2.0
    last = None
    for _ in range(8):
        try:
            resp = client.models.embed_content(
                model=EMBED_MODEL,
                contents=types.Part.from_bytes(data=data, mime_type=mime),
            )
            values = resp.embeddings[0].values
            return [float(x) for x in values]
        except Exception as e:
            last = e
            msg = str(e)
            if "429" not in msg and "RESOURCE_EXHAUSTED" not in msg:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)
    raise last


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "data_dir",
        nargs="?",
        default="data/aug22_gallery_4160518",
    )
    parser.add_argument("--force", action="store_true",
                        help="re-embed photo_ids already in the cache")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    manifest = json.loads((data_dir / "manifest.json").read_text())
    photos = manifest["photos"]
    cache_path = data_dir / "embeddings.json"
    photo_by_seq = {p["sequence"]: p["photo_id"] for p in photos}

    existing = load_vectors(cache_path, photo_by_seq) if not args.force else {}
    print(f"cache {cache_path}  {len(existing)} existing  {len(photos)} photos")

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "threebatdrone-prod-420")
    location = os.environ.get("VERTEX_LOCATION", "global")
    todo = [
        p for p in photos
        if args.force or p["photo_id"] not in existing
    ]
    skipped = 0
    done = 0
    t0 = time.time()
    if not todo:
        print("embedding pair already covers the manifest; leaving review revision unchanged")
        return 0
    client = _client(project, location)
    for i, p in enumerate(todo, 1):
        local = p.get("local_path") or ""
        data = read_local_image(local)
        if not data:
            print(f"[skip] seq {p['sequence']} missing {local}")
            skipped += 1
            continue
        vec = embed_one(client, data)
        existing[p["photo_id"]] = vec
        done += 1
        if done % 10 == 0 or i == len(todo):
            elapsed = time.time() - t0
            print(
                f"[{i}/{len(todo)}] seq {p['sequence']}  "
                f"dim {len(vec)}  {elapsed:.0f}s  staged {len(existing)}",
                flush=True,
            )

    if skipped:
        print(f"[REFUSED] {skipped} requested photo(s) were missing; cache unchanged")
        return 2
    sequences = {p["photo_id"]: p["sequence"] for p in photos}
    mapped = {k: v for k, v in existing.items() if k in sequences}
    edges = reshoot_edges(mapped, sequences) if mapped else set()
    publish_embedding_pair(
        cache_path,
        mapped,
        edges,
        required_ids=set(sequences),
        manifest_sha256=sha256_file(data_dir / "manifest.json"),
        model=EMBED_MODEL,
    )
    print(f"wrote {cache_path}  {len(existing)} vectors  skipped {skipped}")
    print(f"wrote {sidecar_path(cache_path)}  {len(edges)} proposed edges (not approved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
