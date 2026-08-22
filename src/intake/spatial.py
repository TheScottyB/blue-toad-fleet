"""Spatial Room Graph — surface signatures, zones, trajectory clustering.

The model names the surface and zone. This module clusters photos along the
auctioneer's walk so multi-angle and under-table runs become one lot.
"""
from dataclasses import dataclass
from enum import Enum

from src.intake.manifest import LotGroup, TriagedPhoto


class SurfaceSignature(str, Enum):
    BLUE_VINYL = "blue_vinyl"
    PINE_PLYWOOD = "pine_plywood"
    CONCRETE = "concrete"
    OTHER = "other"


class Zone(str, Enum):
    NORTH_BACK_WALL = "north_back_wall"
    WEST_SIDE_TABLES = "west_side_tables"
    CENTER_ISLAND_1 = "center_island_1"
    CENTER_ISLAND_2 = "center_island_2"
    EAST_SIDE_TABLES = "east_side_tables"
    SOUTH_UNDER_TABLE = "south_under_table"
    UNKNOWN = "unknown"


SURFACE_VALUES = [s.value for s in SurfaceSignature]
ZONE_VALUES = [z.value for z in Zone]


@dataclass(frozen=True)
class AdjacencyClaim:
    """'This photo's right edge shows the object in photo 47.'"""
    from_id: str
    edge: str
    to_id: str


@dataclass(frozen=True)
class PhotoObservation:
    """One photo as Step 0 saw it in the listing, not in isolation."""
    photo_id: str
    zone: Zone
    surface: SurfaceSignature
    caption: str = ""
    summary: str = ""
    is_lot: bool = True
    same_lot_as_previous: bool = False
    margin_neighbors: tuple[str, ...] = ()
    adjacencies: tuple[AdjacencyClaim, ...] = ()


@dataclass(frozen=True)
class SpatiallyTaggedPhoto:
    photo_id: str
    caption: str = ""
    summary: str = ""
    is_lot: bool = True
    same_lot_as_previous: bool = False
    surface: SurfaceSignature = SurfaceSignature.OTHER
    zone: Zone = Zone.UNKNOWN
    margin_neighbors: tuple[str, ...] = ()


def spatial_same_lot(
    prev: SpatiallyTaggedPhoto | None, curr: SpatiallyTaggedPhoto,
) -> bool:
    if prev is None:
        return False
    if curr.zone is Zone.UNKNOWN or prev.zone is Zone.UNKNOWN:
        return False
    if curr.zone is not prev.zone:
        return False
    if curr.same_lot_as_previous:
        return True
    uncaptioned = not curr.caption.strip()
    if uncaptioned and curr.surface is prev.surface:
        return True
    if uncaptioned and prev.summary.strip():
        blob = " ".join(curr.margin_neighbors).lower()
        if prev.summary.lower() in blob:
            return True
    return False


def apply_trajectory(photos: list[SpatiallyTaggedPhoto]) -> list[TriagedPhoto]:
    out: list[TriagedPhoto] = []
    prev: SpatiallyTaggedPhoto | None = None
    for p in photos:
        same = spatial_same_lot(prev, p)
        out.append(TriagedPhoto(
            photo_id=p.photo_id,
            caption=p.caption,
            is_lot=p.is_lot,
            same_lot_as_previous=same,
        ))
        prev = p
    return out


def adjacency_graph(obs: list[PhotoObservation]) -> dict[str, set[str]]:
    """Undirected neighbour map from explicit cross-photo claims."""
    g: dict[str, set[str]] = {o.photo_id: set() for o in obs}
    for o in obs:
        for claim in o.adjacencies:
            g.setdefault(claim.from_id, set()).add(claim.to_id)
            g.setdefault(claim.to_id, set()).add(claim.from_id)
    return g


def observations_to_tagged(obs: list[PhotoObservation]) -> list[SpatiallyTaggedPhoto]:
    return [
        SpatiallyTaggedPhoto(
            photo_id=o.photo_id,
            caption=o.caption,
            summary=o.summary,
            is_lot=o.is_lot,
            same_lot_as_previous=o.same_lot_as_previous,
            surface=o.surface,
            zone=o.zone,
            margin_neighbors=o.margin_neighbors,
        )
        for o in obs
    ]


LISTING_GRAPH_SCHEMA = {
    "type": "object",
    "properties": {
        "photos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "photo_id": {"type": "string"},
                    "zone": {"type": "string", "enum": ZONE_VALUES},
                    "surface_signature": {"type": "string", "enum": SURFACE_VALUES},
                    "margin_neighbors": {"type": "array", "items": {"type": "string"}},
                    "adjacencies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from_id": {"type": "string"},
                                "edge": {
                                    "type": "string",
                                    "enum": ["left", "right", "behind", "below", "above"],
                                },
                                "to_id": {"type": "string"},
                            },
                            "required": ["from_id", "edge", "to_id"],
                        },
                    },
                },
                "required": ["photo_id", "zone", "surface_signature",
                             "margin_neighbors", "adjacencies"],
            },
        },
    },
    "required": ["photos"],
}


def occupancy(
    photos: list[SpatiallyTaggedPhoto], groups: list[LotGroup],
) -> dict[Zone, list[str]]:
    by_id = {p.photo_id: p for p in photos}
    occ: dict[Zone, list[str]] = {z: [] for z in Zone}
    for g in groups:
        primary = by_id.get(g.primary_photo_id)
        zone = primary.zone if primary is not None else Zone.UNKNOWN
        occ[zone].append(g.lot_key)
    return occ


SANITY_FLOOR = 0.80


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _walk_adjacent(i: str, j: str, sequences: dict[str, int]) -> bool:
    return abs(sequences[i] - sequences[j]) == 1


def nearest_neighbor(
    photo_id: str,
    vectors: dict[str, tuple | list],
    sequences: dict[str, int],
    *,
    exclude_walk_adjacent: bool = True,
) -> str | None:
    best_id, best, tied = None, None, False
    for other, vec in vectors.items():
        if other == photo_id:
            continue
        if exclude_walk_adjacent and _walk_adjacent(photo_id, other, sequences):
            continue
        c = cosine(vectors[photo_id], vec)
        if best is None or c > best:
            best_id, best, tied = other, c, False
        elif c == best:
            tied = True
    if tied or best is None:
        return None
    return best_id


def reshoot_edges(
    vectors: dict[str, tuple | list],
    sequences: dict[str, int],
) -> set[frozenset[str]]:
    # nn consults sequences[id]; extra cache keys (or a photo_id/BT mix) must
    # not KeyError or steal the argmax. Same filter as list_reshoot_edges.
    vectors = {k: v for k, v in vectors.items() if k in sequences}
    edges: set[frozenset[str]] = set()
    for i in vectors:
        j = nearest_neighbor(i, vectors, sequences)
        if j is None:
            continue
        if nearest_neighbor(j, vectors, sequences) != i:
            continue
        if cosine(vectors[i], vectors[j]) < SANITY_FLOOR:
            continue
        edges.add(frozenset({i, j}))
    return edges


def merge_reshoots(
    groups: list[LotGroup],
    edges: set[frozenset[str]],
) -> list[LotGroup]:
    parent = {id(g): g for g in groups}

    def group_of(photo_id: str) -> LotGroup | None:
        for g in groups:
            if photo_id in g.photo_ids:
                return g
        return None

    unions: dict[LotGroup, LotGroup] = {g: g for g in groups}

    def find(g: LotGroup) -> LotGroup:
        while unions[g] is not g:
            unions[g] = unions[unions[g]]
            g = unions[g]
        return g

    for edge in edges:
        a, b = tuple(edge)
        ga, gb = group_of(a), group_of(b)
        if ga is None or gb is None:
            continue
        ra, rb = find(ga), find(gb)
        if ra is rb:
            continue
        earlier, later = (ra, rb) if ra.lot_key <= rb.lot_key else (rb, ra)
        unions[later] = earlier

    buckets: dict[LotGroup, list[str]] = {}
    order: list[LotGroup] = []
    for g in groups:
        root = find(g)
        if root not in buckets:
            buckets[root] = []
            order.append(root)
        for pid in g.photo_ids:
            if pid not in buckets[root]:
                buckets[root].append(pid)
    return [
        LotGroup(lot_key=root.lot_key, photo_ids=tuple(buckets[root]))
        for root in order
    ]


@dataclass(frozen=True)
class Seat:
    lot_id: str
    zone: Zone
    walk_index: int
    photo_ids: tuple[str, ...]


def seats_from_groups(
    groups: list[LotGroup],
    sequences: dict[str, int],
    zones: dict[str, Zone] | None = None,
) -> list[Seat]:
    zones = zones or {}
    seats = []
    for g in groups:
        walk = min(sequences.get(pid, 10**9) for pid in g.photo_ids)
        zone = zones.get(g.lot_key, Zone.UNKNOWN)
        seats.append(Seat(
            lot_id=g.lot_key, zone=zone, walk_index=walk,
            photo_ids=g.photo_ids,
        ))
    seats.sort(key=lambda s: s.walk_index)
    return seats
