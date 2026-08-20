import pytest
from src.appraisal import (
    Appraisal, Confidence, Question, QuestionKind, StandingRule,
    build_queue, group, learn, DESK_ANSWERABLE,
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
        qs = [q(kind=QuestionKind.APPETITE, cat=f"cat{i}") for i in range(30)]
        r = build_queue(qs, cap=12)
        assert len(r.asked) == 12
        assert len(r.dropped) == 18

    def test_naive_forty_questions_becomes_a_bounded_queue(self):
        qs = [q(kind=QuestionKind.APPETITE, cat="stoneware", lots=(f"L{i}",))
              for i in range(40)]
        r = build_queue(qs, cap=12)
        assert len(r.asked) == 1, "same question about 40 lots is one question"
        assert set(r.asked[0].lot_ids) == {f"L{i}" for i in range(40)}

    def test_asked_are_ordered_by_impact(self):
        r = build_queue([q(kind=QuestionKind.APPETITE, cat=f"c{i}",
                           lots=tuple(f"L{i}{j}" for j in range(i + 1)))
                         for i in range(5)], cap=10)
        impacts = [x.impact for x in r.asked]
        assert impacts == sorted(impacts, reverse=True)

    def test_highest_impact_survives_the_cap(self):
        big = q(kind=QuestionKind.APPETITE, cat="big",
                lots=tuple(f"B{i}" for i in range(9)))
        smalls = [q(kind=QuestionKind.APPETITE, cat=f"s{i}") for i in range(20)]
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
        qs = [q(kind=QuestionKind.APPETITE, cat=f"c{i}", lots=(f"L{i}",))
              for i in range(5)]
        r = build_queue(qs, cap=2)
        assert len(r.flagged_lot_ids) == 3

    def test_every_question_is_accounted_for(self):
        qs = [q(kind=QuestionKind.APPETITE, cat=f"c{i}") for i in range(20)]
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

    def test_object_specific_questions_are_never_memoised_away(self):
        """
        A maker's mark on a new object is a new question every cycle. Memory
        must not learn it away — it surfaces as deferred, since it needs the
        object in hand, but it never silently disappears.
        """
        c1 = build_queue(self._cycle_questions())
        rules = learn([(x, "a") for x in c1.asked], cycle="c1")
        c2 = build_queue(self._cycle_questions(), rules)
        kinds = {x.kind for x in c2.deferred}
        assert QuestionKind.MARK in kinds and QuestionKind.CONDITION in kinds

    def test_decay_converges_not_collapses(self):
        rules: list = []
        counts = []
        for i in range(4):
            r = build_queue(self._cycle_questions(), rules)
            counts.append(len(r.asked))
            rules += learn([(x, "a") for x in r.asked], cycle=f"c{i}")
        assert counts[0] > counts[1]
        assert counts[1] == counts[2] == counts[3], "should settle, not oscillate"

    def test_the_desk_queue_empties_but_the_work_does_not_disappear(self):
        """
        Once the conventions are learned the desk has nothing left to answer,
        which is the point — "needs you less every cycle". What must not happen
        is the object-specific work evaporating with it: those lots keep
        surfacing as deferred, and keep shipping flagged.
        """
        rules: list = []
        for i in range(3):
            r = build_queue(self._cycle_questions(), rules)
            rules += learn([(x, "a") for x in r.asked], cycle=f"c{i}")

        settled = build_queue(self._cycle_questions(), rules)
        assert settled.asked == []
        assert len(settled.deferred) == 2
        assert settled.flagged_lot_ids == {"G", "H"}


class TestMergeKeyVsRuleKey:
    """
    Regression: rule_key was doing double duty as both the merge key and the
    memory key. Two unrelated stoneware shelves collapsed into one prompt that
    named one shelf while covering both — unanswerable, and the single answer
    would have been promoted to a rule governing all future stoneware grouping.
    """

    def _cluster(self, cid, lots, kind=QuestionKind.LOT_GROUPING):
        return Question(kind=kind, category="stoneware",
                        prompt=f"Shelf {cid}: one lot or {len(lots)}?",
                        lot_ids=tuple(lots), value_at_stake=300.0,
                        confidence_gap=1.0, cluster_id=cid)

    def test_distinct_clusters_stay_distinct(self):
        out = group([self._cluster("A", ["a1", "a2", "a3"]),
                     self._cluster("B", ["b1", "b2", "b3"])])
        assert len(out) == 2
        for x in out:
            assert len(x.lot_ids) == 3

    def test_same_cluster_still_merges(self):
        out = group([self._cluster("A", ["a1", "a2"]), self._cluster("A", ["a3"])])
        assert len(out) == 1
        assert sorted(out[0].lot_ids) == ["a1", "a2", "a3"]

    def test_scope_is_also_cluster_scoped(self):
        out = group([self._cluster("A", ["a1"], QuestionKind.SCOPE),
                     self._cluster("B", ["b1"], QuestionKind.SCOPE)])
        assert len(out) == 2

    def test_object_kinds_still_merge_by_category(self):
        mark = lambda l: Question(kind=QuestionKind.MARK, category="stoneware",
                                  prompt="Mark on the base?", lot_ids=(l,),
                                  value_at_stake=100.0, confidence_gap=0.7)
        out = group([mark("a"), mark("b"), mark("c")])
        assert len(out) == 1 and len(out[0].lot_ids) == 3

    def test_memory_still_generalises_across_clusters(self):
        # One answer about shelf A must still suppress shelf B next cycle:
        # rule_key stays (kind, category) even though merge_key does not.
        a = self._cluster("A", ["a1", "a2"])
        rules = learn([(a, "whole shelf")], cycle="c1")
        r = build_queue([self._cluster("B", ["b1", "b2"])], rules)
        assert r.asked == [] and len(r.auto_answered) == 1

    def test_prompt_suffix_does_not_stack(self):
        out = group([self._cluster("A", ["a1"]), self._cluster("A", ["a2"]),
                     self._cluster("A", ["a3"])])
        assert out[0].prompt.count("lots)") == 1
        assert "(3 lots)" in out[0].prompt

    def test_single_lot_keeps_the_bare_prompt(self):
        out = group([self._cluster("A", ["a1"])])
        assert "lots)" not in out[0].prompt


class TestDeskAnswerable:
    """
    The Friday queue is worked at a desk, from the same gallery photos the model
    saw. A hallmark on a clasp or a hairline on a reverse needs the object in
    hand at Saturday's preview — asking before the cutoff produces a queue
    nobody can clear, and buries the conventions that *can* be settled.
    """

    def test_mark_questions_are_deferred_not_asked(self):
        r = build_queue([q(kind=QuestionKind.MARK)])
        assert r.asked == []
        assert len(r.deferred) == 1

    def test_condition_questions_are_deferred_not_asked(self):
        r = build_queue([q(kind=QuestionKind.CONDITION)])
        assert r.asked == [] and len(r.deferred) == 1

    @pytest.mark.parametrize("kind", [
        QuestionKind.POLICY, QuestionKind.LOT_GROUPING,
        QuestionKind.SCOPE, QuestionKind.APPETITE,
    ])
    def test_convention_and_policy_questions_are_asked(self, kind):
        r = build_queue([q(kind=kind)])
        assert len(r.asked) == 1 and r.deferred == []

    def test_deferred_lots_ship_flagged_rather_than_vanishing(self):
        r = build_queue([q(kind=QuestionKind.MARK, lots=("L7",))])
        assert "L7" in r.flagged_lot_ids

    def test_every_question_is_still_accounted_for(self):
        qs = ([q(kind=QuestionKind.MARK, cat=f"m{i}") for i in range(6)]
              + [q(kind=QuestionKind.SCOPE, cat=f"s{i}") for i in range(6)])
        r = build_queue(qs, cap=3)
        assert len(r.asked) + len(r.dropped) + len(r.auto_answered) + len(r.deferred) == 12

    def test_deferred_questions_do_not_consume_the_cap(self):
        qs = ([q(kind=QuestionKind.MARK, cat=f"m{i}") for i in range(10)]
              + [q(kind=QuestionKind.SCOPE, cat=f"s{i}") for i in range(4)])
        r = build_queue(qs, cap=4)
        assert len(r.asked) == 4, "object-specific questions ate the desk queue"

    def test_a_standing_rule_answers_before_the_kind_check(self):
        rule = StandingRule(kind=QuestionKind.MARK, category="stoneware",
                            answer="assume unmarked", learned_cycle="2026-07-11")
        r = build_queue([q(kind=QuestionKind.MARK, cat="stoneware")], [rule])
        assert len(r.auto_answered) == 1 and r.deferred == []

    def test_the_policy_is_overridable_for_a_desk_that_works_differently(self):
        r = build_queue([q(kind=QuestionKind.MARK)],
                        desk_answerable=frozenset({QuestionKind.MARK}))
        assert len(r.asked) == 1 and r.deferred == []

    def test_deferring_everything_leaves_an_honest_empty_queue(self):
        r = build_queue([q(kind=QuestionKind.MARK), q(kind=QuestionKind.CONDITION)])
        assert r.asked == [] and len(r.deferred) == 2
