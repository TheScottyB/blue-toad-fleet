#!/usr/bin/env python3
"""Dump every Slice A reshoot edge. Not CI. Eyeball before a live sheet."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intake.embed import load_vectors
from src.intake.spatial import SANITY_FLOOR, cosine, reshoot_edges

DATA = ROOT / "data" / "aug22_gallery_4160518"
MANIFEST = DATA / "manifest.json"
CACHE = DATA / "embeddings.json"


def main() -> int:
    if not CACHE.is_file():
        print(f"missing embedding cache: {CACHE}")
        return 0

    manifest = json.loads(MANIFEST.read_text())
    photos = manifest["photos"]
    photo_by_seq = {p["sequence"]: p["photo_id"] for p in photos}
    sequences = {p["photo_id"]: p["sequence"] for p in photos}

    vectors = load_vectors(CACHE, photo_by_seq)
    if not vectors:
        print(f"missing embedding cache: {CACHE}")
        return 0

    vectors = {k: v for k, v in vectors.items() if k in sequences}
    edges = reshoot_edges(vectors, sequences)

    print(
        f"Slice A reshoot edges | SANITY_FLOOR={SANITY_FLOOR} | "
        f"scoped nn (exclude walk-adjacent) | {len(edges)} edges"
    )
    print("seq_a seq_b gap cosine photo_a photo_b")

    rows = []
    for edge in edges:
        a, b = edge
        sa, sb = sequences[a], sequences[b]
        if sa > sb:
            a, b, sa, sb = b, a, sb, sa
        gap = sb - sa
        cos = cosine(vectors[a], vectors[b])
        rows.append((gap, sa, sb, cos, a, b))

    rows.sort(key=lambda r: (-r[0], r[1], r[2]))
    for gap, sa, sb, cos, a, b in rows:
        print(f"{sa} {sb} {gap} {cos:.6f} {a} {b}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
