from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Relation = Literal["same_item", "same_lot", "spatial_neighbor", "incompatible"]


@dataclass(frozen=True)
class PhotoPiece:
    photo_id: str
    cycle_id: str
    sequence: int
    caption: str
    source_object: str
    source_generation: str
    image_sha256: str


@dataclass(frozen=True)
class Observation:
    photo_id: str
    detected_objects: tuple[str, ...]
    visible_text: tuple[str, ...]
    visual_embedding: tuple[float, ...]
    scene_features: tuple[str, ...]
    viewpoint: str
    visible_marks: tuple[str, ...]
    visible_condition: tuple[str, ...]


@dataclass(frozen=True)
class MatchEdge:
    photo_a: str
    photo_b: str
    relation: Relation
    score: float
    evidence: tuple[str, ...]
    iteration: int


@dataclass(frozen=True)
class ItemCluster:
    cluster_id: str
    member_photo_ids: tuple[str, ...]
    identity: str
    sale_unit: str
    conflicts: tuple[str, ...]
    confidence: float
    revision: int


@dataclass(frozen=True)
class PuzzleState:
    cycle_id: str
    iteration: int
    assigned_photo_count: int
    total_photo_count: int
    clusters: tuple[ItemCluster, ...]
    changed_edges: int
    merges: int
    splits: int
    identity_changes: int
    stable_passes: int
    complete: bool
