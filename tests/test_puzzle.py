from src.intake.manifest import TriagedPhoto
from src.intake.puzzle import cannot_link, seed_clusters


def P(pid, caption="", same=False, is_lot=True):
    return TriagedPhoto(photo_id=pid, caption=caption,
                        is_lot=is_lot, same_lot_as_previous=same)


class TestSeed:
    def test_uncaptioned_photos_start_as_singletons(self):
        cs = seed_clusters([P("a"), P("b")])
        assert sorted(c.photo_ids for c in cs) == [("a",), ("b",)]

    def test_same_caption_lot_number_is_must_link(self):
        cs = seed_clusters([
            P("a", "Lot 47 truck"),
            P("b", "Lot 12 glass"),
            P("c", "Lot 47 reverse"),
        ])
        by = {frozenset(c.photo_ids): c for c in cs}
        assert frozenset({"a", "c"}) in by
        assert frozenset({"b"}) in by

    def test_different_lot_numbers_are_cannot_link(self):
        photos = [P("a", "Lot 47 truck"), P("b", "Lot 48 trumpet")]
        assert frozenset({"a", "b"}) in cannot_link(photos)

    def test_walk_flag_does_not_seed_a_merge(self):
        """Walk is a proposal, not a constraint."""
        cs = seed_clusters([P("a", "truck"), P("b", "angle", same=True)])
        assert sorted(c.photo_ids for c in cs) == [("a",), ("b",)]


from src.intake.puzzle import (
    identities_mixed, puzzle_loop, split_cluster, walk_proposal_edges,
)


class TestProposalsAndSplit:
    def test_walk_flag_is_a_proposal_edge(self):
        photos = [P("a", "truck"), P("b", "angle", same=True)]
        assert frozenset({"a", "b"}) in walk_proposal_edges(photos)

    def test_cannot_link_blocks_a_walk_proposal(self):
        photos = [P("a", "Lot 47 truck"), P("b", "Lot 48 trumpet", same=True)]
        assert frozenset({"a", "b"}) not in walk_proposal_edges(photos)

    def test_jewelry_vs_edison_is_mixed(self):
        assert identities_mixed([
            ("costume jewelry tray", "jewelry"),
            ("Edison cylinder records", "phonograph / records"),
        ]) is True

    def test_two_other_categories_are_not_mixed(self):
        assert identities_mixed([
            ("box of smalls", "other"),
            ("another box", "other"),
        ]) is False

    def test_must_link_is_not_split(self):
        from src.intake.puzzle import Cluster
        c = Cluster("47", ("a", "b"))
        out = split_cluster(
            c,
            {"a": ("jewelry", "jewelry"), "b": ("edison", "phonograph / records")},
            must_together={frozenset({"a", "b"})},
        )
        assert out == [c]


class TestLoop:
    def test_walk_proposal_merges_then_stops(self):
        photos = [P("a", "truck"), P("b", "angle", same=True)]
        calls = []

        def identify(ids):
            calls.append(ids)
            return {pid: ("truck", "vintage toys") for pid in ids}

        out = puzzle_loop(photos, proposal_edges=walk_proposal_edges(photos),
                          identify=identify)
        assert [c.photo_ids for c in out] == [("a", "b")]
        assert len(calls) <= 3

    def test_mixed_unconstrained_photos_split(self):
        photos = [P("a"), P("b")]
        ids = {
            "a": ("costume jewelry", "jewelry"),
            "b": ("Edison cylinders", "phonograph / records"),
        }
        out = puzzle_loop(
            photos,
            proposal_edges={frozenset({"a", "b"})},
            identify=lambda pids: {p: ids[p] for p in pids},
        )
        assert sorted(c.photo_ids for c in out) == [("a",), ("b",)]

    def test_identity_rephrase_does_not_continue_the_loop(self):
        photos = [P("a", "truck")]
        n = {"i": 0}

        def identify(ids):
            n["i"] += 1
            return {pid: (f"truck pass {n['i']}", "vintage toys") for pid in ids}

        puzzle_loop(photos, proposal_edges=set(), identify=identify)
        assert n["i"] <= 2  # one identify on seed set + optional final; never 4

    def test_round_cap_is_three(self):
        photos = [P("a"), P("b"), P("c")]
        rounds = {"n": 0}

        def identify(ids):
            rounds["n"] += 1
            # always disagree so a naive loop would never halt
            return {pid: (pid, pid) for pid in ids}

        puzzle_loop(
            photos,
            proposal_edges={frozenset({"a", "b"}), frozenset({"b", "c"})},
            identify=identify, max_rounds=3,
        )
        assert rounds["n"] <= 4  # 3 rounds + final freeze identify


from src.assemble import AppraisedPhoto, assemble_lots
from src.intake.manifest import LotGroup


def test_assemble_accepts_precomputed_groups():
    photos = [
        AppraisedPhoto(photo_id="a", caption="x", identification="truck",
                       category="vintage toys", is_lot=True),
        AppraisedPhoto(photo_id="b", caption="y", identification="truck",
                       category="vintage toys", is_lot=True),
    ]
    groups = [LotGroup(lot_key="seq:a", photo_ids=("a", "b"))]
    lots = assemble_lots(photos, groups=groups)
    assert len(lots) == 1
    assert lots[0].lot_id == "seq:a"


def test_sidecar_is_not_a_price_cache():
    from src.assemble.grounded import load_grounded_prices
    from pathlib import Path
    p = Path("data/aug22_gallery_4160518/grounded_search_remaining.json")
    got = load_grounded_prices(p)
    assert got == {}

