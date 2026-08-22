"""Puzzle assignment: every photo is a node. Caption numbers constrain; everything else proposes."""

from dataclasses import dataclass
from src.intake.manifest import TriagedPhoto, lot_number_from

GENERIC_CATEGORIES = frozenset({"other", "unsorted", "general estate", ""})


@dataclass(frozen=True)
class Cluster:
    cluster_id: str
    photo_ids: tuple[str, ...]


def cannot_link(photos: list[TriagedPhoto]) -> set[frozenset[str]]:
    numbered = [(p.photo_id, lot_number_from(p.caption)) for p in photos]
    out: set[frozenset[str]] = set()
    for i, (a, na) in enumerate(numbered):
        if na is None:
            continue
        for b, nb in numbered[i + 1:]:
            if nb is not None and na != nb:
                out.add(frozenset({a, b}))
    return out


def seed_clusters(photos: list[TriagedPhoto]) -> list[Cluster]:
    by_num: dict[str, list[str]] = {}
    singles: list[str] = []
    for p in photos:
        n = lot_number_from(p.caption)
        if n is None:
            singles.append(p.photo_id)
        else:
            by_num.setdefault(n, []).append(p.photo_id)
    clusters = [Cluster(cluster_id=num, photo_ids=tuple(ids))
                for num, ids in by_num.items()]
    clusters.extend(Cluster(cluster_id=f"seq:{pid}", photo_ids=(pid,))
                    for pid in singles)
    return clusters
