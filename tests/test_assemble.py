"""Turning appraised photos into priceable lots.

This is the layer that was missing entirely: `Lot` objects existed only in
hand-authored demo seed JSON, so nothing connected triage output to the bid
sheet. The merge rules here decide real money, so each one is pinned.

The governing bias is conservative. An absentee sheet is committed before the
auctioneer opens the floor; an optimistic merge is discovered only by
overpaying.
"""
import pytest

from src.assemble import AppraisedPhoto, assemble_lots
from src.bidmath import (
    CompEstimate, Confidence, Priority, allocate, price_lot,
)
from scripts.run_vertex_pipeline import apply_operator_fit


def ap(pid, caption="", **kw):
    return AppraisedPhoto(photo_id=pid, caption=caption, **kw)


def comp(low=100.0, high=140.0, n=3, conf=Confidence.HIGH):
    return CompEstimate(low=low, high=high, source_count=n, confidence=conf)


class TestGrouping:
    def test_two_angles_of_one_lot_produce_one_lot(self):
        lots = assemble_lots([
            ap("p1", "Lot 47 Tonka crane", fit_score=0.8),
            ap("p2", "reverse", same_lot_as_previous=True),
        ])
        assert len(lots) == 1

    def test_explicit_lot_number_becomes_the_lot_id(self):
        lots = assemble_lots([ap("p1", "Lot 47 Tonka crane")])
        assert lots[0].lot_id == "47"

    def test_filler_photos_produce_no_lot(self):
        lots = assemble_lots([
            ap("p1", "Tonka crane"),
            ap("p2", "Blue Toad banner", is_lot=False),
        ])
        assert len(lots) == 1

    def test_empty_input_yields_no_lots(self):
        assert assemble_lots([]) == []


class TestMergeRules:
    def test_condition_penalty_takes_the_worst_angle(self):
        """Damage visible in ANY angle is real damage.

        A photo that did not show the chip is not evidence there is no chip, so
        the group takes the maximum penalty rather than the first or the mean.
        """
        lots = assemble_lots([
            ap("p1", "Lot 5 pitcher", condition_penalty=0.10),
            ap("p2", "hairline crack visible", same_lot_as_previous=True,
               condition_penalty=0.60),
        ])
        assert lots[0].condition_penalty == pytest.approx(0.60)

    def test_best_evidence_photo_supplies_identification_and_category(self):
        """Highest-confidence appraisal wins; a poor angle must not define the lot."""
        lots = assemble_lots([
            ap("p1", "Lot 9 blurry", category="unsorted", fit_score=0.20,
               confidence=Confidence.LOW),
            ap("p2", "clear maker's mark", same_lot_as_previous=True,
               category="stoneware", fit_score=0.90, confidence=Confidence.HIGH),
        ])
        assert lots[0].category == "stoneware"
        assert lots[0].fit_score == pytest.approx(0.90)

    def test_ties_on_confidence_fall_back_to_the_primary_photo(self):
        lots = assemble_lots([
            ap("p1", "Lot 9 first", category="railroad", confidence=Confidence.HIGH),
            ap("p2", "second", same_lot_as_previous=True,
               category="cameras", confidence=Confidence.HIGH),
        ])
        assert lots[0].category == "railroad"

    def test_out_of_range_penalty_from_the_model_is_clamped_on_the_lot(self):
        """The Lot itself must carry a sane value, not just survive bidmath.

        bidmath clamps too, but a Lot that records condition_penalty=-0.5 would
        print "-50% condition" on any sheet or console built straight from it.
        """
        lots = assemble_lots(
            [ap("p1", "Lot 5 pitcher", condition_penalty=-0.5, fit_score=0.8)],
            comps={"5": comp()},
        )
        assert lots[0].condition_penalty == pytest.approx(0.0)

    def test_clamping_does_not_flatten_a_legitimate_penalty(self):
        lots = assemble_lots(
            [ap("p1", "Lot 5 pitcher", condition_penalty=0.35, fit_score=0.8)],
            comps={"5": comp()},
        )
        assert lots[0].condition_penalty == pytest.approx(0.35)


class TestComps:
    def test_a_comp_is_attached_by_lot_id(self):
        lots = assemble_lots([ap("p1", "Lot 47 crane", fit_score=0.8)],
                             comps={"47": comp(low=200.0, high=300.0)})
        assert lots[0].comp.low == 200.0

    def test_a_lot_without_a_comp_routes_to_human_pricing(self):
        """Comps are a separate component and may be absent. Never invent one."""
        lots = assemble_lots([ap("p1", "Lot 47 crane", fit_score=0.8)])
        d = price_lot(lots[0])
        assert d.needs_human_pricing is True
        assert d.max_bid is None


class TestTheWholePoint:
    def test_duplicate_angles_yield_one_bid_not_two(self):
        """The money test: four photos of one lot must commit budget once."""
        appraised = [
            ap("p1", "Lot 3 Fisher-Price circus train", fit_score=0.9,
               confidence=Confidence.HIGH),
            ap("p2", "detail", same_lot_as_previous=True),
            ap("p3", "box", same_lot_as_previous=True),
            ap("p4", "underside", same_lot_as_previous=True),
        ]
        lots = assemble_lots(appraised, comps={"3": comp(low=200.0, high=300.0)})
        decisions = [price_lot(l) for l in lots]
        sheet = allocate(decisions, budget_cap=1000.0)
        bid_ids = [d.lot_id for d in sheet if d.allocated]
        assert len(lots) == 1
        assert len(bid_ids) == len(set(bid_ids)) == 1

    def test_without_grouping_the_same_input_would_have_bid_four_times(self):
        """Documents the bug this layer exists to prevent."""
        appraised = [
            ap(f"p{i}", "Lot 3 Fisher-Price circus train", fit_score=0.9,
               confidence=Confidence.HIGH)
            for i in range(1, 5)
        ]
        # All four carry the SAME explicit lot number, so they must still collapse.
        lots = assemble_lots(appraised, comps={"3": comp()})
        assert len(lots) == 1


class TestReshootMerge:
    """Non-walk returns merge via edges after group_into_lots, not via triage."""

    P2, P181, P87 = "838421481", "838424282", "838422448"

    def test_reshoot_edges_union_two_lots_leave_third(self):
        # Captions without lot numbers → seq:photo_id keys; triage keeps three
        # separate groups (same_lot_as_previous=False on all).
        lots = assemble_lots(
            [
                ap(self.P2, "trays front", same_lot_as_previous=False),
                ap(self.P181, "trays close-up", same_lot_as_previous=False),
                ap(self.P87, "unrelated shelf", same_lot_as_previous=False),
            ],
            reshoot_edges={frozenset({self.P2, self.P181})},
        )
        assert len(lots) == 2
        by_id = {lot.lot_id: lot for lot in lots}
        assert f"seq:{self.P2}" in by_id
        assert f"seq:{self.P87}" in by_id
        assert f"seq:{self.P181}" not in by_id
        assert by_id[f"seq:{self.P2}"].unit_count == 1


class TestOperatorFitAfterMerge:
    """Owner decline of BT-181 must not SKIP the surviving BT-002 lot."""

    def test_declined_closeup_does_not_zero_merged_lot_fit(self):
        lots = assemble_lots(
            [
                ap("BT-002", "Estate Costume Jewelry",
                   identification="trays 12/14/16", category="jewelry",
                   fit_score=0.85, confidence=Confidence.MEDIUM),
                ap("BT-181", "estate costume jewelry",
                   identification="close-up of trays 12/14", category="jewelry",
                   fit_score=0.0, confidence=Confidence.HIGH),
            ],
            comps={"seq:BT-002": comp(), "BT-002": comp()},
            reshoot_edges={frozenset({"BT-002", "BT-181"})},
        )
        assert len(lots) == 1
        lot = apply_operator_fit(lots[0])
        assert lot.lot_id == "BT-002"
        assert lot.fit_score == pytest.approx(0.90)
        d = price_lot(lot)
        assert d.priority is not Priority.SKIP
        assert d.max_bid is not None

    def test_unmerged_declined_181_still_skips(self):
        lots = assemble_lots(
            [ap("BT-181", "estate costume jewelry", category="jewelry",
                fit_score=0.9, confidence=Confidence.HIGH)],
            comps={"seq:BT-181": comp(), "BT-181": comp()},
        )
        lot = apply_operator_fit(lots[0])
        assert lot.lot_id == "BT-181"
        assert lot.fit_score == pytest.approx(0.0)
        assert price_lot(lot).priority is Priority.SKIP


class TestContainerDecomposition:
    def test_container_contents_reach_the_lot_caption(self):
        lots = assemble_lots([
            ap("p1", "Lot 41 box of cylinders",
               identification="Edison cylinder crate",
               is_container=True,
               contents=("11 Blue Amberol cylinders", "1 Gold Moulded cylinder"),
               category="phonograph / records", fit_score=0.9,
               confidence=Confidence.HIGH),
        ])
        caption = lots[0].caption
        assert "Blue Amberol" in caption
        assert "Gold Moulded" in caption

    def test_table_clutter_on_a_weaker_angle_does_not_replace_contents(self):
        lots = assemble_lots([
            ap("p1", "Lot 41 crate",
               identification="Edison cylinder crate",
               is_container=True,
               contents=("11 Blue Amberol cylinders",),
               category="phonograph / records", fit_score=0.9,
               confidence=Confidence.HIGH),
            ap("p2", "wider table shot",
               identification="crate next to a clock and a lamp",
               same_lot_as_previous=True,
               is_container=False,
               contents=(),
               category="unsorted", fit_score=0.2,
               confidence=Confidence.LOW),
        ])
        assert "clock" not in lots[0].caption
        assert "Blue Amberol" in lots[0].caption

    def test_non_container_caption_stays_the_identification(self):
        lots = assemble_lots([
            ap("p1", "Lot 5 crock", identification="Red Wing 5 gallon",
               category="stoneware", fit_score=0.9, confidence=Confidence.HIGH),
        ])
        assert lots[0].caption == "Red Wing 5 gallon"
