"""Photos must collapse into lots before anything bids.

An auction gallery carries several photos of the same physical lot. The triage
schema already asks the model `same_lot_as_previous`, but nothing read the
answer, so two angles of one shelf became two independent Lots — separately
priced, separately budgeted, and both bid. On a real absentee sheet that is a
duplicate bid with real money behind it.
"""
import pytest

from src.intake.manifest import (
    LotGroup, TriagedPhoto, group_into_lots, parse_drop,
)


def photo(pid, caption="", is_lot=True, same=False):
    return TriagedPhoto(photo_id=pid, caption=caption,
                        is_lot=is_lot, same_lot_as_previous=same)


def test_two_angles_of_one_lot_become_one_group():
    groups = group_into_lots([
        photo("p1", "Pressed steel Tonka crane"),
        photo("p2", "another angle", same=True),
    ])
    assert len(groups) == 1
    assert groups[0].photo_ids == ("p1", "p2")


def test_distinct_lots_stay_separate():
    groups = group_into_lots([
        photo("p1", "Tonka crane"),
        photo("p2", "Waterford crystal bowl"),
    ])
    assert len(groups) == 2


def test_explicit_lot_numbers_merge_regardless_of_order():
    """The auction house's own lot number is ground truth and order-independent.

    A gallery that interleaves lots must still collapse to one group per lot.
    """
    groups = group_into_lots([
        photo("p1", "Lot 47 pressed steel truck"),
        photo("p2", "Lot 12 carnival glass"),
        photo("p3", "Lot 47 reverse side"),
    ])
    by_key = {g.lot_key: g for g in groups}
    assert len(groups) == 2
    assert by_key["47"].photo_ids == ("p1", "p3")
    assert by_key["12"].photo_ids == ("p2",)


def test_explicit_lot_number_beats_a_wrong_same_lot_flag():
    """A model slip must not merge two lots the auctioneer numbered apart."""
    groups = group_into_lots([
        photo("p1", "Lot 47 truck"),
        photo("p2", "Lot 48 trumpet", same=True),
    ])
    assert len(groups) == 2


def test_filler_photos_are_not_lots():
    """Signage and gallery filler must never reach the bid sheet."""
    groups = group_into_lots([
        photo("p1", "Tonka crane"),
        photo("p2", "Blue Toad Auctions banner", is_lot=False),
    ])
    assert len(groups) == 1
    assert groups[0].photo_ids == ("p1",)


def test_non_lot_photo_flagged_same_as_previous_still_attaches():
    """A duplicate angle is is_lot=False AND same_lot_as_previous=True.

    It is not its own lot, but it is evidence about the previous one, so it
    belongs in that group rather than being dropped.
    """
    groups = group_into_lots([
        photo("p1", "Tonka crane"),
        photo("p2", "closer angle", is_lot=False, same=True),
    ])
    assert len(groups) == 1
    assert groups[0].photo_ids == ("p1", "p2")


def test_first_photo_flagged_same_as_previous_is_its_own_lot():
    """There is no previous photo to attach to — must not crash or drop it."""
    groups = group_into_lots([photo("p1", "Tonka crane", same=True)])
    assert len(groups) == 1
    assert groups[0].photo_ids == ("p1",)


def test_empty_input_yields_no_groups():
    assert group_into_lots([]) == []


def test_group_exposes_a_primary_photo():
    groups = group_into_lots([
        photo("p1", "Tonka crane"),
        photo("p2", "angle", same=True),
    ])
    assert groups[0].primary_photo_id == "p1"


def test_one_group_per_physical_lot_is_the_whole_point():
    """Regression guard: N photos of one lot must yield exactly one bid slot."""
    groups = group_into_lots([
        photo("p1", "Lot 3 Fisher-Price circus train"),
        photo("p2", "Lot 3 detail", same=True),
        photo("p3", "Lot 3 box", same=True),
        photo("p4", "Lot 3 underside"),
    ])
    assert len(groups) == 1
    assert len(groups[0].photo_ids) == 4


def test_photos_sort_numerically_not_lexicographically():
    """`same_lot_as_previous` is sequence-dependent, so drop order must be right.

    Lexicographic sort puts fp10 before fp9 and silently rewires which photo is
    'previous', corrupting every merge decision downstream.
    """
    entries = [{"name": f"fp{n}.jpg", "uri": f"gs://b/fp{n}.jpg"} for n in (10, 9, 1)]
    drop = parse_drop("cycle-1", "listing-1", entries)
    assert [p.photo_id for p in drop.photos] == ["fp1", "fp9", "fp10"]
