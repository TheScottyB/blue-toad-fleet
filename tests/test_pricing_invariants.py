"""
Pricing invariants — the rules, not examples of the rules.

Every example test in this suite pins one input to one output. These pin the
PROPERTIES that must hold for every input, which is what catches the class of
bug the examples keep missing: a formula that is right for $25 and wrong for
$17.50, a clamp that holds for 3 units and not for 60.

The invariants below are the business's own rules, stated once:

  * all-in is hammer x (1 + absentee fee) x (1 + tax), and never less than hammer
  * a max bid is a CEILING that snaps DOWN onto the house's $5 grid
  * a bid cap is a DEFENSIVE MAXIMUM — the point past which you stop, not what
    you expect to pay, and never a number the math is allowed to walk down
  * a per-unit lot commits hammer x units, and the allocator must see that
  * the budget cap is hard: allocated commitment never exceeds it
  * anything the system cannot establish refuses, it does not guess

Where a property is genuinely one-sided — refusal is always acceptable, a
confident wrong answer never is — the test asserts the asymmetry rather than
demanding a specific verdict.
"""

import re
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from scripts.run_vertex_pipeline import OPERATOR_APPROVED, apply_operator_cap
from src.bidmath import (
    ABSENTEE_FEE, BASE_BID_FRACTION_HIGH, BASE_BID_FRACTION_LOW, BID_INCREMENT,
    DEFAULT_TAX_RATE, HOUSE_MINIMUM_BID, MAX_PLAUSIBLE_UNITS, WI_SALES_TAX_RATE,
    BidMechanic, CompEstimate, Confidence, Decision, Lot, Priority,
    all_in_cost, allocate, bid_fraction_for, clerk_directive, elect,
    mechanic_from_ruling, price_lot, remainder_opportunity, snap_to_increment,
    summarize, units_committed,
)

# Money is denominated in CENTS. A sub-cent hammer is not a price the house can
# call, and `all_in_cost` rounds its output to cents — so `all_in_cost(0.001)`
# floors to 0.00, which is genuinely less than the hammer. That is outside the
# contract rather than a defect in it: `price_lot` refuses anything below one
# $5 increment and `snap_to_increment` floors onto the grid. Quantising the
# strategy states the real domain instead of weakening the invariant.
money = st.integers(min_value=1, max_value=10_000_000).map(lambda c: c / 100)
rate = st.floats(min_value=0.0, max_value=0.30, allow_nan=False,
                 allow_infinity=False)
units = st.integers(min_value=1, max_value=MAX_PLAUSIBLE_UNITS)
mechanics = st.sampled_from(list(BidMechanic))


def comp(low=100.0, high=140.0, n=3, conf=Confidence.HIGH):
    return CompEstimate(low=low, high=high, source_count=n, confidence=conf)


def lot(**kw):
    base = dict(lot_id="L1", caption="c", category="railroad", fit_score=0.85,
                condition_penalty=0.0, comp=comp())
    base.update(kw)
    return Lot(**base)


# ---------------------------------------------------------------- all-in cost

class TestAllInIsAlwaysTheStatedFormula:
    @given(hammer=money, tax=rate)
    def test_matches_the_formula_exactly(self, hammer, tax):
        assert all_in_cost(hammer, tax) == pytest.approx(
            round(hammer * (1 + ABSENTEE_FEE) * (1 + tax), 2), abs=0.01)

    @given(hammer=money, tax=rate)
    def test_never_costs_less_than_the_hammer(self, hammer, tax):
        """Fees and tax only ever add. A cheaper all-in than the bid is a sign
        error, and it would let the allocator fit lots it cannot afford."""
        assert all_in_cost(hammer, tax) >= hammer

    @given(a=money, b=money, tax=rate)
    def test_is_monotonic_in_the_hammer(self, a, b, tax):
        assume(a < b)
        assert all_in_cost(a, tax) <= all_in_cost(b, tax)

    @given(hammer=money)
    def test_the_resale_exemption_is_the_default(self, hammer):
        assert all_in_cost(hammer) == all_in_cost(hammer, DEFAULT_TAX_RATE)
        assert DEFAULT_TAX_RATE == 0.0

    @given(hammer=money)
    def test_an_unexempt_buyer_always_pays_more(self, hammer):
        assert all_in_cost(hammer, WI_SALES_TAX_RATE) >= all_in_cost(hammer)


# --------------------------------------------------------------- the $5 grid

class TestTheFiveDollarGrid:
    @given(amount=money)
    def test_snapping_never_rounds_up(self, amount):
        """A max bid is a ceiling. Snapping UP would authorise spending above
        what the margin math allowed, and above what the allocator checked."""
        assert snap_to_increment(amount) <= amount

    @given(amount=money)
    def test_the_result_sits_on_the_grid(self, amount):
        assert round(snap_to_increment(amount) % BID_INCREMENT, 6) in (0.0, BID_INCREMENT)

    @given(amount=money)
    def test_snapping_is_idempotent(self, amount):
        once = snap_to_increment(amount)
        assert snap_to_increment(once) == once

    @given(amount=money)
    def test_never_produces_a_negative_bid(self, amount):
        assert snap_to_increment(amount) >= 0

    @given(amount=money)
    def test_loses_less_than_one_increment(self, amount):
        assert amount - snap_to_increment(amount) < BID_INCREMENT


# ------------------------------------------------------------ bid fractions

class TestBidFractionStaysInTheDocumentedBand:
    @given(cat=st.text(max_size=30))
    def test_an_uncalibrated_category_uses_the_band_midpoint(self, cat):
        assert bid_fraction_for(cat) == pytest.approx(
            (BASE_BID_FRACTION_LOW + BASE_BID_FRACTION_HIGH) / 2)

    @given(cat=st.text(max_size=30),
           value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False,
                           allow_infinity=False))
    def test_calibration_is_clamped_to_something_sane(self, cat, value):
        """Calibration is learned from prior cycles. A corrupt value must not
        become a 400% bid fraction."""
        assert 0.05 <= bid_fraction_for(cat, {cat: value}) <= 0.90


# ------------------------------------------------------- units and commitment

class TestUnitsCommitted:
    @given(mech=mechanics, n=units, k=st.one_of(st.none(), units))
    def test_always_at_least_one_and_never_more_than_available(self, mech, n, k):
        got = units_committed(mech, n, k)
        assert 1 <= got <= max(1, n)

    @given(n=units, k=st.one_of(st.none(), units))
    def test_straight_ignores_units_and_election(self, n, k):
        assert units_committed(BidMechanic.STRAIGHT, n, k) == 1

    @given(mech=st.sampled_from([BidMechanic.CHOICE, BidMechanic.TIMES_THE_MONEY]),
           n=units, k=units)
    def test_an_election_is_honoured_and_never_exceeds_the_lot(self, mech, n, k):
        assert units_committed(mech, n, k) == min(k, n)

    @given(mech=st.sampled_from([BidMechanic.CHOICE, BidMechanic.TIMES_THE_MONEY,
                                 BidMechanic.UNKNOWN]), n=units)
    def test_no_election_budgets_the_whole_group(self, mech, n):
        """No ceiling stated means no ceiling known. Budget the expensive
        reading — assuming one unit under-books a lot that may charge n."""
        assert units_committed(mech, n, None) == n

    @given(mech=mechanics, n=st.integers(min_value=-50, max_value=0))
    def test_a_malformed_count_never_zeroes_a_real_commitment(self, mech, n):
        assert units_committed(mech, n, None) >= 1


class TestCommittedMoney:
    @given(hammer=money, mech=mechanics, n=units, k=st.one_of(st.none(), units))
    def test_commitment_is_all_in_times_units(self, hammer, mech, n, k):
        d = Decision(lot_id="L", category="c", priority=Priority.B,
                     max_bid=hammer, all_in=all_in_cost(hammer),
                     bid_fraction=0.35, reason="", needs_human_pricing=False,
                     mechanic=mech, unit_count=n, units_wanted=k)
        assert d.committed_all_in == pytest.approx(
            round(d.all_in * units_committed(mech, n, k), 2), abs=0.01)
        assert d.committed_max == pytest.approx(
            round(d.max_bid * units_committed(mech, n, k), 2), abs=0.01)

    @given(hammer=money, mech=mechanics, n=units)
    def test_commitment_is_never_less_than_a_single_unit(self, hammer, mech, n):
        d = Decision(lot_id="L", category="c", priority=Priority.B,
                     max_bid=hammer, all_in=all_in_cost(hammer),
                     bid_fraction=0.35, reason="", needs_human_pricing=False,
                     mechanic=mech, unit_count=n)
        assert d.committed_all_in >= d.all_in

    @given(mech=mechanics, n=units)
    def test_an_unpriced_decision_commits_nothing(self, mech, n):
        d = Decision(lot_id="L", category="c", priority=Priority.SKIP,
                     max_bid=None, all_in=None, bid_fraction=None, reason="",
                     needs_human_pricing=True, mechanic=mech, unit_count=n)
        assert d.committed_all_in is None and d.committed_max is None


# ------------------------------------------------------------- the hard cap

class TestTheBudgetCapIsHard:
    @given(cap=st.floats(min_value=0.0, max_value=5_000, allow_nan=False,
                         allow_infinity=False),
           specs=st.lists(st.tuples(money, mechanics, units), min_size=1,
                          max_size=12))
    @settings(max_examples=200, deadline=None)
    def test_allocated_commitment_never_exceeds_the_cap(self, cap, specs):
        """The single most important property in the module. The operator sets
        a cap so the sheet cannot spend past it; a lot whose commitment the
        allocator under-counts breaches that cap at the block, where it cannot
        be undone."""
        ds = [Decision(lot_id=f"L{i}", category="c", priority=Priority.B,
                       max_bid=snap_to_increment(h) or BID_INCREMENT,
                       all_in=all_in_cost(snap_to_increment(h) or BID_INCREMENT),
                       bid_fraction=0.35, reason="", needs_human_pricing=False,
                       mechanic=m, unit_count=n)
              for i, (h, m, n) in enumerate(specs)]
        out = allocate(ds, budget_cap=cap)
        spent = sum(d.committed_all_in for d in out if d.allocated)
        assert spent <= cap + 0.01

    @given(cap=st.floats(min_value=0.0, max_value=5_000, allow_nan=False,
                         allow_infinity=False),
           specs=st.lists(st.tuples(money, mechanics, units), min_size=1,
                          max_size=12))
    @settings(max_examples=200, deadline=None)
    def test_the_summary_reports_what_was_actually_committed(self, cap, specs):
        ds = [Decision(lot_id=f"L{i}", category="c", priority=Priority.B,
                       max_bid=snap_to_increment(h) or BID_INCREMENT,
                       all_in=all_in_cost(snap_to_increment(h) or BID_INCREMENT),
                       bid_fraction=0.35, reason="", needs_human_pricing=False,
                       mechanic=m, unit_count=n)
              for i, (h, m, n) in enumerate(specs)]
        out = allocate(ds, budget_cap=cap)
        s = summarize(out)
        assert s.committed_all_in == pytest.approx(
            round(sum(d.committed_all_in for d in out if d.allocated), 2), abs=0.02)
        assert s.allocated == sum(1 for d in out if d.allocated)

    @given(specs=st.lists(st.tuples(money, mechanics, units), min_size=1,
                          max_size=8))
    @settings(max_examples=100, deadline=None)
    def test_a_zero_cap_allocates_nothing(self, specs):
        ds = [Decision(lot_id=f"L{i}", category="c", priority=Priority.B,
                       max_bid=snap_to_increment(h) or BID_INCREMENT,
                       all_in=all_in_cost(snap_to_increment(h) or BID_INCREMENT),
                       bid_fraction=0.35, reason="", needs_human_pricing=False,
                       mechanic=m, unit_count=n)
              for i, (h, m, n) in enumerate(specs)]
        assert not any(d.allocated for d in allocate(ds, budget_cap=0.0))


# ---------------------------------------------------------------- price_lot

class TestPriceLotProperties:
    @given(low=st.floats(min_value=1.0, max_value=5_000, allow_nan=False),
           spread=st.floats(min_value=0.0, max_value=5_000, allow_nan=False),
           fit=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
           penalty=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False))
    @settings(max_examples=300, deadline=None)
    def test_any_bid_it_produces_is_on_the_grid_and_positive(
            self, low, spread, fit, penalty):
        d = price_lot(lot(fit_score=fit, condition_penalty=penalty,
                          comp=comp(low=low, high=low + spread)))
        if d.max_bid is not None:
            assert d.max_bid >= BID_INCREMENT
            assert round(d.max_bid % BID_INCREMENT, 6) in (0.0, BID_INCREMENT)

    @given(penalty=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False))
    @settings(max_examples=200, deadline=None)
    def test_a_condition_penalty_can_never_raise_a_bid(self, penalty):
        """`1 - penalty` turns a NEGATIVE penalty into a bid INCREASE. A model
        slip of -0.5 once raised a $41.25 max to $61.88."""
        clean = price_lot(lot(condition_penalty=0.0))
        dirty = price_lot(lot(condition_penalty=penalty))
        if clean.max_bid is not None and dirty.max_bid is not None:
            assert dirty.max_bid <= clean.max_bid

    @given(fit=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    def test_no_external_comp_always_refuses_to_price(self, fit):
        d = price_lot(lot(fit_score=fit,
                          comp=CompEstimate(None, None, 0, Confidence.NONE)))
        assert d.max_bid is None

    @given(n=st.integers(min_value=2, max_value=MAX_PLAUSIBLE_UNITS))
    def test_an_unestablished_mechanic_always_refuses(self, n):
        d = price_lot(lot(mechanic=BidMechanic.UNKNOWN, unit_count=n))
        assert d.max_bid is None and d.needs_mechanic_ruling is True

    @given(n=st.integers(min_value=2, max_value=MAX_PLAUSIBLE_UNITS))
    def test_a_per_unit_lot_prices_below_the_group_comp(self, n):
        """The comp covers the group; the hammer is called per unit. Bidding
        the group's value per unit overbids by roughly the unit count."""
        single = price_lot(lot())
        multi = price_lot(elect(lot(mechanic=BidMechanic.TIMES_THE_MONEY,
                                    unit_count=n), n))
        if single.max_bid and multi.max_bid:
            assert multi.max_bid <= single.max_bid


# ------------------------------------------------------- defensive maxima

class TestBidCapsAreDefensiveMaxima:
    """A cap is the point past which you stop, not what you expect to pay.

    Walking a negotiated cap down to look prudent loses the lot to the next
    bidder, which is the outcome the cap existed to prevent.
    """

    @given(cap=st.floats(min_value=5.0, max_value=1_000, allow_nan=False))
    @settings(deadline=None)
    def test_an_operator_cap_is_applied_as_stated(self, cap):
        capped = [k for k, v in OPERATOR_APPROVED.items() if v.get("cap")]
        assume(capped)
        lot_id = capped[0]
        want = OPERATOR_APPROVED[lot_id]["cap"]
        d = Decision(lot_id=lot_id, category="c", priority=Priority.A,
                     max_bid=cap, all_in=all_in_cost(cap), bid_fraction=0.35,
                     reason="", needs_human_pricing=False)
        assert apply_operator_cap(d).max_bid == want

    @given(cap=st.floats(min_value=5.0, max_value=1_000, allow_nan=False))
    @settings(deadline=None)
    def test_the_capped_all_in_always_matches_bidmaths_own_formula(self, cap):
        """The all-in beside a cap must come from all_in_cost, not a second
        hand-rolled copy of the formula that can drift from it."""
        capped = [k for k, v in OPERATOR_APPROVED.items() if v.get("cap")]
        assume(capped)
        lot_id = capped[0]
        d = Decision(lot_id=lot_id, category="c", priority=Priority.A,
                     max_bid=cap, all_in=all_in_cost(cap), bid_fraction=0.35,
                     reason="", needs_human_pricing=False)
        out = apply_operator_cap(d)
        assert out.all_in == pytest.approx(all_in_cost(out.max_bid), abs=0.01)


# ------------------------------------------------- buyer's choice, per spec

class TestBuyersChoiceProperties:
    @given(data=st.integers(min_value=2, max_value=MAX_PLAUSIBLE_UNITS).flatmap(
        lambda n: st.tuples(st.just(n), st.integers(min_value=1, max_value=n))))
    def test_an_election_is_clamped_to_what_the_lot_holds(self, data):
        n, k = data
        assert elect(lot(mechanic=BidMechanic.CHOICE, unit_count=n),
                     k).units_wanted == k

    @given(n=st.integers(min_value=2, max_value=MAX_PLAUSIBLE_UNITS),
           k=st.integers(min_value=-10, max_value=200))
    def test_an_impossible_election_is_refused_not_silently_fixed(self, n, k):
        assume(not 1 <= k <= n)
        with pytest.raises(ValueError):
            elect(lot(mechanic=BidMechanic.CHOICE, unit_count=n), k)

    @given(data=st.integers(min_value=2, max_value=20).flatmap(
        lambda n: st.tuples(st.just(n), st.integers(min_value=1, max_value=n - 1))))
    @settings(deadline=None)
    def test_a_remainder_never_costs_more_per_unit_than_the_lot_itself(self, data):
        n, k = data
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=n), k))
        assume(d.max_bid is not None)
        r = remainder_opportunity(d)
        if r is not None:
            assert r.max_bid <= d.max_bid
            assert r.unit_count == n - k
            assert r.speculative is True

    @given(n=st.integers(min_value=2, max_value=20))
    def test_taking_everything_leaves_no_remainder(self, n):
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=n), n))
        assert remainder_opportunity(d) is None

    @given(data=st.integers(min_value=2, max_value=20).flatmap(
        lambda n: st.tuples(st.just(n), st.integers(min_value=1, max_value=n - 1))))
    @settings(deadline=None)
    def test_a_speculative_remainder_is_never_auto_sent(self, data):
        n, k = data
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=n), k))
        assume(d.max_bid is not None)
        r = remainder_opportunity(d)
        assume(r is not None)
        out = allocate([r], budget_cap=1e9, auto_send_threshold=1e9)
        assert out[0].auto_send is False


# ---------------------------------------------- the parser refuses, or is right

class TestTheRulingParserIsOneSided:
    """Refusal is always acceptable. A confident wrong answer never is."""

    @given(text=st.text(max_size=120))
    @settings(max_examples=500, deadline=None)
    def test_it_never_invents_an_implausible_unit_count(self, text):
        _, n, k = mechanic_from_ruling(text)
        assert 1 <= n <= MAX_PLAUSIBLE_UNITS
        assert k is None or 1 <= k <= n

    @given(text=st.text(max_size=120))
    @settings(max_examples=500, deadline=None)
    def test_it_never_returns_a_mechanic_outside_the_enum(self, text):
        assert mechanic_from_ruling(text)[0] in set(BidMechanic)

    @given(prefix=st.sampled_from(["no, ", "It is not ", "that isn't ",
                                   "never ", "no longer "]),
           body=st.sampled_from(["a x3 bid", "times the money",
                                 "buyer's choice", "sold as a single lot"]))
    def test_a_denial_never_establishes_the_thing_denied(self, prefix, body):
        assert mechanic_from_ruling(prefix + body)[0] is BidMechanic.UNKNOWN

    @given(amount=st.integers(min_value=1, max_value=999),
           n=st.integers(min_value=2, max_value=9))
    def test_a_dollar_figure_is_never_read_as_the_unit_count(self, amount, n):
        assume(amount != n)
        mech, got, _ = mechanic_from_ruling(f"MAX ${amount}.00 PER TRAY x {n} TRAYS")
        assert mech is BidMechanic.UNKNOWN or got == n


# -------------------------------------------------------- the clerk directive

class TestTheClerkDirectiveNeverMisleads:
    @given(mech=mechanics, n=units, k=st.one_of(st.none(), units),
           priced=st.booleans())
    @settings(max_examples=300, deadline=None)
    def test_an_unbiddable_lot_always_says_do_not_bid(self, mech, n, k, priced):
        d = Decision(lot_id="L", category="c", priority=Priority.B,
                     max_bid=25.0 if priced else None,
                     all_in=all_in_cost(25.0) if priced else None,
                     bid_fraction=0.35, reason="r", needs_human_pricing=not priced,
                     mechanic=mech, unit_count=n, units_wanted=k,
                     needs_mechanic_ruling=(mech is BidMechanic.UNKNOWN and n > 1))
        text = clerk_directive(d)
        if d.max_bid is None or d.needs_mechanic_ruling:
            assert "do not bid" in text.lower()

    @given(hammer=st.floats(min_value=5.0, max_value=500, allow_nan=False),
           n=st.integers(min_value=2, max_value=20))
    def test_a_per_unit_directive_states_arithmetic_that_multiplies(self, hammer, n):
        h = snap_to_increment(hammer) or BID_INCREMENT
        d = Decision(lot_id="L", category="c", priority=Priority.B, max_bid=h,
                     all_in=all_in_cost(h), bid_fraction=0.35, reason="",
                     needs_human_pricing=False,
                     mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=n,
                     units_wanted=n)
        text = clerk_directive(d)
        for per, cnt in re.findall(r"\$([\d,]+\.\d{2}) per unit x (\d+)", text):
            assert float(per.replace(",", "")) * int(cnt) == pytest.approx(
                d.committed_max, abs=0.01)


# --------------------------------------------------------------- opening bid

class TestOpeningBid:
    """The figure the clerk opens at, derived once instead of re-typed.

    `max(5.0, max_bid * 0.35)` was open-coded in the pipeline twice and in the
    single-photo runner once — three copies of the $5 increment and the 35% bid
    fraction, each free to drift from the constants that document them.
    """

    @given(hammer=money)
    def test_never_opens_above_the_max(self, hammer):
        from src.bidmath import opening_bid
        assert opening_bid(hammer) <= max(hammer, BID_INCREMENT)

    @given(hammer=money)
    def test_always_sits_on_the_grid(self, hammer):
        from src.bidmath import opening_bid
        assert round(opening_bid(hammer) % BID_INCREMENT, 6) in (0.0, BID_INCREMENT)

    @given(hammer=money)
    def test_never_opens_below_one_increment(self, hammer):
        from src.bidmath import opening_bid
        assert opening_bid(hammer) >= BID_INCREMENT

    @given(a=money, b=money)
    def test_is_monotonic(self, a, b):
        from src.bidmath import opening_bid
        assume(a < b)
        assert opening_bid(a) <= opening_bid(b)

    def test_reproduces_what_the_scripts_computed_by_hand(self):
        """Same output as the three open-coded copies, so no sheet moves."""
        from src.bidmath import opening_bid
        for h in (5.0, 10.0, 15.0, 25.0, 40.0, 100.0):
            assert opening_bid(h) == snap_to_increment(
                max(BID_INCREMENT, h * BASE_BID_FRACTION_LOW))
