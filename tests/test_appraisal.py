import pytest
from src.appraisal import (
    Appraisal, Confidence, Question, QuestionKind, StandingRule,
    build_queue, group, learn,
)


def q(kind=QuestionKind.MARK, cat="stoneware", lots=("L1",), value=100.0,
      gap=0.7, photo=False, prompt="?"):
    return Question(kind=kind, category=cat, prompt=prompt, lot_ids=tuple(lots),
                    value_at_stake=value, confidence_gap=gap, wants_photo=photo)


class TestAppraisal:
    def test_carries_attribution_not_price(self):
        a = Appraisal(lot_id="L1", category="stoneware",
                      identification="Red Wing 5 gallon crock",
                      attributes={"mark": "wing", "damage": "hairline to base"},
                      confidence=Confidence.HIGH)
        assert "price" not in a.__dict__
        assert a.attributes["mark"] == "wing"

    def test_confidence_gap_ordering(self):
        gaps = [Appraisal("L", "c", "x", confidence=k).confidence_gap
                for k in (Confidence.HIGH, Confidence.MEDIUM,
                          Confidence.LOW, Confidence.NONE)]
        assert gaps == sorted(gaps)


class TestImpact:
    def test_breadth_dominates(self):
        wide = q(lots=("A", "B", "C", "D", "E", "F"))
        narrow = q(lots=("A",))
        assert wide.impact > narrow.impact

    def test_kind_weighting(self):
        grouping = q(kind=QuestionKind.LOT_GROUPING)
        appetite = q(kind=QuestionKind.APPETITE)
        assert grouping.impact > appetite.impact

    def test_confidence_gap_raises_impact(self):
        assert q(gap=1.0).impact > q(gap=0.1).impact

    def test_value_is_damped_not_linear(self):
        cheap, dear = q(value=100.0), q(value=10_000.0)
        ratio = dear.impact / cheap.impact
        assert 1 < ratio < 10, "one expensive lot must not monopolise the queue"


class TestGroup:
    def test_merges_same_kind_and_category(self):
        out = group([q(lots=("A",)), q(lots=("B",)), q(lots=("C",))])
        assert len(out) == 1
        assert set(out[0].lot_ids) == {"A", "B", "C"}

    def test_does_not_merge_across_categories(self):
        out = group([q(cat="stoneware"), q(cat="railroad")])
        assert len(out) == 2

    def test_does_not_merge_across_kinds(self):
        out = group([q(kind=QuestionKind.MARK), q(kind=QuestionKind.SCOPE)])
        assert len(out) == 2

    def test_merged_value_accumulates(self):
        out = group([q(lots=("A",), value=100.0), q(lots=("B",), value=50.0)])
        assert out[0].value_at_stake == pytest.approx(150.0)

    def test_merged_keeps_widest_confidence_gap(self):
        out = group([q(lots=("A",), gap=0.2), q(lots=("B",), gap=0.9)])
        assert out[0].confidence_gap == pytest.approx(0.9)

    def test_photo_request_survives_merge(self):
        out = group([q(lots=("A",), photo=False), q(lots=("B",), photo=True)])
        assert out[0].wants_photo is True

    def test_dedupes_repeated_lot_ids(self):
        out = group([q(lots=("A",)), q(lots=("A", "B"))])
        assert sorted(out[0].lot_ids) == ["A", "B"]


class TestBuildQueue:
    def test_hard_cap_is_respected(self):
        qs = [q(cat=f"cat{i}") for i in range(30)]
        r = build_queue(qs, cap=12)
        assert len(r.asked) == 12
        assert len(r.dropped) == 18

    def test_naive_forty_questions_becomes_a_bounded_queue(self):
        qs = [q(cat="stoneware", lots=(f"L{i}",)) for i in range(40)]
        r = build_queue(qs, cap=12)
        assert len(r.asked) == 1, "same question about 40 lots is one question"
        assert set(r.asked[0].lot_ids) == {f"L{i}" for i in range(40)}

    def test_asked_are_ordered_by_impact(self):
        r = build_queue([q(cat=f"c{i}", lots=tuple(f"L{i}{j}" for j in range(i + 1)))
                         for i in range(5)], cap=10)
        impacts = [x.impact for x in r.asked]
        assert impacts == sorted(impacts, reverse=True)

    def test_highest_impact_survives_the_cap(self):
        big = q(cat="big", lots=tuple(f"B{i}" for i in range(9)))
        smalls = [q(cat=f"s{i}") for i in range(20)]
        r = build_queue(smalls + [big], cap=3)
        assert big.rule_key in {x.rule_key for x in r.asked}

    def test_standing_rule_suppresses_the_question(self):
        rule = StandingRule(kind=QuestionKind.SCOPE, category="stoneware",
                            answer="whole shelf", learned_cycle="c1")
        r = build_queue([q(kind=QuestionKind.SCOPE, cat="stoneware")], [rule])
        assert r.asked == []
        assert len(r.auto_answered) == 1
        assert r.auto_answered[0][1].answer == "whole shelf"

    def test_rule_does_not_leak_across_categories(self):
        rule = StandingRule(kind=QuestionKind.SCOPE, category="stoneware",
                            answer="whole shelf", learned_cycle="c1")
        r = build_queue([q(kind=QuestionKind.SCOPE, cat="railroad")], [rule])
        assert len(r.asked) == 1

    def test_dropped_lots_are_flagged_not_lost(self):
        qs = [q(cat=f"c{i}", lots=(f"L{i}",)) for i in range(5)]
        r = build_queue(qs, cap=2)
        assert len(r.flagged_lot_ids) == 3

    def test_every_question_is_accounted_for(self):
        qs = [q(cat=f"c{i}") for i in range(20)]
        r = build_queue(qs, cap=7)
        assert len(r.asked) + len(r.dropped) + len(r.auto_answered) == 20

    def test_empty_input_is_safe(self):
        r = build_queue([])
        assert r.asked == [] and r.dropped == []


class TestLearn:
    def test_conventions_generalise(self):
        rules = learn([(q(kind=QuestionKind.SCOPE, cat="stoneware"), "whole shelf")],
                      cycle="2026-07-11")
        assert len(rules) == 1
        assert rules[0].answer == "whole shelf"
        assert rules[0].learned_cycle == "2026-07-11"

    def test_object_specific_answers_do_not_generalise(self):
        rules = learn([(q(kind=QuestionKind.MARK), "yes, wing mark")], cycle="c1")
        assert rules == [], "a mark on one base teaches nothing reusable"

    def test_condition_does_not_generalise(self):
        assert learn([(q(kind=QuestionKind.CONDITION), "chipped")], cycle="c1") == []

    def test_appetite_generalises(self):
        rules = learn([(q(kind=QuestionKind.APPETITE, cat="native american"), "no")],
                      cycle="c1")
        assert len(rules) == 1


class TestTwoCycleDecay:
    """The video's learning beat, as a test."""

    def _cycle_questions(self):
        return [
            q(kind=QuestionKind.LOT_GROUPING, cat="stoneware", lots=("A", "B", "C")),
            q(kind=QuestionKind.SCOPE, cat="advertising", lots=("D", "E")),
            q(kind=QuestionKind.APPETITE, cat="native american", lots=("F",)),
            q(kind=QuestionKind.MARK, cat="stoneware", lots=("G",)),
            q(kind=QuestionKind.CONDITION, cat="railroad", lots=("H",)),
        ]

    def test_second_cycle_asks_strictly_fewer(self):
        c1 = build_queue(self._cycle_questions())
        answered = [(x, "answer") for x in c1.asked]
        rules = learn(answered, cycle="c1")

        c2 = build_queue(self._cycle_questions(), rules)
        assert len(c2.asked) < len(c1.asked)
        assert len(c2.auto_answered) == 3  # grouping, scope, appetite

    def test_object_specific_questions_still_asked_next_cycle(self):
        c1 = build_queue(self._cycle_questions())
        rules = learn([(x, "a") for x in c1.asked], cycle="c1")
        c2 = build_queue(self._cycle_questions(), rules)
        kinds = {x.kind for x in c2.asked}
        assert QuestionKind.MARK in kinds and QuestionKind.CONDITION in kinds

    def test_decay_converges_not_collapses(self):
        rules: list = []
        counts = []
        for i in range(4):
            r = build_queue(self._cycle_questions(), rules)
            counts.append(len(r.asked))
            rules += learn([(x, "a") for x in r.asked], cycle=f"c{i}")
        assert counts[0] > counts[1]
        assert counts[1] == counts[2] == counts[3], "should settle, not hit zero"
