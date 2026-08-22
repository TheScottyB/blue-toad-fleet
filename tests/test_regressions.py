"""
One test per bug this pipeline has actually shipped.

Every case below was live at some point and cost, or nearly cost, real money on
a real absentee sheet. They are collected here — rather than left scattered in
the suites that happen to cover the same module — so that the list itself is
readable: this is what this system has got wrong, and what must never regress.

Each test names the defect, the direction of the harm, and how it was caught.
Direction matters: a bug that under-bids loses a lot, a bug that over-bids or
double-books spends the operator's cash. The second kind is why these exist.
"""

import json
import re
from pathlib import Path

import pytest

from src.appraiser.images import ImageTooSmall, assert_appraisal_grade
from src.bidmath import (
    BidMechanic, CompEstimate, Confidence, Decision, Lot, Priority,
    all_in_cost, allocate, clerk_directive, elect, mechanic_from_ruling,
    price_lot, remainder_opportunity, summarize, units_committed,
)


def comp(low=100.0, high=140.0, n=3, conf=Confidence.HIGH):
    return CompEstimate(low=low, high=high, source_count=n, confidence=conf)


def lot(**kw):
    base = dict(lot_id="L1", caption="c", category="railroad", fit_score=0.85,
                condition_penalty=0.0, comp=comp())
    base.update(kw)
    return Lot(**base)


class TestMoneyDefects:
    """Bugs that moved, or would have moved, real cash."""

    def test_a_negative_condition_penalty_cannot_raise_a_bid(self):
        """OVER-BID. `1 - penalty` turns a negative penalty into an increase;
        a model slip of -0.5 raised a $41.25 max to $61.88. The field is
        documented 0..1 and nothing enforced it."""
        raised = price_lot(lot(condition_penalty=-0.5))
        clean = price_lot(lot(condition_penalty=0.0))
        assert raised.max_bid <= clean.max_bid

    def test_a_times_the_money_lot_spends_its_full_commitment_from_the_cap(self):
        """UNDER-BOOKED. allocate() summed `all_in` regardless of mechanic, so
        a x3 lot charged the cap a third of its true cost and jumped the
        value-density queue ahead of straight lots while doing it."""
        d = price_lot(lot(mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=3))
        assert allocate([d], budget_cap=d.all_in * 2)[0].allocated is False
        assert allocate([d], budget_cap=d.committed_all_in)[0].allocated is True

    def test_the_jewelry_tray_ruling_reaches_the_money(self, ):
        """The auctioneer ruled the labelled tray run "a x3 bid". Nothing
        carried that to unit_count, so the sheet booked $25 where $75 was
        committed and the operator typed the correction by hand."""
        mech, n, k = mechanic_from_ruling("take all three trays at x3")
        assert (mech, n, k) == (BidMechanic.TIMES_THE_MONEY, 3, 3)
        d = Decision(lot_id="BT-002", category="jewelry", priority=Priority.B,
                     max_bid=25.0, all_in=all_in_cost(25.0), bid_fraction=0.35,
                     reason="", needs_human_pricing=False,
                     mechanic=mech, unit_count=n, units_wanted=k)
        assert d.committed_max == pytest.approx(75.00)
        assert d.committed_all_in == pytest.approx(86.25)

    def test_a_dollar_figure_is_never_read_as_the_unit_count(self):
        """OVER-BID, and outbound. "MAX $25 x 3 TRAYS" — the operator's own bid
        format — parsed as 25 units, priced them at $5.00 each and wrote
        ">> I am taking ALL 50 <<" into a draft with every refusal flag clean.
        \\b matches after a dollar sign, so the pattern read money."""
        for text in ("MAX $25 x 3 TRAYS", "bid to $17.50 x 2 trays", "$30 x 2"):
            mech, n, _ = mechanic_from_ruling(text)
            assert mech is BidMechanic.UNKNOWN or n <= 3, f"{text!r} -> {n}"

    def test_disagreeing_multipliers_do_not_let_position_decide(self):
        """"trays 12 x 14 x 16 go as a x3 bid" took the FIRST match, read 14
        units, and discarded the x3 that was the ruling."""
        assert mechanic_from_ruling(
            "trays 12 x 14 x 16 go as a x3 bid")[0] is BidMechanic.UNKNOWN

    def test_an_unreadable_ruling_refuses_instead_of_pricing(self):
        """FAILED OPEN. The parser cannot establish a count from a ruling it
        could not read, so it returned 1 meaning "nobody counted" — and
        price_lot's refusal required unit_count > 1, making it dead code. Every
        unreadable ruling shipped as a clean, allocated, auto-sendable bid."""
        for text in ("times the money", "yes", "x0 bid"):
            mech, n, k = mechanic_from_ruling(text)
            d = price_lot(lot(mechanic=mech, unit_count=n, units_wanted=k))
            assert d.max_bid is None, f"{text!r} priced at {d.max_bid}"
            assert d.needs_mechanic_ruling is True

    def test_a_denial_never_establishes_the_thing_denied(self):
        """"No, that is not a x3 bid" affirmed x3 — booking the exact
        arrangement the auctioneer had just refused."""
        assert mechanic_from_ruling(
            "No, that is not a x3 bid.")[0] is BidMechanic.UNKNOWN

    def test_choice_with_no_count_does_not_fabricate_one(self):
        """OVER-BID by ~5x. CHOICE invented unit_count=1 when no count was
        supplied — which is how both production callers call it — suppressing
        price_lot's divide-down and making the whole group's value the ceiling
        for a single unit."""
        mech, n, k = mechanic_from_ruling("buyer's choice, take 3")
        assert not (mech is BidMechanic.CHOICE and n == 1)

    def test_a_speculative_remainder_never_auto_sends(self):
        """A remainder bid exists only if the winner declines part of the lot.
        Contingent money that reads like committed money gets bid."""
        d = price_lot(elect(lot(mechanic=BidMechanic.CHOICE, unit_count=5), 2))
        r = remainder_opportunity(d)
        assert r.speculative is True
        assert allocate([r], budget_cap=1e9,
                        auto_send_threshold=1e9)[0].auto_send is False
        assert "only if" in clerk_directive(r).lower()


class TestArtifactsAgreeWithEachOther:
    """Defects where two surfaces described the same sheet differently."""

    def test_the_pitch_banner_totals_committed_money(self):
        """build_pitch summed max_bid and all_in, so the banner disagreed with
        the sheet header on the same page. Worse: those figures seed
        allowed_amounts, so invented_amounts flagged the TRUE total as a
        hallucination and the fallback printed the understated one — the guard
        built to stop a model inventing numbers enforcing the wrong one."""
        from src.gate.pitch import build_pitch, invented_amounts
        from src.server import get_aug22_state
        _, _, _, decisions, _, _, captions = get_aug22_state()
        allocated = [d for d in decisions if d.allocated]
        facts = build_pitch(allocated, captions, [])
        s = summarize(decisions)
        assert facts.committed_max == pytest.approx(s.committed_max)
        assert facts.committed_all_in == pytest.approx(s.committed_all_in)
        honest = (f"Total committed is ${s.committed_max:,.2f}, "
                  f"or ${s.committed_all_in:,.2f} with the house fee.")
        assert invented_amounts(honest, facts.allowed_amounts) == []

    def test_the_console_cards_sum_to_the_console_header(self):
        """Cards printed per-unit all-in while the header printed committed, so
        the operator approved "all-in $28.75" for an $86.25 commitment."""
        from starlette.testclient import TestClient
        from src.server import app
        html = TestClient(app).get("/").text
        # Skip cards still print a max; the header is allocated committed.
        cards = [float(x.replace(",", "")) for x in
                 re.findall(
                     r'<div class="card [^"]*" data-allocated="1">[\s\S]*?all-in \$([\d,]+\.\d{2})</span>',
                     html)]
        hdr = re.search(r"\$([\d,]+\.\d{2}) committed", html)
        assert hdr, "console header has no committed figure"
        assert sum(cards) == pytest.approx(
            float(hdr.group(1).replace(",", "")), abs=0.01)

    def test_the_email_states_per_unit_arithmetic_that_multiplies(self):
        """The compiled email printed "MAX $25.00" on a line contributing
        $75.00 to its own total — a $50 gap a clerk could not reconcile."""
        email = Path("data/aug22_absentee_bid_email.txt")
        if not email.is_file():
            pytest.skip("no compiled email")
        for per, n, total in re.findall(
                r"MAX\s*\$\s*([\d,]+\.\d{2})\s*PER UNIT\s*x\s*(\d+)"
                r"[^\n]*?=\s*\$\s*([\d,]+\.\d{2})\s*TOTAL", email.read_text()):
            assert float(per.replace(",", "")) * int(n) == pytest.approx(
                float(total.replace(",", "")), abs=0.01)

    def test_the_email_does_not_contradict_its_own_per_lot_instruction(self):
        """The footer stated a blanket one-unit rule 25 lines below a per-lot
        line reading ">> I am taking ALL 3 <<" — two directives to a third
        party with $50 riding on which he followed."""
        email = Path("data/aug22_absentee_bid_email.txt")
        if not email.is_file():
            pytest.skip("no compiled email")
        text = email.read_text()
        if "taking ALL" in text:
            assert "any OTHER" in text, (
                "footer states a blanket one-unit rule while a lot line takes "
                "all N; the exception must be named")


class TestIngestDefects:
    def test_a_thumbnail_is_refused_before_the_credential_check(self):
        """Every appraisal before 2026-08-20 17:45 ran on 140x105 thumbnails.
        The model said so in its own condition_notes and emitted a generic
        question per lot; a queue of "dumb AI" questions was the symptom and a
        5KB thumbnail was the cause."""
        tiny = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"
                b"\x00\x00\xff\xc0\x00\x11\x08\x00\x69\x00\x8c\x03\x01\x22\x00")
        with pytest.raises(ImageTooSmall):
            assert_appraisal_grade(tiny, lot_id="BT-000")

    def test_no_photo_at_all_is_refused_rather_than_appraised_from_caption(self):
        with pytest.raises(ImageTooSmall):
            assert_appraisal_grade(None, lot_id="BT-000")

    def test_the_gallery_sequence_is_read_from_the_manifest_not_positionally(self):
        """AuctionZip's photopanel does not list `_th` tags in sequence order;
        indexing by position returned a photo two off the one requested while
        looking entirely correct."""
        man = Path("data/aug22_gallery_4160518/manifest.json")
        if not man.is_file():
            pytest.skip("no cached manifest")
        photos = json.loads(man.read_text())["photos"]
        by_seq = {p["sequence"]: p["photo_id"] for p in photos}
        assert by_seq[2] == "838421481"
        assert by_seq[181] == "838424282"
        assert by_seq[87] == "838422448"


class TestOperatorDecisionsSurvive:
    def test_a_declined_lot_carries_its_reason(self):
        """Declines are recorded, not deleted, so the reasoning survives the
        person who made it."""
        from scripts.run_vertex_pipeline import OPERATOR_APPROVED
        for lot_id, rec in OPERATOR_APPROVED.items():
            if rec.get("fit") is None:
                assert rec.get("why", "").strip(), f"{lot_id} declined silently"

    def test_bt_181_is_not_bid_alongside_bt_002(self):
        """BT-181 is a close-up of trays already inside BT-002. Bidding both
        buys the same three trays twice."""
        from src.server import get_aug22_state
        _, _, _, decisions, _, _, _ = get_aug22_state()
        bid = {d.lot_id for d in decisions if d.allocated}
        assert not ("BT-002" in bid and "BT-181" in bid)

    def test_an_operator_cap_is_not_walked_down_by_a_condition_penalty(self):
        """A max is a ceiling you only reach if pushed. Reducing it to look
        prudent loses the lot to the next bidder, which is the outcome the cap
        existed to prevent."""
        from scripts.run_vertex_pipeline import OPERATOR_APPROVED, apply_operator_cap
        for lot_id, rec in OPERATOR_APPROVED.items():
            cap = rec.get("cap")
            if cap is None:
                continue
            d = Decision(lot_id=lot_id, category="c", priority=Priority.A,
                         max_bid=cap * 0.4, all_in=all_in_cost(cap * 0.4),
                         bid_fraction=0.35, reason="", needs_human_pricing=False)
            assert apply_operator_cap(d).max_bid == cap


class TestTheConsoleShowsTheClerkDirective:
    """`clerk_directive` is the one line that says what to DO with a lot, and it
    had no caller outside its own tests — the same defect this session twice
    criticised elsewhere: a function built, tested, and wired to nothing.

    The operator reads the console. A lot whose mechanic says DO NOT BID, or
    whose per-unit price commits three times its printed max, should say so on
    the card rather than only in a module nobody calls.
    """

    def test_a_per_unit_lot_states_its_directive_on_the_card(self):
        from starlette.testclient import TestClient
        from src.server import app
        from src.bidmath import BidMechanic
        from src.server import get_aug22_state
        _, _, _, decisions, _, _, _ = get_aug22_state()
        per_unit = [d for d in decisions if d.allocated
                    and d.mechanic is not BidMechanic.STRAIGHT]
        if not per_unit:
            pytest.skip("no per-unit lot on the current sheet")
        html = TestClient(app).get("/").text
        for d in per_unit:
            assert "times the money" in html.lower() or "buyer's choice" in html.lower(), (
                f"{d.lot_id} commits {d.unit_count} units and the console never "
                f"says which mechanic")

    def test_the_directive_does_not_disturb_the_card_money_sum(self):
        """The console header and its cards must still reconcile — the directive
        is prose, not a second set of figures to be summed."""
        import re as _re
        from starlette.testclient import TestClient
        from src.server import app, get_aug22_state
        from src.bidmath import summarize
        _, _, _, decisions, _, _, _ = get_aug22_state()
        html = TestClient(app).get("/").text
        cards = [float(x.replace(",", "")) for x in
                 _re.findall(
                     r'<div class="card [^"]*" data-allocated="1">[\s\S]*?all-in \$([\d,]+\.\d{2})</span>',
                     html)]
        assert sum(cards) == pytest.approx(
            summarize(decisions).committed_all_in, abs=0.01)
