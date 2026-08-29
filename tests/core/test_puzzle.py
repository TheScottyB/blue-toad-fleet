# tests/core/test_puzzle.py
from src.blue_toad.processing.constraints import seed_clusters
from src.blue_toad.processing.models import PhotoPiece
from src.blue_toad.processing.puzzle import identities_mixed, puzzle_loop


def P(pid, caption="", seq=0):
    return PhotoPiece(
        photo_id=pid, cycle_id="c", sequence=seq, caption=caption,
        source_object=pid, source_generation="1", image_sha256=pid,
    )


def test_unmatched_photo_is_a_singleton_and_complete():
    state = puzzle_loop(
        [P("a"), P("b")],
        proposal_edges=set(),
        identify=lambda ids: {pid: ("x", "other") for pid in ids},
    )
    assert state.complete is True
    assert state.assigned_photo_count == 2
    assert state.total_photo_count == 2
    assert sorted(c.member_photo_ids for c in state.clusters) == [("a",), ("b",)]


def test_proposal_merges_then_stops():
    calls = []

    def identify(ids):
        calls.append(ids)
        return {pid: ("truck", "vintage toys") for pid in ids}

    state = puzzle_loop(
        [P("a", seq=1), P("b", seq=2)],
        proposal_edges={frozenset({"a", "b"})},
        identify=identify,
    )
    assert [c.member_photo_ids for c in state.clusters] == [("a", "b")]
    assert len(calls) <= 3


def test_mixed_unconstrained_photos_split():
    ids = {
        "a": ("costume jewelry", "jewelry"),
        "b": ("Edison cylinders", "phonograph / records"),
    }
    state = puzzle_loop(
        [P("a"), P("b")],
        proposal_edges={frozenset({"a", "b"})},
        identify=lambda pids: {p: ids[p] for p in pids},
    )
    assert sorted(c.member_photo_ids for c in state.clusters) == [("a",), ("b",)]


def test_cannot_link_blocks_a_proposal():
    state = puzzle_loop(
        [P("a", "Lot 47 truck"), P("b", "Lot 48 trumpet")],
        proposal_edges={frozenset({"a", "b"})},
        identify=lambda ids: {pid: ("x", "other") for pid in ids},
    )
    assert sorted(c.member_photo_ids for c in state.clusters) == [("a",), ("b",)]


def test_sorted_edges_make_the_uncaptioned_bridge_deterministic():
    """Uncaptioned B between Lot 1 and Lot 2: first sorted edge wins."""
    pieces = [
        P("A", "Lot 1 glass", seq=1),
        P("B", "", seq=2),
        P("C", "Lot 2 tray", seq=3),
    ]
    state = puzzle_loop(
        pieces,
        proposal_edges={frozenset({"A", "B"}), frozenset({"B", "C"})},
        identify=lambda ids: {pid: ("x", "other") for pid in ids},
    )
    groups = sorted(tuple(sorted(c.member_photo_ids)) for c in state.clusters)
    assert groups == [("A", "B"), ("C",)]


def test_jewelry_vs_edison_is_mixed():
    assert identities_mixed([
        ("costume jewelry tray", "jewelry"),
        ("Edison cylinder records", "phonograph / records"),
    ]) is True
