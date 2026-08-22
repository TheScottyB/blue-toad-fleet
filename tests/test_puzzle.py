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
