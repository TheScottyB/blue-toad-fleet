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
