"""
Elective quantity — k, and the second bite at the remainder.

Blue Toad's Buyer's Choice is per-unit pricing with an ELECTIVE quantity. The
operator, correcting an earlier reading that had choice and times-the-money as
opposite mechanics:

    "it's only OPTIONAL to take 1 at bid price. One may take 1-N at bid price...
     if the winner takes anything less than N, the remaining lot is re-auctioned
     usually starting right at the min or 1/2 of last winning bid. I did that one
     at the min of $5."

Two things follow, and neither was modelled anywhere.

First, k is a DECISION, not a property of the lot. The winner elects it in the
room. An absentee bidder is not in the room, so k has to be written down and
handed to the clerk — which is exactly what the plain-English closing
instruction in his own July 11 drafts was doing.

Second, when k < N the remainder goes back up, typically at the house minimum or
half the last hammer. That is a second, cheaper buying opportunity on inventory
already appraised, and the sheet has never once looked at it.
"""

import pytest

from src.bidmath import (
    BID_INCREMENT, BidMechanic, CompEstimate, Confidence, Decision, Lot,
    Priority, all_in_cost, allocate, clerk_directive, elect, price_lot,
    remainder_opportunity, summarize, units_committed,
)


def comp(low=100.0, high=140.0, n=3, conf=Confidence.HIGH):
    return CompEstimate(low=low, high=high, source_count=n, confidence=conf)


def lot(lot_id="L1", cat="railroad", fit=0.85, cond=0.0, c=None,
        mechanic=BidMechanic.STRAIGHT, unit_count=1, units_wanted=None):
    return Lot(lot_id=lot_id, caption="test", category=cat, fit_score=fit,
               condition_penalty=cond, comp=c or comp(), mechanic=mechanic,
               unit_count=unit_count, units_wanted=units_wanted)


class TestElect:
    def test_records_the_operators_election(self):
        assert elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2).units_wanted == 2

    def test_taking_everything_is_allowed(self):
        assert elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 5).units_wanted == 5

    def test_cannot_elect_more_than_the_lot_holds(self):
        with pytest.raises(ValueError):
            elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 6)

    def test_cannot_elect_none(self):
        # Electing zero is declining the lot, which is done by not bidding.
        with pytest.raises(ValueError):
            elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 0)

    def test_leaves_every_other_field_alone(self):
        before = lot(mechanic=BidMechanic.CHOICE, unit_count=5)
        after = elect(before, 3)
        assert (after.lot_id, after.comp, after.mechanic) == (
            before.lot_id, before.comp, before.mechanic)


class TestUnitsCommittedHonoursTheElection:
    def test_choice_commits_only_what_was_elected(self):
        assert units_committed(BidMechanic.CHOICE, 5, units_wanted=2) == 2

    def test_times_the_money_defaults_to_taking_them_all(self):
        assert units_committed(BidMechanic.TIMES_THE_MONEY, 3) == 3

    def test_times_the_money_respects_a_smaller_election(self):
        assert units_committed(BidMechanic.TIMES_THE_MONEY, 3, units_wanted=2) == 2

    def test_an_unelected_choice_lot_budgets_for_the_whole_group(self):
        """No election yet means no ceiling yet. Budget the expensive reading.

        The alternative — assuming one — books a fifth of the exposure on a lot
        that could take the whole cap, and the cap exists to stop exactly that.
        """
        assert units_committed(BidMechanic.CHOICE, 5) == 5

    def test_a_straight_lot_ignores_an_election_entirely(self):
        assert units_committed(BidMechanic.STRAIGHT, 1, units_wanted=4) == 1


class TestChoiceLotsArePricedPerUnit:
    def test_an_elected_choice_lot_prices_and_commits_k_units(self):
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2))
        assert d.max_bid is not None
        assert d.needs_human_pricing is False
        assert d.committed_all_in == pytest.approx(round(d.all_in * 2, 2))

    def test_an_unelected_choice_lot_asks_for_the_election(self):
        d = price_lot(lot(mechanic=BidMechanic.CHOICE, unit_count=5))
        assert d.needs_election is True
        assert "how many" in d.reason.lower()

    def test_a_single_unit_choice_lot_needs_no_election(self):
        d = price_lot(lot(mechanic=BidMechanic.CHOICE, unit_count=1))
        assert d.needs_election is False
        assert d.max_bid is not None

    def test_a_lot_awaiting_an_election_is_never_auto_sent(self):
        out = allocate([price_lot(lot(mechanic=BidMechanic.CHOICE, unit_count=5))],
                       budget_cap=10_000.0, auto_send_threshold=10_000.0)
        assert out[0].auto_send is False


class TestClerkDirective:
    """The absentee bidder is not in the room, so k goes in writing to the clerk."""

    def test_a_straight_lot_says_one_bid(self):
        text = clerk_directive(price_lot(lot()))
        assert "one lot" in text.lower()
        assert "per unit" not in text.lower()

    def test_a_choice_lot_states_how_many_to_take(self):
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2))
        text = clerk_directive(d)
        assert "choice" in text.lower()
        assert "2 of the 5" in text

    def test_times_the_money_states_the_multiplier_and_the_total(self):
        d = price_lot(lot(mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3))
        text = clerk_directive(d)
        assert "times the money" in text.lower()
        assert f"{d.committed_all_in:,.2f}" in text

    def test_an_unruled_mechanic_tells_the_clerk_not_to_bid(self):
        """Silence is the dangerous default. Say it out loud."""
        text = clerk_directive(price_lot(lot(mechanic=BidMechanic.UNKNOWN, unit_count=3)))
        assert "do not bid" in text.lower()

    def test_an_unpriced_lot_tells_the_clerk_not_to_bid(self):
        d = price_lot(lot(c=CompEstimate(None, None, 0, Confidence.NONE)))
        assert "do not bid" in clerk_directive(d).lower()


class TestRemainderOpportunity:
    """When k < N the rest goes back up cheap. That is inventory already appraised."""

    def test_offers_the_leftover_units_at_the_house_minimum(self):
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2))
        r = remainder_opportunity(d, floor=5.0)
        assert r is not None
        assert r.unit_count == 3
        assert r.max_bid == 5.0
        assert r.committed_all_in == pytest.approx(round(all_in_cost(5.0) * 3, 2))

    def test_the_floor_never_exceeds_the_primary_bid(self):
        """A remainder bid above the lot's own max is not a bargain, it is a bug."""
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=4,
                                c=comp(low=20.0, high=24.0)), 1))
        r = remainder_opportunity(d, floor=1_000.0)
        assert r is None or r.max_bid <= d.max_bid

    def test_nothing_is_offered_when_the_election_takes_everything(self):
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=3), 3))
        assert remainder_opportunity(d) is None

    def test_nothing_is_offered_on_a_straight_lot(self):
        assert remainder_opportunity(price_lot(lot())) is None

    def test_nothing_is_offered_when_the_lot_was_never_priced(self):
        d = price_lot(lot(c=CompEstimate(None, None, 0, Confidence.NONE)))
        assert remainder_opportunity(d) is None

    def test_the_remainder_is_distinguishable_from_the_primary_bid(self):
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2))
        r = remainder_opportunity(d)
        assert r.lot_id != d.lot_id
        assert "remainder" in r.reason.lower()

    def test_the_remainder_is_marked_speculative(self):
        """It only exists if the winner declines part of the lot."""
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2))
        assert remainder_opportunity(d).speculative is True

    def test_the_remainder_directive_says_it_is_contingent(self):
        """Contingent money reads like committed money unless it says otherwise,
        and a clerk holding an unmarked contingent line will simply bid it."""
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2))
        text = clerk_directive(remainder_opportunity(d))
        assert "only if" in text.lower()
        assert "skip if the lot clears whole" in text.lower()

    def test_the_remainder_never_auto_sends(self):
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2))
        out = allocate([remainder_opportunity(d)], budget_cap=10_000.0,
                       auto_send_threshold=10_000.0)
        assert out[0].auto_send is False

    def test_the_remainder_competes_for_the_same_budget(self):
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2))
        r = remainder_opportunity(d)
        s = summarize(allocate([d, r], budget_cap=10_000.0))
        assert s.committed_all_in == pytest.approx(
            round(d.committed_all_in + r.committed_all_in, 2))


class TestNothingExistingMoves:
    def test_defaults_leave_a_plain_lot_untouched(self):
        d = price_lot(lot())
        assert d.unit_count == 1 and d.units_wanted is None
        assert d.needs_election is False
        assert d.committed_all_in == d.all_in

    def test_new_fields_stay_appended_last(self):
        from dataclasses import fields
        assert [f.name for f in fields(Lot)][6:] == [
            "mechanic", "unit_count", "units_wanted"]
        assert [f.name for f in fields(Decision)][10:] == [
            "mechanic", "unit_count", "units_wanted", "needs_mechanic_ruling",
            "needs_election", "speculative"]
