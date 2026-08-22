import re
import pytest
from src.appraisal import Question, QuestionKind, StandingRule, build_queue, learn
from src.bidmath import (
    CompEstimate, Confidence, Lot, allocate, price_lot, summarize,
)
from src.gate import CycleView, render_console
from src.intake.spatial import Seat, Zone


def _lot(i, fit=0.85, low=100.0, high=140.0, n=3, conf=Confidence.HIGH):
    return Lot(lot_id=f"BT-{i:03d}", caption=f"item {i}", category="stoneware",
               fit_score=fit, condition_penalty=0.1,
               comp=CompEstimate(low=low, high=high, source_count=n, confidence=conf))


def _view(lots=None, questions=(), rules=(), cap=2205.0, thresh=40.0):
    lots = lots if lots is not None else [_lot(i) for i in range(4)]
    ds = allocate([price_lot(l) for l in lots], cap, thresh)
    return CycleView(
        cycle_id="2026-08-22", auction_date="Sat 2026-08-22", photos_ingested=428,
        queue=build_queue(questions, rules), decisions=ds, summary=summarize(ds),
        budget_cap=cap, auto_send_threshold=thresh,
        captions={l.lot_id: l.caption for l in lots})


def _q(kind=QuestionKind.MARK, cat="stoneware", lots=("BT-000",), photo=False):
    return Question(kind=kind, category=cat, prompt="Is there a mark on the base?",
                    lot_ids=tuple(lots), value_at_stake=190.0,
                    confidence_gap=0.7, wants_photo=photo)


class TestRenderContract:
    def test_produces_a_complete_document(self):
        h = render_console(_view())
        assert h.startswith("<!DOCTYPE html>") and h.rstrip().endswith("</html>")

    def test_is_self_contained(self):
        h = render_console(_view())
        assert "<style>" in h
        assert "src=" not in h and "href=" not in h, "no external assets"

    def test_tags_are_balanced(self):
        h = render_console(_view(questions=[_q()]))
        for tag in ("div", "span", "header", "footer", "body", "html"):
            assert len(re.findall(rf"<{tag}[\s>]", h)) == len(re.findall(rf"</{tag}>", h)), tag

    def test_renders_with_nothing_at_all(self):
        v = _view(lots=[])
        assert render_console(v).startswith("<!DOCTYPE html>")


class TestQuestionQueue:
    def test_questions_appear(self):
        h = render_console(_view(questions=[_q(kind=QuestionKind.APPETITE)]))
        assert "Is there a mark on the base?" in h
        assert "Needs your eye" in h

    def test_answer_controls_post_to_the_real_api(self):
        h = render_console(_view(questions=[_q(kind=QuestionKind.APPETITE)]))
        assert 'data-question-id="q_' in h
        assert 'data-act="answer"' in h
        assert 'fetch("/api/answer"' in h
        assert "X-Operator-Token" in h
        assert "src=" not in h and "href=" not in h

    def test_photo_requests_are_marked(self):
        h = render_console(_view(questions=[_q(kind=QuestionKind.SCOPE, photo=True)]))
        assert ">photo<" in h

    def test_memory_answers_render_separately(self):
        rule = StandingRule(kind=QuestionKind.SCOPE, category="stoneware",
                            answer="whole shelf", learned_cycle="2026-07-11")
        h = render_console(_view(questions=[_q(kind=QuestionKind.SCOPE)], rules=[rule]))
        assert "Answered from memory" in h
        assert "whole shelf" in h and "2026-07-11" in h

    def test_empty_queue_says_so(self):
        assert "Nothing ambiguous" in render_console(_view())

    def test_does_not_claim_nothing_is_ambiguous_while_deferring_work(self):
        """
        "Nothing ambiguous this cycle" is the most confident line the console
        has. It must not appear above a list of questions nobody could answer.
        """
        h = render_console(_view(questions=[_q(kind=QuestionKind.MARK)]))
        assert "Nothing ambiguous" not in h

    def test_dropped_questions_are_disclosed_not_hidden(self):
        qs = [_q(kind=QuestionKind.APPETITE, cat=f"c{i}", lots=(f"BT-{i:03d}",))
              for i in range(20)]
        h = render_console(_view(questions=qs))
        assert "over the cap" in h and "flagged low-confidence" in h


class TestSheet:
    def test_decision_cards_show_money(self):
        h = render_console(_view())
        assert "max $" in h and "all-in $" in h

    def test_auto_send_and_approval_are_distinguished(self):
        lots = [_lot(0, low=20, high=30), _lot(1, low=400, high=600)]
        h = render_console(_view(lots=lots))
        assert "auto-send" in h and "needs approval" in h

    def test_refused_lots_are_prominent_not_hidden(self):
        lots = [_lot(0), Lot(lot_id="BT-099", caption="unmarked basket",
                             category="native american", fit_score=0.78,
                             condition_penalty=0.1,
                             comp=CompEstimate(None, None, 0, Confidence.NONE))]
        h = render_console(_view(lots=lots))
        assert "human pricing required" in h
        assert "unmarked basket" in h

    def test_budget_bar_never_overflows(self):
        h = render_console(_view(lots=[_lot(i, low=500, high=700) for i in range(40)]))
        widths = [float(w) for w in re.findall(r"width:([\d.]+)%", h)]
        assert all(w <= 100.0 for w in widths)


class TestSafety:
    def test_captions_are_escaped(self):
        lots = [Lot(lot_id="BT-000", caption="<script>alert(1)</script>",
                    category="stoneware", fit_score=0.85, condition_penalty=0.0,
                    comp=CompEstimate(100.0, 140.0, 3, Confidence.HIGH))]
        h = render_console(_view(lots=lots))
        assert "<script>alert(1)</script>" not in h
        assert "&lt;script&gt;" in h

    def test_question_prompts_are_escaped(self):
        q = Question(kind=QuestionKind.APPETITE, category="stoneware",
                     prompt="<img onerror=x>", lot_ids=("BT-000",),
                     value_at_stake=1.0, confidence_gap=0.5, wants_photo=False)
        h = render_console(_view(questions=[q]))
        assert "<img onerror=x>" not in h and "&lt;img" in h


class TestFraming:
    def test_carries_the_uncertainty_budget_line(self):
        h = render_console(_view())
        assert "asks when confidence is low" in h
        assert "sends without asking when value is low" in h

    def test_states_that_questions_do_not_block(self):
        assert "do not block" in render_console(_view())


class TestIllustrativeBanner:
    def test_banner_absent_by_default(self):
        assert "Illustrative cycle" not in render_console(_view())

    def test_banner_present_when_flagged(self):
        v = _view(); v.illustrative = True
        assert "Illustrative cycle" in render_console(v)
        assert "the decision code, ranking and memory are real" in render_console(v)

    def test_partial_lot_count_is_disclosed(self):
        v = _view(); v.lots_total = 61
        assert "of 61 lots appraised" in render_console(v)


class TestDeferredQuestions:
    """
    A question the desk cannot answer must still be visible. Filtering it out
    of the queue is right; making it disappear is how nine questions and their
    lots go missing without anyone noticing.
    """

    def test_deferred_questions_are_disclosed_not_hidden(self):
        h = render_console(_view(questions=[_q(kind=QuestionKind.MARK)]))
        assert "1" in h
        assert "preview" in h.lower() or "in hand" in h.lower()

    def test_the_deferred_prompt_itself_is_shown(self):
        h = render_console(_view(questions=[_q(kind=QuestionKind.CONDITION)]))
        assert "Is there a mark on the base?" in h

    def test_deferred_prompts_are_escaped(self):
        q = Question(kind=QuestionKind.MARK, category="stoneware",
                     prompt="<img onerror=x>", lot_ids=("BT-000",),
                     value_at_stake=1.0, confidence_gap=0.5, wants_photo=False)
        h = render_console(_view(questions=[q]))
        assert "<img onerror=x>" not in h and "&lt;img" in h

    def test_no_deferred_section_when_nothing_is_deferred(self):
        h = render_console(_view(questions=[_q(kind=QuestionKind.APPETITE)]))
        assert "needs the item in hand" not in h.lower()

    def test_deferred_lots_are_named_as_shipping_flagged(self):
        h = render_console(_view(questions=[_q(kind=QuestionKind.MARK, lots=("BT-042",))]))
        assert "BT-042" in h


class TestTheCuratorBanner:
    def test_the_pitch_text_is_rendered(self):
        h = render_console(_view(), pitch_text="Hold BT-001; the rest can ride.")
        assert "Hold BT-001; the rest can ride." in h

    def test_the_pitch_text_is_escaped(self):
        h = render_console(_view(), pitch_text="<img onerror=x>")
        assert "<img onerror=x>" not in h and "&lt;img" in h

    def test_the_banner_names_the_model_that_wrote_it(self):
        """A reader should be able to tell prose from computation at a glance."""
        h = render_console(_view(), pitch_text="Anything.")
        assert "gemma" in h.lower()

    def test_without_pitch_text_the_banner_is_omitted_rather_than_faked(self):
        h = render_console(_view())
        assert "Curator" not in h


def _slice_between(html: str, start: str, end: str) -> str:
    i = html.find(start)
    j = html.find(end, i + len(start)) if i >= 0 else -1
    if i < 0 or j < 0:
        return ""
    return html[i:j]


def _holding_strip_html(html: str) -> str:
    m = re.search(
        r'<div class="holding" id="unplaced">.*?</div></div>',
        html,
        re.DOTALL,
    )
    return m.group(0) if m else ""


def _seat_el(html: str, lot_id: str) -> str:
    m = re.search(
        rf'<div class="seat"><b>{re.escape(lot_id)}</b>.*?</div>',
        html,
    )
    assert m is not None, f"{lot_id} seat missing from slice"
    return m.group(0)


class TestShowroomMap:
    def test_topology_title_always_renders(self):
        assert "Pole Barn Showroom Topology" in render_console(_view())

    def test_fake_island_inventory_is_gone(self):
        h = render_console(_view())
        assert "Topps Baseball Cards & Costume Jewelry" not in h

    def test_holding_strip_lists_unplaced_seats(self):
        v = _view()
        v.seats = [
            Seat(lot_id="BT-002", zone=Zone.UNKNOWN, walk_index=2,
                 photo_ids=("838421481", "838424282")),
            Seat(lot_id="BT-087", zone=Zone.UNKNOWN, walk_index=87,
                 photo_ids=("838422448",)),
        ]
        h = render_console(v)
        assert "not yet placed" in h.lower() or "unplaced" in h.lower()
        strip = _holding_strip_html(h)
        assert "BT-002" in strip and "BT-087" in strip
        seat = _seat_el(strip, "BT-002")
        assert "8421481" in seat and "8424282" in seat
        assert "8422448" not in seat
        assert "838422448" not in seat

    def test_zoned_seat_sits_on_its_row_not_only_the_strip(self):
        v = _view()
        v.seats = [
            Seat(lot_id="BT-099", zone=Zone.CENTER_ISLAND_1, walk_index=1,
                 photo_ids=("p1",)),
        ]
        h = render_console(v)
        island1 = _slice_between(
            h, "<b>Island Table 1:</b>", "<b>Island Table 2:</b>")
        assert "BT-099" in island1
        assert _seat_el(island1, "BT-099")
        assert "BT-099" not in _holding_strip_html(h)


class TestStructuredVoiceBanner:
    def test_renders_gemma_voice_prose_when_present(self):
        from src.gate.voice import PitchVoice
        v = _view()
        v.voice = PitchVoice(
            alpha="Keep the Topps at the defensive cap.",
            fast_smalls="Handheld games turn fast.",
            wildcard="Bet the games as the wildcard.",
            pushback="Understood on dropping sports, but keep BT-001.",
        )

        h = render_console(v)
        assert "Keep the Topps at the defensive cap." in h
        assert "Handheld games turn fast." in h
        assert "Understood on dropping sports, but keep BT-001." in h
        assert "Gemma 4" in h

