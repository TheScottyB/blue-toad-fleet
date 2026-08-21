"""
The curator's pitch.

Who is in the pitch is a decision. How it reads is writing. Those are different
jobs and they are split here on purpose: build_pitch selects from the allocated
sheet by rule, and Gemma is handed the result and asked only for prose.

A language model that could pick the lots could also invent one. A language
model handed a finished list can only phrase it — and the money guard below
makes that a property of the code rather than a hope about the prompt.
"""

import pytest

from src.bidmath import Decision, Priority
from src.gate.pitch import (
    build_pitch, invented_amounts, PitchFacts,
)


def dec(lot_id, max_bid, category="stoneware", auto=True, allocated=True):
    return Decision(
        lot_id=lot_id, category=category,
        priority=Priority.A if max_bid and max_bid >= 35 else Priority.B,
        max_bid=max_bid,
        all_in=round(max_bid * 1.15, 2) if max_bid else None,
        bid_fraction=0.38, reason="test", needs_human_pricing=False,
        auto_send=auto, allocated=allocated,
    )


class TestBuildPitch:
    def test_alpha_picks_are_the_biggest_commitments(self):
        p = build_pitch([dec("BT-001", 100.0), dec("BT-002", 25.0), dec("BT-003", 5.0),
                         dec("BT-004", 40.0), dec("BT-005", 15.0)], {})
        assert [l.lot_id for l in p.alpha] == ["BT-001", "BT-004", "BT-002"]

    def test_alpha_is_capped_at_three(self):
        p = build_pitch([dec(f"BT-{i:03d}", 100.0 - i) for i in range(8)], {})
        assert len(p.alpha) <= 3

    def test_fast_smalls_are_the_auto_send_remainder(self):
        """Everything past the top three that ships without a conversation."""
        p = build_pitch([dec("BT-001", 100.0, auto=False), dec("BT-002", 40.0),
                         dec("BT-003", 30.0), dec("BT-004", 20.0),
                         dec("BT-005", 10.0, auto=False)], {})
        assert [l.lot_id for l in p.alpha] == ["BT-001", "BT-002", "BT-003"]
        assert [l.lot_id for l in p.fast_smalls] == ["BT-004"], \
            "a lot needing approval is not a fast small"

    def test_unallocated_lots_are_not_pitched(self):
        p = build_pitch([dec("BT-009", None, allocated=False)], {})
        assert p.alpha == [] and p.fast_smalls == []

    def test_captions_are_carried_so_the_writer_never_guesses_what_a_lot_is(self):
        p = build_pitch([dec("BT-001", 100.0)], {"BT-001": "Topps run, 1956-1962"})
        assert p.alpha[0].caption == "Topps run, 1956-1962"

    def test_the_totals_come_from_the_sheet_not_the_writer(self):
        p = build_pitch([dec("BT-001", 100.0), dec("BT-002", 25.0)], {})
        assert p.committed_max == 125.0
        assert p.committed_all_in == pytest.approx(143.75)

    def test_selection_is_deterministic(self):
        ds = [dec("BT-003", 40.0), dec("BT-001", 100.0), dec("BT-002", 40.0)]
        assert [l.lot_id for l in build_pitch(ds, {}).alpha] == \
               [l.lot_id for l in build_pitch(list(reversed(ds)), {}).alpha]


class TestTheMoneyGuard:
    """
    Gemma is told not to invent figures. Telling is not enforcing — a model that
    writes "$450" into a bid pitch has put a number in front of the owner that
    no part of the system computed, and this project's whole claim is that it
    does not do that.
    """

    def test_a_figure_from_the_facts_is_allowed(self):
        assert invented_amounts("Recommend holding at $100.", {100.0}) == []

    def test_a_figure_that_appears_nowhere_is_caught(self):
        assert invented_amounts("Worth up to $450 all day.", {100.0}) == [450.0]

    def test_commas_and_cents_still_match(self):
        assert invented_amounts("committed $1,250.00 total", {1250.0}) == []

    def test_several_inventions_are_all_reported(self):
        got = invented_amounts("$20 here and $30 there", {100.0})
        assert sorted(got) == [20.0, 30.0]

    def test_prose_with_no_money_is_clean(self):
        assert invented_amounts("Keep the Topps run; skip the tools.", set()) == []

    def test_percentages_are_not_mistaken_for_money(self):
        assert invented_amounts("a 38% margin target", {100.0}) == []


class TestTheCuratorVoice:
    """
    Gemma writes the prose. Everything it is allowed to know arrives in the
    prompt, and anything it invents is thrown away rather than shown.
    """

    def test_the_prompt_carries_the_lots_and_never_the_comps(self):
        from src.gate.pitch import build_curator_prompt
        facts = build_pitch([dec("BT-001", 100.0, category="vintage cards")],
                            {"BT-001": "Topps run 1956-1962"})
        prompt = build_curator_prompt(facts)
        assert "BT-001" in prompt and "Topps run 1956-1962" in prompt
        for banned in ("comp", "low_mid", "resale", "margin"):
            assert banned not in prompt.lower(), f"the writer must not see {banned}"

    def test_the_prompt_states_every_figure_it_may_use(self):
        from src.gate.pitch import build_curator_prompt
        facts = build_pitch([dec("BT-001", 100.0)], {})
        prompt = build_curator_prompt(facts)
        assert "100" in prompt and "115" in prompt

    def test_invented_money_falls_back_to_the_deterministic_line(self):
        from src.gate.pitch import curator_voice
        facts = build_pitch([dec("BT-001", 100.0)], {})
        out = curator_voice(facts, writer=lambda _p: "Easily worth $900 at retail.")
        assert "$900" not in out
        assert "BT-001" in out, "the fallback must still name the lots"

    def test_clean_prose_is_passed_through(self):
        from src.gate.pitch import curator_voice
        facts = build_pitch([dec("BT-001", 100.0)], {})
        out = curator_voice(facts, writer=lambda _p: "Hold BT-001 at $100; the rest can ride.")
        assert out == "Hold BT-001 at $100; the rest can ride."

    def test_a_writer_that_fails_falls_back_rather_than_breaking_the_console(self):
        from src.gate.pitch import curator_voice
        def boom(_p):
            raise RuntimeError("model unavailable")
        facts = build_pitch([dec("BT-001", 100.0)], {})
        out = curator_voice(facts, writer=boom)
        assert "BT-001" in out

    def test_an_empty_sheet_says_so_without_calling_the_model(self):
        from src.gate.pitch import curator_voice
        called = []
        out = curator_voice(build_pitch([], {}), writer=lambda p: called.append(p) or "x")
        assert called == []
        assert out
