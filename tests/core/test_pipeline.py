from src.blue_toad.processing.models import PhotoPiece
from src.blue_toad.processing.pipeline import run_puzzle


def P(pid, caption=""):
    return PhotoPiece(
        photo_id=pid, cycle_id="c", sequence=0, caption=caption,
        source_object=pid, source_generation="1", image_sha256=pid,
    )


def test_run_puzzle_partitions_every_piece():
    state = run_puzzle(
        [P("a"), P("b"), P("c")],
        proposal_edges={frozenset({"a", "b"})},
        identify=lambda ids: {pid: ("x", "other") for pid in ids},
    )
    assigned = [pid for c in state.clusters for pid in c.member_photo_ids]
    assert sorted(assigned) == ["a", "b", "c"]
    assert state.complete is True
