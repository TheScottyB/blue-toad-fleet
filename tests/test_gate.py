import re
import pytest
from src.appraisal import Question, QuestionKind, StandingRule, build_queue, learn
from src.bidmath import (
    CompEstimate, Confidence, Lot, allocate, price_lot, summarize,
)
from src.gate import CycleView, render_console


def _lot(i, fit=0.85, low=100.0, high=140.0, n=3, conf=Confidence.HIGH):
    return Lot(lot_id=f"BT-{i:03d}", caption=f"item {i}", category="stoneware",
               fit_score=fit, condition_penalty=0.1,
               comp=CompEstimate(low=low, high=high, source_count=n, confidence=conf))


def _view(lots=None, questions=(), rules=(), cap=2205.0, thresh=40.0):
    lots = lots or [_lot(i) for i in range(4)]
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
        h = render_console(_view(questions=[_q()]))
        assert "Is there a mark on the base?" in h
        assert "Needs your eye" in h

    def test_photo_requests_are_marked(self):
        assert ">photo<" in render_console(_view(questions=[_q(photo=True)]))

    def test_memory_answers_render_separately(self):
        rule = StandingRule(kind=QuestionKind.SCOPE, category="stoneware",
                            answer="whole shelf", learned_cycle="2026-07-11")
        h = render_console(_view(questions=[_q(kind=QuestionKind.SCOPE)], rules=[rule]))
        assert "Answered from memory" in h
        assert "whole shelf" in h and "2026-07-11" in h

    def test_empty_queue_says_so(self):
        assert "Nothing ambiguous" in render_console(_view())

    def test_dropped_questions_are_disclosed_not_hidden(self):
        qs = [_q(cat=f"c{i}", lots=(f"BT-{i:03d}",)) for i in range(20)]
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
        q = Question(kind=QuestionKind.MARK, category="stoneware",
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
