"""Puzzle loop: every photo is assigned exactly once. Caption numbers constrain; proposals merge."""

from __future__ import annotations

from collections.abc import Callable

from src.blue_toad.processing.constraints import (
    cannot_link,
    lot_number_from,
    must_link_pairs,
    seed_clusters,
)
from src.blue_toad.processing.models import ItemCluster, PhotoPiece, PuzzleState

GENERIC_CATEGORIES = frozenset({"other", "unsorted", "general estate", ""})


def _item_cluster(cluster_id: str, member_photo_ids: tuple[str, ...]) -> ItemCluster:
    return ItemCluster(
        cluster_id=cluster_id,
        member_photo_ids=member_photo_ids,
        identity="",
        sale_unit="unknown",
        conflicts=(),
        confidence=0.0,
        revision=1,
    )


def identities_mixed(members: list[tuple[str, str]]) -> bool:
    specific: set[str] = set()
    for _identification, category in members:
        cat = (category or "").casefold()
        if cat and cat not in GENERIC_CATEGORIES:
            specific.add(cat)
    return len(specific) > 1


def _lot_of(pieces: list[PhotoPiece]) -> dict[str, str | None]:
    return {p.photo_id: lot_number_from(p.caption) for p in pieces}


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
    cluster: ItemCluster,
    per_photo: dict[str, tuple[str, str]],
    must_together: set[frozenset[str]],
) -> list[ItemCluster]:
    members = [per_photo.get(pid, ("", "")) for pid in cluster.member_photo_ids]
    if not identities_mixed(members) or _must_covers_all(cluster.member_photo_ids, must_together):
        return [cluster]

    parent = {p: p for p in cluster.member_photo_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    id_set = set(cluster.member_photo_ids)
    for edge in must_together:
        if len(edge) == 2 and edge <= id_set:
            a, b = tuple(edge)
            union(a, b)

    by_cat: dict[str, list[str]] = {}
    for pid in cluster.member_photo_ids:
        _ident, category = per_photo.get(pid, ("", ""))
        cat = (category or "").casefold()
        if cat and cat not in GENERIC_CATEGORIES:
            by_cat.setdefault(cat, []).append(pid)
    for group in by_cat.values():
        for pid in group[1:]:
            union(group[0], pid)

    buckets: dict[str, list[str]] = {}
    order: list[str] = []
    for pid in cluster.member_photo_ids:
        root = find(pid)
        if root not in buckets:
            buckets[root] = []
            order.append(root)
        buckets[root].append(pid)
    if len(order) == 1:
        return [cluster]
    return [
        _item_cluster(f"seq:{buckets[r][0]}", tuple(buckets[r]))
        for r in order
    ]


def _merge_clusters(
    clusters: list[ItemCluster],
    edges: set[frozenset[str]],
    blocked: set[frozenset[str]],
    lot_of: dict[str, str | None],
) -> list[ItemCluster]:
    if not clusters:
        return clusters
    unions: dict[ItemCluster, ItemCluster] = {c: c for c in clusters}

    def find(c: ItemCluster) -> ItemCluster:
        while unions[c] is not c:
            unions[c] = unions[unions[c]]
            c = unions[c]
        return c

    def group_of(photo_id: str) -> ItemCluster | None:
        for c in clusters:
            if photo_id in c.member_photo_ids:
                return c
        return None

    def component_ids(root: ItemCluster) -> list[str]:
        out: list[str] = []
        for c in clusters:
            if find(c) is not root:
                continue
            for pid in c.member_photo_ids:
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

    buckets: dict[ItemCluster, list[str]] = {}
    order: list[ItemCluster] = []
    for c in clusters:
        root = find(c)
        if root not in buckets:
            buckets[root] = []
            order.append(root)
        for pid in c.member_photo_ids:
            if pid not in buckets[root]:
                buckets[root].append(pid)
    return [
        _item_cluster(_cluster_id(tuple(buckets[root]), lot_of), tuple(buckets[root]))
        for root in order
    ]


def _membership(clusters: list[ItemCluster]) -> frozenset[frozenset[str]]:
    return frozenset(frozenset(c.member_photo_ids) for c in clusters)


def _puzzle_state(
    pieces: list[PhotoPiece],
    clusters: list[ItemCluster],
    *,
    iteration: int,
    stable_passes: int,
) -> PuzzleState:
    input_ids = [p.photo_id for p in pieces]
    assigned = [pid for c in clusters for pid in c.member_photo_ids]
    assigned_set = set(assigned)
    input_set = set(input_ids)
    assigned_photo_count = len(assigned_set)
    total_photo_count = len(input_ids)
    is_partition = assigned_set == input_set and len(assigned) == len(input_set)
    return PuzzleState(
        cycle_id=pieces[0].cycle_id if pieces else "",
        iteration=iteration,
        assigned_photo_count=assigned_photo_count,
        total_photo_count=total_photo_count,
        clusters=tuple(clusters),
        changed_edges=0,
        merges=0,
        splits=0,
        identity_changes=0,
        stable_passes=stable_passes,
        complete=assigned_photo_count == total_photo_count and is_partition,
    )


def puzzle_loop(
    pieces: list[PhotoPiece],
    *,
    proposal_edges: set[frozenset[str]],
    identify: Callable[[tuple[str, ...]], dict[str, tuple[str, str]]],
    max_rounds: int = 3,
) -> PuzzleState:
    clusters = seed_clusters(pieces)
    blocked = cannot_link(pieces)
    must = must_link_pairs(pieces)
    lot_of = _lot_of(pieces)
    edges = {e for e in proposal_edges if e not in blocked}

    identities: dict[str, tuple[str, str]] = {}
    identified: set[frozenset[str]] = set()

    def identify_missing(cs: list[ItemCluster]) -> None:
        for c in cs:
            key = frozenset(c.member_photo_ids)
            if key in identified:
                continue
            identities.update(identify(c.member_photo_ids))
            identified.add(key)

    halted = False
    iteration = 0
    for _ in range(max_rounds):
        iteration += 1
        snapshot = _membership(clusters)
        clusters = _merge_clusters(clusters, edges, blocked, lot_of)
        identify_missing(clusters)
        split: list[ItemCluster] = []
        for c in clusters:
            per_photo = {pid: identities.get(pid, ("", "")) for pid in c.member_photo_ids}
            split.extend(split_cluster(c, per_photo, must))
        clusters = [
            _item_cluster(_cluster_id(c.member_photo_ids, lot_of), c.member_photo_ids)
            for c in split
        ]
        if _membership(clusters) == snapshot:
            identify_missing(clusters)
            halted = True
            break

    if not halted:
        identify_missing(clusters)
    return _puzzle_state(
        pieces,
        clusters,
        iteration=iteration,
        stable_passes=1 if halted else 0,
    )
