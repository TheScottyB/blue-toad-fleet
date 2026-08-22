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
