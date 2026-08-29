# tests/core/test_models.py
from src.blue_toad.processing.models import (
    ItemCluster,
    MatchEdge,
    Observation,
    PhotoPiece,
    PuzzleState,
)


def test_photo_piece_is_frozen_and_carries_source_identity():
    piece = PhotoPiece(
        photo_id="p1",
        cycle_id="2026-08-22",
        sequence=1,
        caption="Lot 47 truck",
        source_object="input/images/p1.jpg",
        source_generation="1",
        image_sha256="abc",
    )
    assert piece.photo_id == "p1"
    try:
        piece.caption = "nope"
    except Exception:
        return
    raise AssertionError("PhotoPiece must be frozen")


def test_match_edge_relations_are_the_spec_set():
    edge = MatchEdge(
        photo_a="a",
        photo_b="b",
        relation="same_lot",
        score=0.9,
        evidence=("walk",),
        iteration=1,
    )
    assert edge.relation in {"same_item", "same_lot", "spatial_neighbor", "incompatible"}


def test_puzzle_state_complete_requires_full_assignment_fields():
    cluster = ItemCluster(
        cluster_id="seq:a",
        member_photo_ids=("a",),
        identity="",
        sale_unit="unknown",
        conflicts=(),
        confidence=0.0,
        revision=1,
    )
    state = PuzzleState(
        cycle_id="c1",
        iteration=1,
        assigned_photo_count=1,
        total_photo_count=1,
        clusters=(cluster,),
        changed_edges=0,
        merges=0,
        splits=0,
        identity_changes=0,
        stable_passes=1,
        complete=True,
    )
    assert state.complete is True
    assert state.assigned_photo_count == state.total_photo_count
