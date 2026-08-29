import pytest
from src.bidmath import (
    ABSENTEE_FEE, DEFAULT_TAX_RATE, WI_SALES_TAX_RATE,
    CompEstimate, Confidence, Decision, Lot, Priority,
    all_in_cost, allocate, bid_fraction_for, price_lot, snap_to_increment,
    summarize,
)


def comp(low=100.0, high=140.0, n=3, conf=Confidence.HIGH):
    return CompEstimate(low=low, high=high, source_count=n, confidence=conf)


def lot(lot_id="L1", cat="breweriana", fit=0.85, cond=0.0, c=None):
    return Lot(lot_id=lot_id, caption="test", category=cat,
               fit_score=fit, condition_penalty=cond, c=c) if False else Lot(
        lot_id=lot_id, caption="test", category=cat,
        fit_score=fit, condition_penalty=cond, comp=c or comp())


class TestAllInCost:
    def test_applies_absentee_fee_and_tax(self):
        # $100 hammer -> 15% absentee -> 5.5% Walworth County tax
        assert all_in_cost(100.0, WI_SALES_TAX_RATE) == pytest.approx(121.32, abs=0.01)

    def test_default_is_untaxed_because_of_the_resale_exemption(self):
        """Richmond General has a resale exemption on file with Blue Toad.

        The default must be 0, not the county rate: an unexempt default silently
        overstates all-in on every lot, and the allocator then under-fills the
        budget cap against a cost the shop never pays.
        """
        assert DEFAULT_TAX_RATE == 0.0
        assert all_in_cost(100.0) == pytest.approx(115.00, abs=0.01)

    def test_zero_tax(self):
        assert all_in_cost(100.0, 0.0) == pytest.approx(100 * (1 + ABSENTEE_FEE))

    def test_rounds_to_cents(self):
        assert all_in_cost(33.33, 0.07) == round(all_in_cost(33.33, 0.07), 2)


class TestLowMid:
    def test_low_mid_is_between_low_and_midpoint(self):
        c = comp(low=100, high=200)
        # midpoint 150; low-mid = (100 + 150)/2 = 125
        assert c.low_mid == pytest.approx(125.0)

    def test_no_comp_has_no_low_mid(self):
        assert comp(low=None, high=None, n=0, conf=Confidence.NONE).low_mid is None


class TestBidFraction:
    def test_defaults_to_documented_midpoint(self):
        assert bid_fraction_for("anything") == pytest.approx(0.375)

    def test_calibration_overrides_per_category(self):
        cal = {"breweriana": 0.32}
        assert bid_fraction_for("breweriana", cal) == pytest.approx(0.32)
        assert bid_fraction_for("railroad", cal) == pytest.approx(0.375)

    def test_calibration_is_clamped(self):
        assert bid_fraction_for("x", {"x": 5.0}) == pytest.approx(0.90)
        assert bid_fraction_for("x", {"x": -1.0}) == pytest.approx(0.05)


class TestPriceLot:
    def test_prices_a_good_lot(self):
        d = price_lot(lot(c=comp(low=100, high=200)))
        # low_mid 125 * 0.375 = 46.88, snapped down to the $5 grid
        assert d.max_bid == pytest.approx(45.00, abs=0.01)
        assert d.all_in == all_in_cost(d.max_bid)
        assert d.priority is Priority.A
        assert not d.needs_human_pricing

    def test_condition_penalty_reduces_bid(self):
        clean = price_lot(lot(cond=0.0, c=comp(low=100, high=200)))
        worn = price_lot(lot(cond=0.30, c=comp(low=100, high=200)))
        assert worn.max_bid < clean.max_bid
        # The penalty applies to the raw ceiling, which is THEN snapped to the
        # grid — so the drop is quantised and is not a clean 0.7x of the
        # snapped clean bid. 125 * 0.375 * 0.7 = 32.81 -> $30, not $31.50.
        assert worn.max_bid == pytest.approx(snap_to_increment(125 * 0.375 * 0.7), abs=0.01)

    def test_no_external_comp_refuses_to_guess(self):
        d = price_lot(lot(c=comp(low=None, high=None, n=0, conf=Confidence.NONE)))
        assert d.max_bid is None
        assert d.needs_human_pricing is True
        assert d.needs_deep_comps is True
        assert "pending deep comps" in d.reason

    def test_low_fit_without_comps_is_empty_dollar_skip(self):
        d = price_lot(lot(fit=0.20, c=comp(low=None, high=None, n=0, conf=Confidence.NONE)))
        assert d.priority is Priority.SKIP
        assert d.max_bid is None
        assert d.needs_human_pricing is True

    def test_low_fit_with_comps_still_has_a_number(self):
        d = price_lot(lot(lot_id="L", fit=0.20, c=comp(low=40, high=80, n=3)))
        assert d.priority is Priority.SKIP
        assert d.max_bid is not None and d.max_bid > 0
        assert d.needs_human_pricing is False

    def test_priority_bands(self):
        assert price_lot(lot(fit=0.90, c=comp(conf=Confidence.HIGH))).priority is Priority.A
        assert price_lot(lot(fit=0.60, c=comp(conf=Confidence.HIGH))).priority is Priority.B
        assert price_lot(lot(fit=0.40, c=comp(conf=Confidence.LOW, n=1))).priority is Priority.C

    def test_high_fit_but_weak_comp_is_not_priority_a(self):
        d = price_lot(lot(fit=0.90, c=comp(n=1, conf=Confidence.LOW)))
        assert d.priority is Priority.B

    def test_trivial_value_is_skipped(self):
        d = price_lot(lot(c=comp(low=1, high=2)))
        assert d.priority is Priority.SKIP
        assert "below one $5 bidding increment" in d.reason

    def test_calibration_flows_through(self):
        base = price_lot(lot(c=comp(low=100, high=200)))
        tuned = price_lot(lot(c=comp(low=100, high=200)), {"breweriana": 0.32})
        assert tuned.max_bid < base.max_bid


class TestAllocate:
    def _priced(self, n, all_in_each=100.0):
        out = []
        for i in range(n):
            d = price_lot(lot(lot_id=f"L{i}", c=comp(low=200, high=280)))
            out.append(d)
        return out

    def test_respects_budget_cap(self):
        ds = allocate(self._priced(10), budget_cap=300.0)
        spent = sum(d.all_in for d in ds if d.allocated)
        assert spent <= 300.0
        assert any(not d.allocated for d in ds)

    def test_priority_a_allocated_before_b(self):
        a = price_lot(lot(lot_id="A1", fit=0.90, c=comp(low=200, high=280)))
        b = price_lot(lot(lot_id="B1", fit=0.60, c=comp(low=200, high=280)))
        ds = allocate([b, a], budget_cap=a.all_in)
        got = {d.lot_id: d.allocated for d in ds}
        assert got["A1"] is True and got["B1"] is False

    def test_over_budget_lots_are_annotated(self):
        ds = allocate(self._priced(5), budget_cap=1.0)
        assert all("over budget cap" in d.reason for d in ds if not d.allocated)

    def test_unpriced_lots_survive_allocation(self):
        unpriced = price_lot(lot(lot_id="U1", c=comp(None, None, 0, Confidence.NONE)))
        ds = allocate(self._priced(2) + [unpriced], budget_cap=10_000)
        assert any(d.lot_id == "U1" and d.needs_human_pricing for d in ds)

    def test_zero_threshold_means_everything_needs_approval(self):
        ds = allocate(self._priced(3), budget_cap=10_000, auto_send_threshold=0.0)
        assert not any(d.auto_send for d in ds)

    def test_auto_send_below_threshold_only(self):
        cheap = price_lot(lot(lot_id="C1", c=comp(low=20, high=30)))
        dear = price_lot(lot(lot_id="D1", c=comp(low=400, high=600)))
        ds = allocate([cheap, dear], budget_cap=10_000, auto_send_threshold=20.0)
        got = {d.lot_id: d.auto_send for d in ds}
        assert got["C1"] is True and got["D1"] is False

    def test_unallocated_never_auto_sends(self):
        ds = allocate(self._priced(5), budget_cap=1.0, auto_send_threshold=10_000.0)
        assert not any(d.auto_send for d in ds)


def test_allocate_does_not_spend_skip_leftovers():
    from src.bidmath import Decision, Priority, allocate, all_in_cost
    skip = Decision(
        lot_id="S", category="c", priority=Priority.SKIP,
        max_bid=50.0, all_in=all_in_cost(50.0), bid_fraction=0.375,
        reason="fit", needs_human_pricing=False,
    )
    out = allocate([skip], budget_cap=10_000.0)
    assert out[0].allocated is False
    assert out[0].auto_send is False


class TestSummarize:
    def test_counts_and_totals(self):
        ds = allocate(
            [price_lot(lot(lot_id=f"L{i}", c=comp(low=100, high=140))) for i in range(3)]
            + [price_lot(lot(lot_id="U", c=comp(None, None, 0, Confidence.NONE)))]
            + [price_lot(lot(lot_id="S", fit=0.1, c=comp(low=1, high=2)))],
            budget_cap=10_000, auto_send_threshold=1_000.0,
        )
        s = summarize(ds)
        assert s.total_lots == 5
        assert s.allocated == 3
        assert s.needs_human_pricing == 1
        assert s.skipped == 1
        assert s.committed_all_in == pytest.approx(
            sum(d.all_in for d in ds if d.allocated), abs=0.01)

    def test_approval_split_adds_up(self):
        ds = allocate(
            [price_lot(lot(lot_id="a", c=comp(low=20, high=30))),
             price_lot(lot(lot_id="b", c=comp(low=400, high=600)))],
            budget_cap=10_000, auto_send_threshold=20.0)
        s = summarize(ds)
        assert s.auto_send + s.needs_approval == s.allocated


class TestConditionPenaltyIsClamped:
    """condition_penalty is documented 0..1 but nothing enforced it.

    The schema only described the range in prose — no minimum/maximum keys —
    so Vertex's constrained decoding would not reject an out-of-range value
    either. `base * (1 - penalty)` then turns a NEGATIVE penalty into a bid
    INCREASE: a model slip silently raises what the sheet is willing to pay.
    """

    def test_negative_penalty_cannot_raise_the_bid(self):
        clean = price_lot(lot(cond=0.0))
        slipped = price_lot(lot(cond=-0.5))
        assert slipped.max_bid == clean.max_bid

    def test_penalty_above_one_never_produces_a_negative_bid(self):
        d = price_lot(lot(cond=1.7))
        assert d.max_bid is None or d.max_bid >= 0

    def test_penalty_in_range_still_discounts(self):
        """The clamp must not flatten legitimate penalties."""
        clean = price_lot(lot(cond=0.0))
        worn = price_lot(lot(cond=0.30))
        assert worn.max_bid < clean.max_bid


class TestBidIncrement:
    """Blue Toad calls bids in standard $5.00 increments.

    A max bid is a CEILING, so it snaps DOWN to the highest callable bid at or
    below the computed number. Snapping up would authorise spending above what
    the margin math allowed, and can breach the budget cap the allocator just
    checked against.
    """

    def test_max_bid_lands_on_a_five_dollar_increment(self):
        # low-mid 125.0 x 0.38 = 47.50 -> not callable at a $5-increment house
        d = price_lot(lot(cat="unknown-category", c=comp(low=100, high=200)))
        assert d.max_bid is not None
        assert d.max_bid % 5 == 0, f"{d.max_bid} is not on the $5 grid"

    def test_snaps_down_never_up(self):
        d = price_lot(lot(cat="unknown-category", c=comp(low=100, high=200)))
        assert d.max_bid == 45.00  # 47.50 floored, not 50.00 rounded up

    def test_ceiling_below_one_increment_is_not_biddable(self):
        # low-mid 10.0 x 0.38 = 3.80 -> below the smallest callable bid
        d = price_lot(lot(cat="unknown-category", c=comp(low=8, high=12)))
        assert d.max_bid is None
        assert d.priority is Priority.SKIP
        assert "increment" in d.reason


class TestOperatorKeptSeatsFirst:
    """Under abundance, 'most lots for the money' must not crowd out the
    owner's kept lots. Found live 2026-08-29: the full-coverage corpus
    offered 56 cheap allocations and the greedy dropped the $100-capped
    Topps lot the owner explicitly kept."""

    def _decision(self, lot_id, all_in, kept=False):
        from src.bidmath import BidMechanic, Decision, Priority
        return Decision(
            lot_id=lot_id, category="test", priority=Priority.A,
            max_bid=round(all_in / 1.15, 2), all_in=all_in,
            bid_fraction=0.375, reason="test", needs_human_pricing=False,
            operator_kept=kept,
        )

    def test_kept_lot_seats_before_cheaper_machine_picks(self):
        from src.bidmath import allocate
        kept = self._decision("BT-KEPT", 115.0, kept=True)
        cheap = [self._decision(f"BT-{i:03d}", 10.0) for i in range(20)]
        out = allocate(cheap + [kept], budget_cap=120.0)
        seated = {d.lot_id for d in out if d.allocated}
        assert "BT-KEPT" in seated, "the owner's kept lot was crowded out"

    def test_without_the_flag_cheapest_still_wins(self):
        from src.bidmath import allocate
        big = self._decision("BT-BIG", 115.0, kept=False)
        cheap = [self._decision(f"BT-{i:03d}", 10.0) for i in range(20)]
        out = allocate(cheap + [big], budget_cap=120.0)
        seated = {d.lot_id for d in out if d.allocated}
        assert "BT-BIG" not in seated and len(seated) == 12
