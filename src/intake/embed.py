"""Embedding cache publication and approved reshoot-edge loading."""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.intake.spatial import reshoot_edges

# Process memo: GET / must not recompute 462×462 3072-d cosine every request.
# Keyed by cache path + mtime/size + id maps so a rewritten file recomputes.
_EDGE_MEMO: dict[tuple, set] = {}
EMBEDDING_SCHEMA_VERSION = 2
EMBED_MODEL = "gemini-embedding-2"


@dataclass(frozen=True)
class ReviewedEdge:
    photo_ids: tuple[str, str]
    status: str = "proposed"
    reviewer: str | None = None
    reviewed_at: str | None = None
    evidence: str = "embedding mutual-nearest-neighbor proposal"
    revision: int = 1

    def __post_init__(self) -> None:
        if len(set(self.photo_ids)) != 2 or not all(self.photo_ids):
            raise ValueError("reviewed edge requires two distinct photo ids")
        if self.status not in {"proposed", "approved", "rejected"}:
            raise ValueError(f"invalid edge review status: {self.status}")
        if self.status != "proposed" and not (self.reviewer and self.reviewed_at):
            raise ValueError("reviewed edge requires reviewer and reviewed_at")
        if self.revision < 1:
            raise ValueError("edge revision must be positive")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def sidecar_path(cache_path) -> Path:
    return Path(cache_path).with_name("reshoot_edges.json")


def _stat_tuple(path: Path) -> tuple:
    try:
        st = path.stat()
    except OSError:
        return ("", 0, 0)
    return (str(path.resolve()), st.st_mtime_ns, st.st_size)


def _memo_key(
    path: Path,
    sidecar: Path,
    photo_by_seq: dict[int, str],
    sequences: dict[str, int],
    gallery_ids: dict[str, str] | None,
) -> tuple | None:
    vec_t = _stat_tuple(path)
    side_t = _stat_tuple(sidecar)
    if vec_t[1] == 0 and side_t[1] == 0:
        return None
    return (
        vec_t,
        side_t,
        tuple(sorted(photo_by_seq.items())),
        tuple(sorted(sequences.items())),
        tuple(sorted((gallery_ids or {}).items())),
    )


def dump_reshoot_edges(
    cache_path,
    edges: set,
    *,
    status: str = "proposed",
    reviewer: str | None = None,
    reviewed_at: str | None = None,
    evidence: str = "embedding mutual-nearest-neighbor proposal",
    model: str = EMBED_MODEL,
    manifest_sha256: str | None = None,
    vector_sha256: str | None = None,
) -> None:
    """Write reviewed/proposed edge records. Production consumes approved only."""
    path = sidecar_path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    reviewed_at = reviewed_at or (
        datetime.now(timezone.utc).isoformat() if status != "proposed" else None)
    records = [
        ReviewedEdge(
            photo_ids=tuple(sorted(str(value) for value in edge)),
            status=status,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
            evidence=evidence,
        )
        for edge in sorted(edges, key=lambda value: sorted(value))
        if len(edge) == 2
    ]
    cache = Path(cache_path)
    if vector_sha256 is None and cache.is_file():
        vector_sha256 = sha256_file(cache)
    payload = {
        "schema_version": EMBEDDING_SCHEMA_VERSION,
        "model": model,
        "manifest_sha256": manifest_sha256,
        "vector_sha256": vector_sha256,
        "edges": [asdict(record) for record in records],
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def _edges_from_sidecar(
    sidecar: Path,
    cache_path: Path,
    photo_by_seq: dict[int, str],
    sequences: dict[str, int],
    gallery_ids: dict[str, str] | None,
    expected_model: str,
    expected_manifest_sha256: str | None,
) -> set:
    raw = json.loads(sidecar.read_text())
    if not isinstance(raw, dict) or raw.get("schema_version") != EMBEDDING_SCHEMA_VERSION:
        raise ValueError("legacy/unversioned reshoot edges are not operator-approved")
    if raw.get("model") != expected_model:
        raise ValueError("reshoot edge model identity is stale")
    if expected_manifest_sha256 and raw.get("manifest_sha256") != expected_manifest_sha256:
        raise ValueError("reshoot edge manifest identity is stale")
    if not cache_path.is_file():
        raise ValueError("approved edge record has no verifiable vector cache")
    if raw.get("vector_sha256") != sha256_file(cache_path):
        raise ValueError("reshoot edge vector identity is stale")
    records = raw.get("edges")
    if not isinstance(records, list):
        raise ValueError("reshoot_edges sidecar has no edge records")
    out: set = set()
    for record in records:
        if not isinstance(record, dict) or record.get("status") != "approved":
            continue
        pair = record.get("photo_ids")
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        if not all((record.get("reviewer"), record.get("reviewed_at"),
                    record.get("evidence"), record.get("revision"))):
            continue
        a = _canonical_id(str(pair[0]), photo_by_seq, gallery_ids)
        b = _canonical_id(str(pair[1]), photo_by_seq, gallery_ids)
        if a in sequences and b in sequences and a != b:
            out.add(frozenset({a, b}))
    return out


def load_reshoot_edges(
    cache_path,
    photo_by_seq: dict[int, str],
    sequences: dict[str, int],
    gallery_ids: dict[str, str] | None = None,
    *,
    expected_model: str = EMBED_MODEL,
    expected_manifest_sha256: str | None = None,
) -> set:
    """Vectors + reshoot edges for the request path.

    Prefers `reshoot_edges.json` next to the vector cache so GET / does not
    run 462×462 cosine. Missing both → empty (walk-only). Present cache that
    maps to 0 grouping keys, corrupt JSON, or mixed-length vectors →
    walk-only, log, no raise. Results are memoized per process by path
    mtime/size.
    """
    path = Path(cache_path)
    sidecar = sidecar_path(path)
    key = _memo_key(path, sidecar, photo_by_seq, sequences, gallery_ids)
    if key is not None and key in _EDGE_MEMO:
        return _EDGE_MEMO[key]

    edges: set | None = None
    if sidecar.is_file():
        try:
            edges = _edges_from_sidecar(
                sidecar, path, photo_by_seq, sequences, gallery_ids,
                expected_model, expected_manifest_sha256,
            )
        except Exception as e:
            print(f"[!] Warning: Could not parse reshoot_edges sidecar: {e}")
            edges = None

    if edges is None:
        # Computing proposals on the request path used to make every inferred
        # edge money-bearing without review. Missing/corrupt/unreviewed input is
        # now deliberately walk-only.
        print("[!] no current approved reshoot-edge revision; walk-only grouping")
        edges = set()

    if key is not None:
        _EDGE_MEMO[key] = edges
    return edges


def dump_vectors(cache_path, vectors: dict[str, list[float]]) -> None:
    """Atomic write of photo_id -> vector. Never called from GET /."""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        pid: [round(float(x), 6) for x in vec]
        for pid, vec in vectors.items()
        if _as_vector(vec) is not None
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def publish_embedding_pair(
    cache_path,
    vectors: dict[str, list[float]],
    edges: set[frozenset[str]],
    *,
    required_ids: set[str],
    manifest_sha256: str,
    model: str = EMBED_MODEL,
    after_vector_replace: Callable[[], None] | None = None,
) -> None:
    """Validate and replace the vector/proposal pair, rolling back on failure."""
    path = Path(cache_path)
    sidecar = sidecar_path(path)
    if set(vectors) != required_ids:
        missing = sorted(required_ids - set(vectors))
        extra = sorted(set(vectors) - required_ids)
        raise ValueError(f"embedding coverage mismatch: missing={missing[:5]} extra={extra[:5]}")
    dimensions = {len(vector) for vector in vectors.values() if _as_vector(vector)}
    if len(dimensions) != 1 or not dimensions or 0 in dimensions:
        raise ValueError(f"embedding dimensions are not uniform: {sorted(dimensions)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    vector_payload = {
        pid: [round(float(x), 6) for x in vectors[pid]]
        for pid in sorted(vectors)
    }
    vector_bytes = json.dumps(vector_payload, separators=(",", ":")).encode()
    vector_sha = hashlib.sha256(vector_bytes).hexdigest()
    records = [
        asdict(ReviewedEdge(photo_ids=tuple(sorted(edge))))
        for edge in sorted(edges, key=lambda value: sorted(value))
    ]
    edge_bytes = (json.dumps({
        "schema_version": EMBEDDING_SCHEMA_VERSION,
        "model": model,
        "manifest_sha256": manifest_sha256,
        "vector_sha256": vector_sha,
        "edges": records,
    }, indent=2) + "\n").encode()

    old_vector = path.read_bytes() if path.is_file() else None
    old_edges = sidecar.read_bytes() if sidecar.is_file() else None
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".embedding-pair-") as tmp:
        tmp_dir = Path(tmp)
        staged_vector = tmp_dir / path.name
        staged_edges = tmp_dir / sidecar.name
        staged_vector.write_bytes(vector_bytes)
        staged_edges.write_bytes(edge_bytes)
        try:
            os.replace(staged_vector, path)
            if after_vector_replace:
                after_vector_replace()
            os.replace(staged_edges, sidecar)
        except BaseException:
            if old_vector is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old_vector)
            if old_edges is None:
                sidecar.unlink(missing_ok=True)
            else:
                sidecar.write_bytes(old_edges)
            raise
