"""
Reading an auctioneer's ruling into money.

The appraiser already asks the right question on the right lots — 21 `lot_grouping`
questions across the Aug 22 corpus, BT-002's being verbatim "Is the auction bid for
a single tray (e.g., Tray 12, 14, or 16) or for all trays shown together?" Bill
answered it: "Yes, that is a x3 bid."

Nothing carried that answer to the two fields that decide what gets spent. The
operator typed it into the absentee email by hand at 16:53 on cutoff day instead:

    MAX $25.00 PER TRAY x 3 TRAYS  =  $75.00 TOTAL
    BT-002 is the ONE exception to my usual one-unit rule: take all three trays at x3.
    For any OTHER 'Buyer's Choice / Times the Money' shelf lot, max quantity is 1 unit.

That is `units_wanted`, written in prose to a clerk, because `StandingRule` had
nowhere to put it. This module is the wire.

It parses free text into a commitment, so the failure mode matters more than the
happy path: anything it cannot read confidently becomes UNKNOWN, never STRAIGHT.
UNKNOWN budgets the expensive reading and flags for a ruling; STRAIGHT silently
books one unit of a lot that may charge five.
"""

import pytest

from src.bidmath import BidMechanic, mechanic_from_ruling


class TestTheAnswerThatStartedThis:
    def test_bills_actual_words(self):
        """The ruling that moved BT-002 from $25 to $75, verbatim."""
        assert mechanic_from_ruling("Yes, that is a x3 bid.") == (
            BidMechanic.TIMES_THE_MONEY, 3, None)

    def test_the_operators_own_instruction_carries_the_election_too(self):
        assert mechanic_from_ruling(
            "BT-002 is the ONE exception to my usual one-unit rule: "
            "take all three trays at x3") == (BidMechanic.TIMES_THE_MONEY, 3, 3)

    def test_the_standing_default_he_wrote_for_every_other_lot(self):
        assert mechanic_from_ruling(
            "For any OTHER 'Buyer's Choice / Times the Money' shelf lot, "
            "max quantity is 1 unit", units_available=5) == (
            BidMechanic.CHOICE, 5, 1)


class TestTimesTheMoney:
    @pytest.mark.parametrize("text", [
        "x3 bid", "X3", "3x the money", "times the money x3",
        "that is a times-the-money lot, 3 of them", "×3",
    ])
    def test_reads_the_multiplier(self, text):
        mech, n, _ = mechanic_from_ruling(text)
        assert mech is BidMechanic.TIMES_THE_MONEY and n == 3

    def test_spelled_out_numbers(self):
        assert mechanic_from_ruling("times the money, all four")[:2] == (
            BidMechanic.TIMES_THE_MONEY, 4)

    def test_times_the_money_without_a_count_falls_back_to_what_is_available(self):
        assert mechanic_from_ruling("times the money", units_available=6)[:2] == (
            BidMechanic.TIMES_THE_MONEY, 6)

    def test_times_the_money_with_no_count_anywhere_is_not_guessed(self):
        """A per-unit charge with an unknown unit count is unpriceable, not 1."""
        assert mechanic_from_ruling("times the money")[0] is BidMechanic.UNKNOWN


class TestChoice:
    @pytest.mark.parametrize("text", [
        "buyer's choice", "buyers choice", "winner's choice of the shelf",
        "choice of any one", "bidder's choice",
    ])
    def test_reads_choice(self, text):
        assert mechanic_from_ruling(text, units_available=5)[0] is BidMechanic.CHOICE

    def test_choice_takes_its_count_from_what_is_available(self):
        assert mechanic_from_ruling("buyer's choice", units_available=5)[1] == 5

    def test_choice_with_an_explicit_election(self):
        assert mechanic_from_ruling(
            "buyer's choice, take 2", units_available=5) == (BidMechanic.CHOICE, 5, 2)

    def test_choice_can_state_both_available_and_elected_counts(self):
        assert mechanic_from_ruling("buyer's choice of 5, take 2") == (
            BidMechanic.CHOICE, 5, 2)

    def test_an_election_larger_than_the_lot_is_clamped_not_accepted(self):
        assert mechanic_from_ruling(
            "buyer's choice, take 9", units_available=5)[2] == 5


class TestStraight:
    @pytest.mark.parametrize("text", [
        "sold as a single lot", "one lot", "all together as one",
        "the whole shelf goes as a unit", "sold as one lot, all trays combined",
    ])
    def test_reads_a_single_lot(self, text):
        assert mechanic_from_ruling(text) == (BidMechanic.STRAIGHT, 1, 1)


class TestItRefusesRatherThanGuesses:
    @pytest.mark.parametrize("text", [
        "", "   ", "not sure", "ask Bill on the day", "see photo",
        "yes", "no", "maybe both", "I'll decide at the preview",
    ])
    def test_anything_unreadable_is_unknown(self, text):
        assert mechanic_from_ruling(text, units_available=4)[0] is BidMechanic.UNKNOWN

    def test_none_is_unknown(self):
        assert mechanic_from_ruling(None)[0] is BidMechanic.UNKNOWN

    def test_unknown_keeps_the_available_count_so_exposure_stays_honest(self):
        """UNKNOWN budgets every unit. It must not lose the count on the way."""
        assert mechanic_from_ruling("not sure", units_available=4)[1] == 4

    def test_a_bare_yes_is_not_a_ruling(self):
        """The question was 'one lot or all of them?'. "Yes" answers neither, and
        reading it as either books money on a coin flip."""
        assert mechanic_from_ruling("yes", units_available=3)[0] is BidMechanic.UNKNOWN

    def test_conflicting_signals_refuse(self):
        """Both mechanics named at once is not a ruling, it is a restatement of
        the question. Do not let word order decide the money."""
        assert mechanic_from_ruling(
            "is it buyer's choice or sold as a single lot?",
            units_available=3)[0] is BidMechanic.UNKNOWN


class TestNumberParsing:
    @pytest.mark.parametrize("text,want", [
        ("x2", 2), ("x10", 10), ("times the money, all five", 5),
        ("x 7 bid", 7),
    ])
    def test_counts(self, text, want):
        assert mechanic_from_ruling(text)[1] == want

    def test_a_zero_multiplier_is_not_a_ruling(self):
        assert mechanic_from_ruling("x0 bid")[0] is BidMechanic.UNKNOWN

    def test_an_absurd_multiplier_is_not_trusted(self):
        """A lot with 900 units is a parse error, not an auction lot."""
        assert mechanic_from_ruling("x900 bid")[0] is BidMechanic.UNKNOWN


class TestItDoesNotReadMoneyAsAMultiplier:
    """The operator's own bid format contains "x N". So does every dollar figure
    beside it, and the multiplier pattern was matching the wrong one.

    "MAX $25 x 3 TRAYS" parsed as 25 units, priced at $5.00 each, and wrote
    ">> I am taking ALL 50 <<" into an outgoing draft with every honest-refusal
    flag reading clean. A quantity nobody stated, sent to the auction house as a
    commitment.
    """

    @pytest.mark.parametrize("text", [
        "bid to $17.50 x 2 trays", "$7.25 x 3", "$30 x 2",
        "MAX $25 x 3 TRAYS", "MAX $25.00 PER TRAY x 3 TRAYS = $75.00 TOTAL",
    ])
    def test_a_dollar_figure_is_never_the_unit_count(self, text):
        mech, n, _ = mechanic_from_ruling(text)
        assert n != 25 and n != 30 and n != 50 and n != 17 and n != 7, \
            f"{text!r} -> {n} units"

    def test_the_operators_own_bid_line_reads_three_units_or_refuses(self):
        mech, n, _ = mechanic_from_ruling("MAX $25.00 PER TRAY x 3 TRAYS")
        assert mech is BidMechanic.UNKNOWN or n == 3

    def test_dimensions_are_not_unit_counts(self):
        assert mechanic_from_ruling("buyer's choice of the 8 x 10 frames",
                                    units_available=4)[1] != 8

    def test_a_real_multiplier_still_reads(self):
        assert mechanic_from_ruling("that is a x3 bid")[:2] == (
            BidMechanic.TIMES_THE_MONEY, 3)


class TestNegationIsNotAgreement:
    """A refusal that names the mechanic was read as affirming it."""

    @pytest.mark.parametrize("text", [
        "No, that is not a x3 bid.",
        "It is NOT times the money, take all 3.",
        "It is not buyers choice.",
        "that isn't a choice lot",
        "no, not sold as a single lot",
    ])
    def test_a_denial_never_establishes_the_thing_denied(self, text):
        assert mechanic_from_ruling(text, units_available=3)[0] is BidMechanic.UNKNOWN


class TestAnUnreadableRulingRefusesToPrice:
    """UNKNOWN must not fail open into a priceable one-unit bid.

    The parser cannot establish a count, so it returned 1 — and `price_lot`'s
    refusal required `unit_count > 1`, making it dead code. Every unreadable
    ruling became a clean, allocated, potentially auto-sent bid. The module
    docstring promised UNKNOWN "budgets every unit and asks for a ruling"; it
    budgeted one unit and asked nothing.
    """

    @pytest.mark.parametrize("text", [
        "times the money", "three times the money", "yes", "x0 bid",
        "it's buyer's choice or sold as a single lot, not sure",
    ])
    def test_every_unreadable_ruling_refuses(self, text):
        from src.bidmath import CompEstimate, Confidence, Lot, price_lot
        mech, n, k = mechanic_from_ruling(text)
        assert mech is BidMechanic.UNKNOWN
        d = price_lot(Lot(lot_id="BT-900", caption="", category="railroad",
                          fit_score=0.85, condition_penalty=0.0,
                          comp=CompEstimate(100.0, 140.0, 3, Confidence.HIGH),
                          mechanic=mech, unit_count=n, units_wanted=k))
        assert d.max_bid is None, f"{text!r} priced at {d.max_bid}"
        assert d.needs_mechanic_ruling is True


class TestChoiceWithNoCountDoesNotInventOne:
    """Both production callers pass no units_available, and CHOICE fabricated
    unit_count=1 — which suppressed price_lot's divide-the-comp-down step and
    made the whole group's value the ceiling for a single unit. Five times the
    per-unit ceiling, in the overbid direction.
    """

    def test_choice_harvests_a_stated_count_like_times_the_money_does(self):
        assert mechanic_from_ruling("buyer's choice, take all five")[:2] == (
            BidMechanic.CHOICE, 5)

    def test_choice_with_no_count_anywhere_refuses(self):
        assert mechanic_from_ruling("buyer's choice, take 3")[0] is BidMechanic.UNKNOWN

    def test_an_election_is_never_clamped_against_an_invented_count(self):
        mech, n, k = mechanic_from_ruling("buyer's choice, take 3")
        assert not (mech is BidMechanic.CHOICE and n == 1 and k == 1)


class TestDisagreeingMultipliersRefuse:
    """Raised by the grok lane against a4a3960, reproduced here before acting.

    "trays 12 x 14 x 16 go as a x3 bid" read 14 units — the first `xN` in the
    string — and silently discarded the `x3` that was the ruling. Tray labels
    written with `x` as a separator is a constructed string today, but `ruling`
    is free text somebody could paste a fuller note into, and the failure is a
    confident wrong count in the direction of bidding on a number nobody stated.

    The module already refuses when two MECHANICS are named, on the grounds that
    the sentence restates the question rather than answering it. Two multipliers
    that disagree is the same shape.
    """

    def test_disagreeing_multipliers_are_not_settled_by_position(self):
        assert mechanic_from_ruling(
            "trays 12 x 14 x 16 go as a x3 bid")[0] is BidMechanic.UNKNOWN

    def test_a_repeated_agreeing_multiplier_still_reads(self):
        assert mechanic_from_ruling("x3 bid, that is x3 the money")[:2] == (
            BidMechanic.TIMES_THE_MONEY, 3)

    @pytest.mark.parametrize("text", [
        "trays 12, 14, and 16 go as a x3 bid",
        "x3 bid on trays 12/14/16",
        "take all three trays at x3",
        "Yes, that is a x3 bid.",
    ])
    def test_every_phrasing_that_worked_before_still_works(self, text):
        assert mechanic_from_ruling(text)[:2] == (BidMechanic.TIMES_THE_MONEY, 3)


class TestNegationScopesTheMechanic:
    def test_operator_not_limit_phrase_affirms_x3(self):
        assert mechanic_from_ruling(
            "take all three trays at x3, do not limit me to one unit"
        ) == (BidMechanic.TIMES_THE_MONEY, 3, 3)

    @pytest.mark.parametrize("text", [
        "that is not a x3 bid",
        "this isn't times the money",
        "buyer's choice is not the mechanic",
        "never a single lot",
    ])
    def test_negated_mechanic_still_refuses(self, text):
        assert mechanic_from_ruling(text)[0] is BidMechanic.UNKNOWN


class TestImplausibleCountsRefuseTheWholeRuling:
    def test_implausible_election_is_not_silently_dropped(self):
        assert mechanic_from_ruling(
            "times the money, take all 900", units_available=5
        )[0] is BidMechanic.UNKNOWN

    def test_implausible_max_quantity_is_not_silently_dropped(self):
        assert mechanic_from_ruling(
            "buyer's choice, maximum quantity is 900", units_available=5
        )[0] is BidMechanic.UNKNOWN
