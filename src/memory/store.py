"""Standing-rule persistence. Unit tests use memory and a JSON file."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from src.appraisal import QuestionKind, StandingRule
from src.memory.ids import make_rule_id


class MemoryConflict(Exception):
    """Optimistic-concurrency failure on a standing rule."""


@dataclass
class StandingRuleRecord:
    shop_id: str
    kind: QuestionKind | str
    category: str
    answer: str
    learned_cycle: str
    source_question_id: str
    active: bool = True
    revision: int = 1
    review_after: str | None = None

    def __post_init__(self):
        if isinstance(self.kind, str):
            self.kind = QuestionKind(self.kind)

    @property
    def rule_id(self) -> str:
        return make_rule_id(self.shop_id, self.kind.value, self.category)

    def to_standing_rule(self) -> StandingRule:
        return StandingRule(
            kind=self.kind,
            category=self.category,
            answer=self.answer,
            learned_cycle=self.learned_cycle,
        )

    def as_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["rule_id"] = self.rule_id
        return d

    @classmethod
    def from_dict(cls, raw: dict) -> "StandingRuleRecord":
        return cls(
            shop_id=raw["shop_id"],
            kind=raw["kind"],
            category=raw["category"],
            answer=raw["answer"],
            learned_cycle=raw["learned_cycle"],
            source_question_id=raw.get("source_question_id") or "",
            active=bool(raw.get("active", True)),
            revision=int(raw.get("revision") or 1),
            review_after=raw.get("review_after"),
        )


class RuleStore(Protocol):
    backend_name: str
    durable: bool

    def active_rules(self, shop_id: str) -> list[StandingRule]: ...
    def put(
        self, rule: StandingRuleRecord, expected_revision: int | None = None,
    ) -> StandingRuleRecord: ...
    def history(self, shop_id: str, rule_key: str) -> list[dict]: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_records(
    seed: list[StandingRule] | None, shop_id: str,
) -> dict[str, StandingRuleRecord]:
    out: dict[str, StandingRuleRecord] = {}
    for r in seed or []:
        rec = StandingRuleRecord(
            shop_id=shop_id,
            kind=r.kind,
            category=r.category,
            answer=r.answer,
            learned_cycle=r.learned_cycle,
            source_question_id="seed",
        )
        out[rec.rule_id] = rec
    return out


class InMemoryRuleStore:
    backend_name = "memory"
    durable = False

    def __init__(
        self,
        seed: list[StandingRule] | None = None,
        shop_id: str = "richmond-general",
    ):
        self._rules: dict[str, StandingRuleRecord] = _seed_records(seed, shop_id)
        self._events: list[dict] = []

    def active_rules(self, shop_id: str) -> list[StandingRule]:
        return [
            r.to_standing_rule()
            for r in self._rules.values()
            if r.shop_id == shop_id and r.active
        ]

    def put(
        self, rule: StandingRuleRecord, expected_revision: int | None = None,
    ) -> StandingRuleRecord:
        existing = self._rules.get(rule.rule_id)
        current_rev = existing.revision if existing else 0
        if expected_revision is not None and expected_revision != current_rev:
            raise MemoryConflict(
                f"rule {rule.rule_id[:8]} at revision {current_rev}, "
                f"expected {expected_revision}"
            )
        stored = StandingRuleRecord(
            shop_id=rule.shop_id,
            kind=rule.kind,
            category=rule.category,
            answer=rule.answer,
            learned_cycle=rule.learned_cycle,
            source_question_id=rule.source_question_id,
            active=rule.active,
            revision=current_rev + 1,
            review_after=rule.review_after,
        )
        self._rules[stored.rule_id] = stored
        self._events.append({
            "rule_id": stored.rule_id,
            "shop_id": stored.shop_id,
            "kind": stored.kind.value,
            "category": stored.category,
            "answer": stored.answer,
            "revision": stored.revision,
            "source_question_id": stored.source_question_id,
            "at": _now(),
        })
        return stored

    def history(self, shop_id: str, rule_key: str) -> list[dict]:
        return [e for e in self._events
                if e["shop_id"] == shop_id and e["rule_id"] == rule_key]


class FileRuleStore:
    """JSON file. Survives process restart on the same disk; not multi-instance."""

    backend_name = "file"

    def __init__(
        self,
        path,
        seed: list[StandingRule] | None = None,
        shop_id: str = "richmond-general",
    ):
        self.path = Path(path)
        self._shop_id = shop_id
        # Writable local disk is durable. Cloud Run's container FS is not.
        self.durable = not bool(os.environ.get("K_SERVICE"))
        if self.path.is_file():
            raw = json.loads(self.path.read_text())
            self._rules = {
                k: StandingRuleRecord.from_dict(v)
                for k, v in (raw.get("rules") or {}).items()
            }
            self._events = list(raw.get("events") or [])
        else:
            self._rules = _seed_records(seed, shop_id)
            self._events = []
            if self._rules:
                self._flush()

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "rules": {k: v.as_dict() for k, v in self._rules.items()},
            "events": self._events,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        tmp.replace(self.path)

    def active_rules(self, shop_id: str) -> list[StandingRule]:
        return [
            r.to_standing_rule()
            for r in self._rules.values()
            if r.shop_id == shop_id and r.active
        ]

    def put(
        self, rule: StandingRuleRecord, expected_revision: int | None = None,
    ) -> StandingRuleRecord:
        existing = self._rules.get(rule.rule_id)
        current_rev = existing.revision if existing else 0
        if expected_revision is not None and expected_revision != current_rev:
            raise MemoryConflict(
                f"rule {rule.rule_id[:8]} at revision {current_rev}, "
                f"expected {expected_revision}"
            )
        stored = StandingRuleRecord(
            shop_id=rule.shop_id,
            kind=rule.kind,
            category=rule.category,
            answer=rule.answer,
            learned_cycle=rule.learned_cycle,
            source_question_id=rule.source_question_id,
            active=rule.active,
            revision=current_rev + 1,
            review_after=rule.review_after,
        )
        self._rules[stored.rule_id] = stored
        self._events.append({
            "rule_id": stored.rule_id,
            "shop_id": stored.shop_id,
            "kind": stored.kind.value,
            "category": stored.category,
            "answer": stored.answer,
            "revision": stored.revision,
            "source_question_id": stored.source_question_id,
            "at": _now(),
        })
        self._flush()
        return stored

    def history(self, shop_id: str, rule_key: str) -> list[dict]:
        return [e for e in self._events
                if e["shop_id"] == shop_id and e["rule_id"] == rule_key]


def seed_rules() -> list[StandingRule]:
    """The five house conventions the Aug 22 cycle already knew."""
    return [
        StandingRule(
            kind=QuestionKind.APPETITE,
            category="dinnerware / pottery",
            answer="SKIP — store has zero room for dishes or box sets",
            learned_cycle="2026-08-22",
        ),
        StandingRule(
            kind=QuestionKind.POLICY,
            category="sports memorabilia",
            answer="SKIP raw uncertified autographs — store currently overstocked",
            learned_cycle="2026-08-22",
        ),
        StandingRule(
            kind=QuestionKind.APPETITE,
            category="vintage tools",
            answer="SKIP — store backlog of unlisted tools",
            learned_cycle="2026-08-22",
        ),
        StandingRule(
            kind=QuestionKind.APPETITE,
            category="jewelry",
            answer="BUY — bulk estate costume jewelry moves in the storefront",
            learned_cycle="2026-08-20",
        ),
        StandingRule(
            kind=QuestionKind.APPETITE,
            category="vintage cards",
            answer="BUY — including junk-wax bulk boxes",
            learned_cycle="2026-08-20",
        ),
    ]


def open_rule_store() -> RuleStore:
    """Pick a backend. Tests get memory. Cloud Run prefers Firestore."""
    import sys
    shop = os.environ.get("BTF_SHOP_ID", "richmond-general")
    seed = seed_rules()
    backend = (os.environ.get("BTF_MEMORY_BACKEND") or "").strip().lower()
    testing = "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST")
    if testing and backend not in {"file", "firestore"}:
        return InMemoryRuleStore(seed=seed, shop_id=shop)
    if backend == "memory":
        return InMemoryRuleStore(seed=seed, shop_id=shop)
    if backend == "firestore" or (
        backend == "" and os.environ.get("K_SERVICE")
    ):
        try:
            from src.memory.firestore import FirestoreRuleStore
            return FirestoreRuleStore(shop_id=shop, seed=seed)
        except Exception as e:
            print(f"[!] Firestore memory unavailable ({e}); file store")
    path = Path(os.environ.get(
        "BTF_MEMORY_PATH", "data/memory/rules.json",
    ))
    return FileRuleStore(path, seed=seed, shop_id=shop)
