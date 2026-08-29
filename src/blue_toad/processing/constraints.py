"""Caption-derived must-link and cannot-link constraints for PhotoPiece."""

from __future__ import annotations

import re

from src.blue_toad.processing.models import ItemCluster, PhotoPiece

_LOT_NO = re.compile(r"(?:^|\b)(?:lot\s*#?\s*|#)(\d{1,4})\b", re.IGNORECASE)


def lot_number_from(caption: str) -> str | None:
    m = _LOT_NO.search(caption or "")
    return m.group(1) if m else None


def cannot_link(pieces: list[PhotoPiece]) -> set[frozenset[str]]:
    numbered = [(p.photo_id, lot_number_from(p.caption)) for p in pieces]
    out: set[frozenset[str]] = set()
    for i, (a, na) in enumerate(numbered):
        if na is None:
            continue
        for b, nb in numbered[i + 1 :]:
            if nb is not None and na != nb:
                out.add(frozenset({a, b}))
    return out


def seed_clusters(pieces: list[PhotoPiece]) -> list[ItemCluster]:
    by_num: dict[str, list[str]] = {}
    singles: list[str] = []
    for p in pieces:
        n = lot_number_from(p.caption)
        if n is None:
            singles.append(p.photo_id)
        else:
            by_num.setdefault(n, []).append(p.photo_id)
    clusters = [
        ItemCluster(
            cluster_id=num,
            member_photo_ids=tuple(ids),
            identity="",
            sale_unit="unknown",
            conflicts=(),
            confidence=0.0,
            revision=1,
        )
        for num, ids in by_num.items()
    ]
    clusters.extend(
        ItemCluster(
            cluster_id=f"seq:{pid}",
            member_photo_ids=(pid,),
            identity="",
            sale_unit="unknown",
            conflicts=(),
            confidence=0.0,
            revision=1,
        )
        for pid in singles
    )
    return clusters


def must_link_pairs(pieces: list[PhotoPiece]) -> set[frozenset[str]]:
    by_num: dict[str, list[str]] = {}
    for p in pieces:
        n = lot_number_from(p.caption)
        if n is not None:
            by_num.setdefault(n, []).append(p.photo_id)
    pairs: set[frozenset[str]] = set()
    for ids in by_num.values():
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                pairs.add(frozenset({a, b}))
    return pairs
