# tests/core/test_constraints.py
from src.blue_toad.processing.constraints import (
    cannot_link,
    lot_number_from,
    must_link_pairs,
    seed_clusters,
)
from src.blue_toad.processing.models import PhotoPiece


def P(pid, caption="", seq=0):
    return PhotoPiece(
        photo_id=pid,
        cycle_id="c",
        sequence=seq,
        caption=caption,
        source_object=pid,
        source_generation="1",
        image_sha256=pid,
    )


def test_lot_number_from_matches_blue_toad_captions():
    assert lot_number_from("Lot 47 truck") == "47"
    assert lot_number_from("#12 glass") == "12"
    assert lot_number_from("uncaptioned extra") is None


def test_uncaptioned_photos_start_as_singletons():
    cs = seed_clusters([P("a"), P("b")])
    assert sorted(c.member_photo_ids for c in cs) == [("a",), ("b",)]


def test_same_caption_lot_number_is_must_link():
    cs = seed_clusters([
        P("a", "Lot 47 truck"),
        P("b", "Lot 12 glass"),
        P("c", "Lot 47 reverse"),
    ])
    by = {frozenset(c.member_photo_ids): c for c in cs}
    assert frozenset({"a", "c"}) in by
    assert frozenset({"b"}) in by
    assert frozenset({"a", "c"}) in must_link_pairs([
        P("a", "Lot 47 truck"),
        P("c", "Lot 47 reverse"),
    ])


def test_different_lot_numbers_are_cannot_link():
    pieces = [P("a", "Lot 47 truck"), P("b", "Lot 48 trumpet")]
    assert frozenset({"a", "b"}) in cannot_link(pieces)
