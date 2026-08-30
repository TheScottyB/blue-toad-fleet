"""Puzzle assignment: every photo is a node. Caption numbers constrain; everything else proposes.

Thin adapter over `src.blue_toad.processing`: TriagedPhoto → PhotoPiece, ItemCluster → Cluster.
"""

from collections.abc import Callable
from dataclasses import dataclass

from src.blue_toad.processing.constraints import cannot_link as _core_cannot_link
from src.blue_toad.processing.constraints import seed_clusters as _core_seed_clusters
from src.blue_toad.processing.models import ItemCluster, PhotoPiece
from src.blue_toad.processing.puzzle import (
    GENERIC_CATEGORIES,
    identities_mixed,
    puzzle_loop as _core_puzzle_loop,
    split_cluster as _core_split_cluster,
)
from src.intake.manifest import LotGroup, TriagedPhoto


@dataclass(frozen=True)
class Cluster:
    cluster_id: str
    photo_ids: tuple[str, ...]


def _to_piece(photo: TriagedPhoto) -> PhotoPiece:
    return PhotoPiece(
        photo_id=photo.photo_id,
        cycle_id="aug22",
        sequence=photo.sequence,
        caption=photo.caption,
        source_object=photo.photo_id,
        source_generation="0",
        image_sha256="",
    )


def _to_pieces(photos: list[TriagedPhoto]) -> list[PhotoPiece]:
    return [_to_piece(p) for p in photos]


def _to_cluster(cluster: ItemCluster) -> Cluster:
    return Cluster(cluster_id=cluster.cluster_id, photo_ids=cluster.member_photo_ids)


def _to_item_cluster(cluster: Cluster) -> ItemCluster:
    return ItemCluster(
        cluster_id=cluster.cluster_id,
        member_photo_ids=cluster.photo_ids,
        identity="",
        sale_unit="unknown",
        conflicts=(),
        confidence=0.0,
        revision=1,
    )


def cannot_link(photos: list[TriagedPhoto]) -> set[frozenset[str]]:
    return _core_cannot_link(_to_pieces(photos))


def seed_clusters(photos: list[TriagedPhoto]) -> list[Cluster]:
    return [_to_cluster(c) for c in _core_seed_clusters(_to_pieces(photos))]


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


def split_cluster(
    cluster: Cluster,
    per_photo: dict[str, tuple[str, str]],
    must_together: set[frozenset[str]],
) -> list[Cluster]:
    return [
        _to_cluster(c)
        for c in _core_split_cluster(_to_item_cluster(cluster), per_photo, must_together)
    ]


def puzzle_loop(
    photos: list[TriagedPhoto],
    *,
    proposal_edges: set[frozenset[str]],
    identify: Callable[[tuple[str, ...]], dict[str, tuple[str, str]]],
    max_rounds: int = 3,
) -> list[Cluster]:
    pieces = _to_pieces(photos)
    edges = proposal_edges | walk_proposal_edges(photos)
    state = _core_puzzle_loop(
        pieces,
        proposal_edges=edges,
        identify=identify,
        max_rounds=max_rounds,
    )
    return [_to_cluster(c) for c in state.clusters]


def as_lot_groups(clusters: list[Cluster]) -> list[LotGroup]:
    return [LotGroup(lot_key=c.cluster_id, photo_ids=c.photo_ids) for c in clusters]
