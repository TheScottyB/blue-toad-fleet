"""Read-only embedding cache. Never calls Vertex."""

import json
from pathlib import Path

from src.intake.spatial import reshoot_edges

# Process memo: GET / must not recompute 462×462 3072-d cosine every request.
# Keyed by cache path + mtime/size + id maps so a rewritten file recomputes.
_EDGE_MEMO: dict[tuple, set] = {}


def _canonical_id(
    key: str,
    photo_by_seq: dict[int, str],
    gallery_ids: dict[str, str] | None,
) -> str:
    """Seq-digit keys and gallery photo_ids both map into one grouping space."""
    if key.isdigit():
        n = int(key)
        if n in photo_by_seq:
            return photo_by_seq[n]
    if gallery_ids and key in gallery_ids:
        return gallery_ids[key]
    return key


def _as_vector(vec) -> list[float] | None:
    if not isinstance(vec, (list, tuple)) or not vec:
        return None
    try:
        return [float(x) for x in vec]
    except (TypeError, ValueError):
        return None


def load_vectors(
    cache_path,
    photo_by_seq: dict[int, str],
    gallery_ids: dict[str, str] | None = None,
) -> dict[str, list[float]]:
    """Load cached vectors. Missing file → {}.

    Seq-digit keys map through `photo_by_seq`. Gallery photo_id keys map
    through `gallery_ids` when given, otherwise are kept as-is. Never calls
    Vertex / embed_content.
    """
    path = Path(cache_path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("embedding cache is not a JSON object")
    out: dict[str, list[float]] = {}
    for key, vec in raw.items():
        parsed = _as_vector(vec)
        if parsed is None:
            continue
        out[_canonical_id(str(key), photo_by_seq, gallery_ids)] = parsed
    return out


def _memo_key(
    path: Path,
    photo_by_seq: dict[int, str],
    sequences: dict[str, int],
    gallery_ids: dict[str, str] | None,
) -> tuple | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (
        str(path.resolve()),
        st.st_mtime_ns,
        st.st_size,
        tuple(sorted(photo_by_seq.items())),
        tuple(sorted(sequences.items())),
        tuple(sorted((gallery_ids or {}).items())),
    )


def load_reshoot_edges(
    cache_path,
    photo_by_seq: dict[int, str],
    sequences: dict[str, int],
    gallery_ids: dict[str, str] | None = None,
) -> set:
    """Vectors + reshoot edges for the request path.

    Missing cache → empty (walk-only, no cosine). Present cache that maps to
    0 grouping keys, corrupt JSON, or mixed-length vectors → walk-only, log,
    no raise. Results are memoized per process by path mtime/size.
    """
    path = Path(cache_path)
    if not path.is_file():
        print("[!] embeddings cache missing or empty; walk-only grouping")
        return set()

    key = _memo_key(path, photo_by_seq, sequences, gallery_ids)
    if key is not None and key in _EDGE_MEMO:
        return _EDGE_MEMO[key]

    try:
        vectors = load_vectors(path, photo_by_seq, gallery_ids)
        vectors = {k: v for k, v in vectors.items() if k in sequences}
        if not vectors:
            print(
                "[!] embeddings cache present but contributed 0 vectors; "
                "walk-only grouping"
            )
            edges: set = set()
        else:
            lengths = {len(v) for v in vectors.values()}
            if len(lengths) != 1:
                raise ValueError(f"mixed-length vectors: {sorted(lengths)}")
            edges = reshoot_edges(vectors, sequences)
    except Exception as e:
        print(f"[!] Warning: Could not parse embedding cache: {e}")
        edges = set()

    if key is not None:
        _EDGE_MEMO[key] = edges
    return edges
