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
