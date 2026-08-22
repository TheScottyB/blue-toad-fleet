"""Standing-rule persistence. Unit tests use memory and a JSON file."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from src.appraisal import LotRuling, QuestionKind, StandingRule
from src.memory.ids import make_rule_id, make_ruling_id


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
    actor: str = "operator"

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
        data = asdict(self)
        data["kind"] = self.kind.value
        data["rule_id"] = self.rule_id
        return data

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
            actor=raw.get("actor") or "operator",
        )


@dataclass
class LotRulingRecord:
    shop_id: str
    cycle_id: str
    kind: QuestionKind | str
    lot_ids: tuple[str, ...]
    answer: str
    source_question_id: str
    cluster_id: str | None = None
    active: bool = True
    revision: int = 1
    actor: str = "operator"

    def __post_init__(self):
        if isinstance(self.kind, str):
            self.kind = QuestionKind(self.kind)
        self.lot_ids = tuple(self.lot_ids)
        # Reuse the domain validation so persistence cannot create a broader
        # authority than the application understands.
        LotRuling(
            kind=self.kind,
            answer=self.answer,
            learned_cycle=self.cycle_id,
            lot_ids=self.lot_ids,
            cluster_id=self.cluster_id,
        )

    @property
    def ruling_id(self) -> str:
        return make_ruling_id(
            self.shop_id,
            self.cycle_id,
            self.kind.value,
            self.lot_ids,
            self.cluster_id,
        )

    def to_lot_ruling(self) -> LotRuling:
        return LotRuling(
            kind=self.kind,
            answer=self.answer,
            learned_cycle=self.cycle_id,
            lot_ids=self.lot_ids,
            cluster_id=self.cluster_id,
        )

    def as_dict(self) -> dict:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["lot_ids"] = list(self.lot_ids)
        data["ruling_id"] = self.ruling_id
        return data

    @classmethod
    def from_dict(cls, raw: dict) -> "LotRulingRecord":
        return cls(
            shop_id=raw["shop_id"],
            cycle_id=raw["cycle_id"],
            kind=raw["kind"],
            lot_ids=tuple(raw.get("lot_ids") or ()),
            answer=raw["answer"],
            source_question_id=raw.get("source_question_id") or "",
            cluster_id=raw.get("cluster_id"),
            active=bool(raw.get("active", True)),
            revision=int(raw.get("revision") or 1),
            actor=raw.get("actor") or "operator",
        )

class RuleStore(Protocol):
    backend_name: str
    durable: bool

    def active_rules(self, shop_id: str) -> list[StandingRule]: ...
    def put(
        self, rule: StandingRuleRecord, expected_revision: int | None = None,
    ) -> StandingRuleRecord: ...
    def history(self, shop_id: str, rule_key: str) -> list[dict]: ...
    def active_rulings(self, shop_id: str, cycle_id: str) -> list[LotRuling]: ...
    def put_ruling(
        self, ruling: LotRulingRecord, expected_revision: int | None = None,
    ) -> LotRulingRecord: ...
    def ruling_history(self, shop_id: str, ruling_id: str) -> list[dict]: ...


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
        self._rulings: dict[str, LotRulingRecord] = {}
        self._ruling_events: list[dict] = []

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
            actor=rule.actor,
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
            "actor": stored.actor,
            "at": _now(),
        })
        return stored

    def history(self, shop_id: str, rule_key: str) -> list[dict]:
        return [e for e in self._events
                if e["shop_id"] == shop_id and e["rule_id"] == rule_key]

    def active_rulings(self, shop_id: str, cycle_id: str) -> list[LotRuling]:
        return [
            record.to_lot_ruling()
            for record in self._rulings.values()
            if (record.shop_id == shop_id and record.cycle_id == cycle_id
                and record.active)
        ]

    def put_ruling(
        self, ruling: LotRulingRecord, expected_revision: int | None = None,
    ) -> LotRulingRecord:
        existing = self._rulings.get(ruling.ruling_id)
        current_rev = existing.revision if existing else 0
        if expected_revision is not None and expected_revision != current_rev:
            raise MemoryConflict(
                f"ruling {ruling.ruling_id[:8]} at revision {current_rev}, "
                f"expected {expected_revision}"
            )
        stored = LotRulingRecord(
            shop_id=ruling.shop_id,
            cycle_id=ruling.cycle_id,
            kind=ruling.kind,
            lot_ids=ruling.lot_ids,
            answer=ruling.answer,
            source_question_id=ruling.source_question_id,
            cluster_id=ruling.cluster_id,
            active=ruling.active,
            revision=current_rev + 1,
            actor=ruling.actor,
        )
        self._rulings[stored.ruling_id] = stored
        self._ruling_events.append({
            **stored.as_dict(),
            "at": _now(),
        })
        return stored

    def ruling_history(self, shop_id: str, ruling_id: str) -> list[dict]:
        return [
            event for event in self._ruling_events
            if event["shop_id"] == shop_id and event["ruling_id"] == ruling_id
        ]


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
            self._rulings = {
                key: LotRulingRecord.from_dict(value)
                for key, value in (raw.get("rulings") or {}).items()
            }
            self._ruling_events = list(raw.get("ruling_events") or [])
        else:
            self._rules = _seed_records(seed, shop_id)
            self._events = []
            self._rulings = {}
            self._ruling_events = []
            if self._rules:
                self._flush()

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "rules": {k: v.as_dict() for k, v in self._rules.items()},
            "events": self._events,
            "rulings": {k: v.as_dict() for k, v in self._rulings.items()},
            "ruling_events": self._ruling_events,
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
            actor=rule.actor,
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
            "actor": stored.actor,
            "at": _now(),
        })
        self._flush()
        return stored

    def history(self, shop_id: str, rule_key: str) -> list[dict]:
        return [e for e in self._events
                if e["shop_id"] == shop_id and e["rule_id"] == rule_key]

    def active_rulings(self, shop_id: str, cycle_id: str) -> list[LotRuling]:
        return [
            record.to_lot_ruling()
            for record in self._rulings.values()
            if (record.shop_id == shop_id and record.cycle_id == cycle_id
                and record.active)
        ]

    def put_ruling(
        self, ruling: LotRulingRecord, expected_revision: int | None = None,
    ) -> LotRulingRecord:
        existing = self._rulings.get(ruling.ruling_id)
        current_rev = existing.revision if existing else 0
        if expected_revision is not None and expected_revision != current_rev:
            raise MemoryConflict(
                f"ruling {ruling.ruling_id[:8]} at revision {current_rev}, "
                f"expected {expected_revision}"
            )
        stored = LotRulingRecord(
            shop_id=ruling.shop_id,
            cycle_id=ruling.cycle_id,
            kind=ruling.kind,
            lot_ids=ruling.lot_ids,
            answer=ruling.answer,
            source_question_id=ruling.source_question_id,
            cluster_id=ruling.cluster_id,
            active=ruling.active,
            revision=current_rev + 1,
            actor=ruling.actor,
        )
        self._rulings[stored.ruling_id] = stored
        self._ruling_events.append({**stored.as_dict(), "at": _now()})
        self._flush()
        return stored

    def ruling_history(self, shop_id: str, ruling_id: str) -> list[dict]:
        return [
            event for event in self._ruling_events
            if event["shop_id"] == shop_id and event["ruling_id"] == ruling_id
        ]


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
