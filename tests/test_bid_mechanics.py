"""
Bid mechanics — how many times the hammer price is actually charged.

Every test here exists because `bidmath` modelled one lot as one bid for one
thing, and a rural auctioneer does not sell that way. Three mechanics are real
at Blue Toad, and the difference between them is money:

  STRAIGHT          bid once, take the lot.
  CHOICE            per-unit price, ELECTIVE quantity: bid high, then take
                    1..N at that price. The unsold rest is re-auctioned, often
                    at the house minimum. Winner's choice of a shelf on a
                    five-shelf lantern unit — one photograph, five lots.
  TIMES_THE_MONEY   the bid is PER UNIT and charged N times. Confirmed by the
                    auctioneer on the labelled jewelry tray run (12/14/16):
                    "Yes, that is a x3 bid." That ruling moved BT-002 from $25
                    of committed money to $75 without any number on the sheet
                    changing.

The allocator budgeted `all_in` per lot regardless, so a times-the-money lot
understated its own commitment by a factor of N against a hard cap the operator
set to stop exactly that.
"""

import pytest

from src.bidmath import (
    BidMechanic, CompEstimate, Confidence, Decision, Lot, Priority,
    all_in_cost, allocate, price_lot, summarize, units_committed,
)


def comp(low=100.0, high=140.0, n=3, conf=Confidence.HIGH):
    return CompEstimate(low=low, high=high, source_count=n, confidence=conf)


def lot(lot_id="L1", cat="breweriana", fit=0.85, cond=0.0, c=None,
        mechanic=BidMechanic.STRAIGHT, unit_count=1):
    return Lot(lot_id=lot_id, caption="test", category=cat, fit_score=fit,
               condition_penalty=cond, comp=c or comp(),
               mechanic=mechanic, unit_count=unit_count)


class TestUnitsCommitted:
    """How many times the hammer price is charged if the bid wins."""

    def test_straight_lot_charges_once(self):
        assert units_committed(BidMechanic.STRAIGHT, 1) == 1

    def test_straight_lot_charges_once_even_if_it_contains_many_things(self):
        # A box of 40 books is one lot. unit_count describes sellable UNITS,
        # not objects, and a straight lot is a single unit however full it is.
        assert units_committed(BidMechanic.STRAIGHT, 40) == 1

    def test_an_unelected_choice_lot_budgets_for_every_unit(self):
        """CORRECTED 2026-08-21. This file first asserted that choice charges
        once, "you pay the bid and take ONE shelf". That is not how Blue Toad
        sells. The operator:

            "it's only OPTIONAL to take 1 at bid price. One may take 1-N at bid
             price."

        Choice is per-unit pricing with an elective quantity, so with no
        election recorded the exposure is the whole group, not one unit. See
        tests/test_elective_quantity.py for k.
        """
        assert units_committed(BidMechanic.CHOICE, 5) == 5

    def test_times_the_money_charges_once_per_unit(self):
        assert units_committed(BidMechanic.TIMES_THE_MONEY, 3) == 3

    def test_times_the_money_never_charges_less_than_once(self):
        # A malformed unit_count must not zero out a real commitment.
        assert units_committed(BidMechanic.TIMES_THE_MONEY, 0) == 1
        assert units_committed(BidMechanic.TIMES_THE_MONEY, -2) == 1

    def test_unknown_mechanic_assumes_the_expensive_reading(self):
        """An unestablished mechanic budgets for the worst case, not the cheap one.

        Guessing STRAIGHT on a lot that turns out to be times-the-money is how
        the cap gets breached at the block, where nobody can undo it. Guessing
        the expensive way only ever under-fills the sheet, which a human can fix.
        """
        assert units_committed(BidMechanic.UNKNOWN, 3) == 3


class TestCommittedAllIn:
    def test_straight_commits_its_all_in(self):
        d = price_lot(lot())
        assert d.committed_all_in == d.all_in

    def test_times_the_money_commits_all_in_times_units(self):
        d = price_lot(lot(mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3))
        assert d.committed_all_in == pytest.approx(round(d.all_in * 3, 2))

    def test_the_jewelry_tray_case_to_the_cent(self):
        # $25 max on each of trays 12/14/16, 15% absentee fee, resale exempt.
        # 25 * 1.15 = 28.75 per tray; three trays is 86.25, not 28.75.
        d = Decision(lot_id="BT-002", category="jewelry", priority=Priority.B,
                     max_bid=25.0, all_in=all_in_cost(25.0), bid_fraction=0.35,
                     reason="", needs_human_pricing=False,
                     mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3)
        assert d.all_in == pytest.approx(28.75)
        assert d.committed_all_in == pytest.approx(86.25)

    def test_an_unpriced_decision_commits_nothing(self):
        d = price_lot(lot(c=CompEstimate(None, None, 0, Confidence.NONE)))
        assert d.max_bid is None and d.committed_all_in is None


class TestAllocateBudgetsTheRealCommitment:
    """The defect this feature exists to fix."""

    def test_times_the_money_consumes_its_full_commitment_from_the_cap(self):
        d = price_lot(lot(mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3))
        # Cap sits above one unit's all_in but below three. Old code allocated.
        cap = d.all_in * 2
        out = allocate([d], budget_cap=cap)
        assert out[0].allocated is False
        assert "over budget cap" in out[0].reason

    def test_the_same_lot_fits_when_the_cap_covers_every_unit(self):
        d = price_lot(lot(mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3))
        out = allocate([d], budget_cap=d.all_in * 3)
        assert out[0].allocated is True

    def test_a_times_the_money_lot_cannot_crowd_in_behind_its_own_understated_cost(self):
        """Two x3 lots against a cap that fits one. The old sum let both in."""
        a = price_lot(lot(lot_id="A", mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3))
        b = price_lot(lot(lot_id="B", mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3))
        out = allocate([a, b], budget_cap=a.committed_all_in + 1.0)
        assert sum(1 for d in out if d.allocated) == 1

    def test_straight_lots_allocate_exactly_as_before(self):
        # Regression guard: the defaults must not move any existing sheet.
        lots = [lot(lot_id=f"L{i}") for i in range(4)]
        out = allocate([price_lot(l) for l in lots], budget_cap=1000.0)
        assert all(d.allocated for d in out)
        assert sum(d.all_in for d in out) == pytest.approx(sum(d.committed_all_in for d in out))


class TestChoiceLotsArePricedPerUnit:
    def test_choice_lot_is_priced_per_unit_not_refused(self):
        """CORRECTED 2026-08-21. This originally refused to price choice lots at
        all, reasoning that a five-shelf comp is not a one-shelf comp.

        The premise was right and the conclusion was wrong. The comp does cover
        the group, so it is divided down to one unit — dividing can only ever
        bid LESS than the group is worth, while not dividing commits several
        times the cap. What is genuinely unknown is not the price but k, how
        many units the operator elects to take, and that is a question to ask
        rather than grounds to refuse.

        See tests/test_elective_quantity.py. Do not restore the refusal.
        """
        d = price_lot(lot(mechanic=BidMechanic.CHOICE, unit_count=5))
        assert d.max_bid is not None
        assert d.needs_human_pricing is False
        assert d.needs_election is True
        assert "per unit" in d.reason.lower()

    def test_a_choice_lot_of_one_unit_is_just_a_straight_lot(self):
        # Choice of one is not a choice. Nothing to elect.
        d = price_lot(lot(mechanic=BidMechanic.CHOICE, unit_count=1))
        assert d.needs_human_pricing is False
        assert d.needs_election is False
        assert d.max_bid is not None


class TestUnknownMechanicNeedsARuling:
    def test_multi_unit_unknown_refuses_and_flags_for_a_ruling(self):
        d = price_lot(lot(mechanic=BidMechanic.UNKNOWN, unit_count=3))
        assert d.needs_mechanic_ruling is True
        assert d.max_bid is None
        assert d.needs_human_pricing is True

    def test_single_unit_unknown_needs_no_ruling(self):
        """One object: straight, choice and times-the-money are the same bid."""
        d = price_lot(lot(mechanic=BidMechanic.UNKNOWN, unit_count=1))
        assert d.needs_mechanic_ruling is False
        assert d.max_bid is not None

    def test_a_lot_needing_a_ruling_is_never_auto_sent(self):
        d = price_lot(lot(mechanic=BidMechanic.UNKNOWN, unit_count=3))
        out = allocate([d], budget_cap=10_000.0, auto_send_threshold=10_000.0)
        assert out[0].auto_send is False


class TestSummarizeCountsCommittedMoney:
    def test_committed_all_in_totals_the_real_exposure(self):
        d = price_lot(lot(mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3))
        out = allocate([d], budget_cap=10_000.0)
        s = summarize(out)
        assert s.committed_all_in == pytest.approx(out[0].committed_all_in)
        assert s.committed_all_in > out[0].all_in

    def test_committed_max_totals_per_unit_hammer(self):
        d = price_lot(lot(mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3))
        s = summarize(allocate([d], budget_cap=10_000.0))
        assert s.committed_max == pytest.approx(round(d.max_bid * 3, 2))


class TestDefaultsPreserveEveryExistingSheet:
    def test_a_lot_built_without_mechanic_is_straight_single_unit(self):
        l = Lot(lot_id="L", caption="c", category="breweriana",
                fit_score=0.85, condition_penalty=0.0, comp=comp())
        assert l.mechanic is BidMechanic.STRAIGHT
        assert l.unit_count == 1

    def test_a_decision_built_without_mechanic_commits_its_all_in(self):
        d = Decision(lot_id="L", category="breweriana", priority=Priority.A,
                     max_bid=40.0, all_in=46.0, bid_fraction=0.35,
                     reason="", needs_human_pricing=False)
        assert d.mechanic is BidMechanic.STRAIGHT
        assert d.committed_all_in == 46.0
        assert d.needs_mechanic_ruling is False

    def test_new_fields_are_appended_last_on_lot(self):
        """Lot and Decision are constructed positionally in demo/ and scripts/.

        tests/test_gate.py already builds CompEstimate with four positional
        arguments, so a field inserted mid-struct there would silently bind the
        wrong value and still pass. Pin the order rather than trust review.
        """
        from dataclasses import fields
        names = [f.name for f in fields(Lot)]
        assert names[:6] == ["lot_id", "caption", "category", "fit_score",
                             "condition_penalty", "comp"]
        assert names[6:] == ["mechanic", "unit_count", "units_wanted"]

    def test_new_fields_are_appended_last_on_decision(self):
        from dataclasses import fields
        names = [f.name for f in fields(Decision)]
        assert names[:10] == [
            "lot_id", "category", "priority", "max_bid", "all_in",
            "bid_fraction", "reason", "needs_human_pricing", "auto_send",
            "allocated"]
        assert names[10:] == ["mechanic", "unit_count", "units_wanted",
                              "needs_mechanic_ruling", "needs_election",
                              "speculative"]
