"""Durable standing-rule store. No Firestore, no Vertex."""

import json
from pathlib import Path

import pytest

from src.appraisal import Question, QuestionKind, StandingRule, learn
from src.memory.ids import make_question_id, make_rule_id, normalize_category
from src.memory.store import (
    FileRuleStore, InMemoryRuleStore, MemoryConflict, StandingRuleRecord,
)


SHOP = "richmond-general"


def _rec(**kw) -> StandingRuleRecord:
    base = dict(
        shop_id=SHOP,
        kind=QuestionKind.APPETITE,
        category="railroadiana",
        answer="SKIP — no wall space",
        learned_cycle="2026-08-22",
        source_question_id="q_test",
        active=True,
        revision=1,
    )
    base.update(kw)
    return StandingRuleRecord(**base)


class TestIds:
    def test_category_normalizes_case_and_space(self):
        assert normalize_category("  Railroadiana ") == normalize_category("railroadiana")

    def test_rule_id_stable_across_category_spelling(self):
        a = make_rule_id(SHOP, "appetite", "Railroadiana")
        b = make_rule_id(SHOP, "appetite", "railroadiana")
        assert a == b and len(a) == 64

    def test_question_id_is_stable(self):
        q = Question(
            kind=QuestionKind.APPETITE, category="railroadiana",
            prompt="want these?", lot_ids=("BT-099", "BT-100"),
        )
        assert make_question_id("2026-08-22", q) == make_question_id("2026-08-22", q)
        assert make_question_id("2026-08-22", q).startswith("q_")


class TestLearnAllowlist:
    def test_mark_never_becomes_a_store_record(self):
        q = Question(kind=QuestionKind.MARK, category="stoneware",
                     prompt="mark?", lot_ids=("BT-041",))
        assert learn([(q, "wing mark")], cycle="c1") == []


class TestInMemoryStore:
    def test_put_then_active_rules(self):
        store = InMemoryRuleStore()
        store.put(_rec())
        rules = store.active_rules(SHOP)
        assert len(rules) == 1
        assert rules[0].category == "railroadiana"
        assert rules[0].answer.startswith("SKIP")

    def test_wrong_revision_conflicts(self):
        store = InMemoryRuleStore()
        store.put(_rec())
        with pytest.raises(MemoryConflict):
            store.put(_rec(answer="BUY", revision=1), expected_revision=0)

    def test_history_appends_on_replace(self):
        store = InMemoryRuleStore()
        store.put(_rec())
        store.put(_rec(answer="BUY", revision=2), expected_revision=1)
        events = store.history(SHOP, make_rule_id(SHOP, "appetite", "railroadiana"))
        assert len(events) == 2
        assert events[-1]["answer"] == "BUY"

    def test_shops_are_isolated(self):
        store = InMemoryRuleStore()
        store.put(_rec())
        assert store.active_rules("other-shop") == []


class TestFileStoreRestart:
    def test_learned_rule_survives_new_store_instance(self, tmp_path):
        path = tmp_path / "rules.json"
        FileRuleStore(path).put(_rec())
        revived = FileRuleStore(path)
        rules = revived.active_rules(SHOP)
        assert len(rules) == 1
        assert rules[0].learned_cycle == "2026-08-22"
        assert rules[0].kind is QuestionKind.APPETITE

    def test_seed_only_fills_an_empty_file(self, tmp_path):
        path = tmp_path / "rules.json"
        seed = [StandingRule(
            kind=QuestionKind.APPETITE, category="jewelry",
            answer="BUY", learned_cycle="2026-08-20",
        )]
        FileRuleStore(path, seed=seed)
        FileRuleStore(path, seed=seed).put(_rec())
        data = json.loads(path.read_text())
        assert len(data["rules"]) == 2
