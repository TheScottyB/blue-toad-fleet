"""Read-only embedding cache. Never calls Vertex."""

import json
from pathlib import Path


def load_vectors(
    cache_path, photo_by_seq: dict[int, str],
) -> dict[str, list[float]]:
    """Load cached vectors. Missing file → {}. Seq-digit keys map through photo_by_seq."""
    path = Path(cache_path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text())
    out: dict[str, list[float]] = {}
    for key, vec in raw.items():
        k = str(key)
        # Gallery photo_ids are also digits; only seq keys exist in photo_by_seq.
        if k.isdigit() and int(k) in photo_by_seq:
            pid = photo_by_seq[int(k)]
        else:
            pid = k
        out[pid] = list(vec)
    return out
