"""Puzzle assignment: every photo is a node. Caption numbers constrain; everything else proposes."""

from collections.abc import Callable
from dataclasses import dataclass

from src.intake.manifest import LotGroup, TriagedPhoto, lot_number_from

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


def walk_proposal_edges(photos: list[TriagedPhoto]) -> set[frozenset[str]]:
    blocked = cannot_link(photos)
    out: set[frozenset[str]] = set()
    for prev, curr in zip(photos, photos[1:]):
        if not curr.same_lot_as_previous:
            continue
        edge = frozenset({prev.photo_id, curr.photo_id})
        if edge not in blocked:
            out.add(edge)
    return out


def identities_mixed(members: list[tuple[str, str]]) -> bool:
    specific: set[str] = set()
    for _identification, category in members:
        cat = (category or "").casefold()
        if cat and cat not in GENERIC_CATEGORIES:
            specific.add(cat)
    return len(specific) > 1


def _caption_must_pairs(photos: list[TriagedPhoto]) -> set[frozenset[str]]:
    by_num: dict[str, list[str]] = {}
    for p in photos:
        n = lot_number_from(p.caption)
        if n is not None:
            by_num.setdefault(n, []).append(p.photo_id)
    pairs: set[frozenset[str]] = set()
    for ids in by_num.values():
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                pairs.add(frozenset({a, b}))
    return pairs


def _lot_of(photos: list[TriagedPhoto]) -> dict[str, str | None]:
    return {p.photo_id: lot_number_from(p.caption) for p in photos}


def _cluster_id(photo_ids: tuple[str, ...], lot_of: dict[str, str | None]) -> str:
    for pid in photo_ids:
        n = lot_of.get(pid)
        if n is not None:
            return n
    return f"seq:{photo_ids[0]}"


def _must_covers_all(photo_ids: tuple[str, ...], must_together: set[frozenset[str]]) -> bool:
    if len(photo_ids) <= 1:
        return True
    parent = {p: p for p in photo_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    id_set = set(photo_ids)
    for edge in must_together:
        if len(edge) != 2 or not edge <= id_set:
            continue
        a, b = tuple(edge)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    return len({find(p) for p in photo_ids}) == 1


def split_cluster(
    cluster: Cluster,
    per_photo: dict[str, tuple[str, str]],
    must_together: set[frozenset[str]],
) -> list[Cluster]:
    members = [per_photo.get(pid, ("", "")) for pid in cluster.photo_ids]
    if not identities_mixed(members) or _must_covers_all(cluster.photo_ids, must_together):
        return [cluster]

    parent = {p: p for p in cluster.photo_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    id_set = set(cluster.photo_ids)
    for edge in must_together:
        if len(edge) == 2 and edge <= id_set:
            a, b = tuple(edge)
            union(a, b)

    by_cat: dict[str, list[str]] = {}
    for pid in cluster.photo_ids:
        _ident, category = per_photo.get(pid, ("", ""))
        cat = (category or "").casefold()
        if cat and cat not in GENERIC_CATEGORIES:
            by_cat.setdefault(cat, []).append(pid)
    for group in by_cat.values():
        for pid in group[1:]:
            union(group[0], pid)

    buckets: dict[str, list[str]] = {}
    order: list[str] = []
    for pid in cluster.photo_ids:
        root = find(pid)
        if root not in buckets:
            buckets[root] = []
            order.append(root)
        buckets[root].append(pid)
    if len(order) == 1:
        return [cluster]
    return [
        Cluster(cluster_id=f"seq:{buckets[r][0]}", photo_ids=tuple(buckets[r]))
        for r in order
    ]


def _merge_clusters(
    clusters: list[Cluster],
    edges: set[frozenset[str]],
    blocked: set[frozenset[str]],
    lot_of: dict[str, str | None],
) -> list[Cluster]:
    if not clusters:
        return clusters
    unions: dict[Cluster, Cluster] = {c: c for c in clusters}

    def find(c: Cluster) -> Cluster:
        while unions[c] is not c:
            unions[c] = unions[unions[c]]
            c = unions[c]
        return c

    def group_of(photo_id: str) -> Cluster | None:
        for c in clusters:
            if photo_id in c.photo_ids:
                return c
        return None

    def component_ids(root: Cluster) -> list[str]:
        out: list[str] = []
        for c in clusters:
            if find(c) is not root:
                continue
            for pid in c.photo_ids:
                if pid not in out:
                    out.append(pid)
        return out

    for edge in sorted(edges, key=lambda e: tuple(sorted(e))):
        if len(edge) != 2:
            continue
        a, b = tuple(edge)
        ga, gb = group_of(a), group_of(b)
        if ga is None or gb is None:
            continue
        ra, rb = find(ga), find(gb)
        if ra is rb:
            continue
        ids_a, ids_b = component_ids(ra), component_ids(rb)
        if any(frozenset({x, y}) in blocked for x in ids_a for y in ids_b):
            continue
        earlier, later = (ra, rb) if ra.cluster_id <= rb.cluster_id else (rb, ra)
        unions[later] = earlier

    buckets: dict[Cluster, list[str]] = {}
    order: list[Cluster] = []
    for c in clusters:
        root = find(c)
        if root not in buckets:
            buckets[root] = []
            order.append(root)
        for pid in c.photo_ids:
            if pid not in buckets[root]:
                buckets[root].append(pid)
    return [
        Cluster(cluster_id=_cluster_id(tuple(buckets[root]), lot_of),
                photo_ids=tuple(buckets[root]))
        for root in order
    ]


def _membership(clusters: list[Cluster]) -> frozenset[frozenset[str]]:
    return frozenset(frozenset(c.photo_ids) for c in clusters)


def puzzle_loop(
    photos: list[TriagedPhoto],
    *,
    proposal_edges: set[frozenset[str]],
    identify: Callable[[tuple[str, ...]], dict[str, tuple[str, str]]],
    max_rounds: int = 3,
) -> list[Cluster]:
    clusters = seed_clusters(photos)
    blocked = cannot_link(photos)
    must = _caption_must_pairs(photos)
    lot_of = _lot_of(photos)
    edges = {e for e in proposal_edges if e not in blocked} | walk_proposal_edges(photos)

    identities: dict[str, tuple[str, str]] = {}
    identified: set[frozenset[str]] = set()

    def identify_missing(cs: list[Cluster]) -> None:
        for c in cs:
            key = frozenset(c.photo_ids)
            if key in identified:
                continue
            identities.update(identify(c.photo_ids))
            identified.add(key)

    halted = False
    for _ in range(max_rounds):
        snapshot = _membership(clusters)
        clusters = _merge_clusters(clusters, edges, blocked, lot_of)
        identify_missing(clusters)
        split: list[Cluster] = []
        for c in clusters:
            per_photo = {pid: identities.get(pid, ("", "")) for pid in c.photo_ids}
            split.extend(split_cluster(c, per_photo, must))
        clusters = [
            Cluster(_cluster_id(c.photo_ids, lot_of), c.photo_ids) for c in split
        ]
        if _membership(clusters) == snapshot:
            identify_missing(clusters)
            halted = True
            break

    if not halted:
        identify_missing(clusters)
    return clusters


def as_lot_groups(clusters: list[Cluster]) -> list[LotGroup]:
    return [LotGroup(lot_key=c.cluster_id, photo_ids=c.photo_ids) for c in clusters]

