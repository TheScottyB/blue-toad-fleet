from src.assemble import AppraisedPhoto, assemble_lots
from src.assemble.email import compile_absentee_email
from src.bidmath import (
    BidMechanic, CompEstimate, Confidence, Lot, allocate, is_choice_lot, price_lot,
)


def comp(low=100.0, high=140.0):
    return CompEstimate(low=low, high=high, source_count=3, confidence=Confidence.HIGH)


class TestDetection:
    def test_buyers_choice_caption_is_choice(self):
        assert is_choice_lot("Buyer's Choice of the railroad lanterns") is True

    def test_times_the_money_is_choice(self):
        assert is_choice_lot("framed travel posters — $200 times the money") is True

    def test_choice_of_the_shelf_is_choice(self):
        assert is_choice_lot("Choice of the shelf") is True

    def test_ordinary_caption_is_not_choice(self):
        assert is_choice_lot("Red Wing 5 gallon crock, wing mark") is False

    def test_joins_multiple_text_fields(self):
        assert is_choice_lot("lantern line", "times the money") is True


class TestStandingDefaultElectsOne:
    def test_choice_without_a_ruling_takes_one_unit(self):
        lot = Lot(
            lot_id="L1", caption="Choice of the lantern line", category="railroad",
            fit_score=0.9, condition_penalty=0.0, comp=comp(),
            mechanic=BidMechanic.CHOICE, unit_count=1, units_wanted=1,
        )
        d = price_lot(lot)
        assert d.mechanic is BidMechanic.CHOICE
        assert d.units_wanted == 1
        assert d.committed_max == d.max_bid
        assert d.max_bid is not None

    def test_choice_does_not_budget_the_whole_shelf_when_k_is_one(self):
        """8 lanterns × $45 would be the clerk blowout the standing rule prevents."""
        lot = Lot(
            lot_id="L1", caption="Choice of 8 railroad lanterns",
            category="railroad", fit_score=0.9, condition_penalty=0.0, comp=comp(),
            mechanic=BidMechanic.CHOICE, unit_count=8, units_wanted=1,
        )
        d = price_lot(lot)
        assert d.units_wanted == 1
        assert d.committed_max == d.max_bid
        assert d.committed_all_in == d.all_in

    def test_straight_lot_defaults_remain_one_hammer(self):
        d = price_lot(Lot(
            lot_id="L1", caption="Red Wing crock", category="stoneware",
            fit_score=0.9, condition_penalty=0.0, comp=comp(),
        ))
        assert d.mechanic is BidMechanic.STRAIGHT
        assert d.unit_count == 1


class TestAssemblePropagatesChoice:
    def test_assemble_marks_choice_from_identification(self):
        lots = assemble_lots([
            AppraisedPhoto(
                photo_id="p1", caption="Lot 12 lanterns",
                identification="Buyer's Choice of the railroad lantern line",
                category="railroad", fit_score=0.9, confidence=Confidence.HIGH,
            ),
        ], comps={"12": comp()})
        assert lots[0].mechanic is BidMechanic.CHOICE
        assert lots[0].units_wanted == 1

    def test_assemble_leaves_ordinary_lots_straight(self):
        lots = assemble_lots([
            AppraisedPhoto(
                photo_id="p1", caption="Lot 5 Red Wing crock",
                identification="Red Wing 5 gallon, wing mark",
                category="stoneware", fit_score=0.9, confidence=Confidence.HIGH,
            ),
        ], comps={"5": comp()})
        assert lots[0].mechanic is BidMechanic.STRAIGHT


class TestEmailInstruction:
    def test_choice_instruction_appears_when_a_choice_lot_is_allocated(self):
        lot = Lot(
            lot_id="BT-184", caption="Choice of the railroad lanterns",
            category="railroad", fit_score=0.9, condition_penalty=0.0, comp=comp(),
            mechanic=BidMechanic.CHOICE, unit_count=1, units_wanted=1,
        )
        ds = allocate([price_lot(lot)], budget_cap=10_000)
        text = compile_absentee_email(
            to="info@bluetoadauctions.com", subject="Absentee Bids",
            auction_date="Saturday, August 22, 2026",
            venue="200 Elizabeth Lane, Genoa City, WI",
            lots=[lot], decisions=ds,
        )
        assert "max quantity is 1" in text.lower() or "max quantity is 1 unit" in text.lower()

    def test_standing_one_unit_rule_is_on_the_sheet_even_without_a_choice_lot(self):
        lot = Lot(
            lot_id="BT-001", caption="Topps cards", category="vintage cards",
            fit_score=0.9, condition_penalty=0.0, comp=comp(),
        )
        ds = allocate([price_lot(lot)], budget_cap=10_000)
        text = compile_absentee_email(
            to="info@bluetoadauctions.com", subject="Absentee Bids",
            auction_date="Saturday, August 22, 2026",
            venue="200 Elizabeth Lane, Genoa City, WI",
            lots=[lot], decisions=ds,
        )
        assert "max quantity is 1 unit only" in text.lower()
