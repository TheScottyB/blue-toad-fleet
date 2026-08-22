"""Firestore adapter. Imported only when BTF_MEMORY_BACKEND=firestore."""

from __future__ import annotations

import os

from src.appraisal import LotRuling, StandingRule
from src.memory.store import (
    LotRulingRecord, MemoryConflict, StandingRuleRecord, _seed_records,
)


class FirestoreRuleStore:
    backend_name = "firestore"
    durable = True

    def __init__(self, shop_id: str = "richmond-general", seed=None):
        from google.cloud import firestore as fs
        self._shop_id = shop_id
        database = os.environ.get("BTF_FIRESTORE_DATABASE", "blue-toad")
        self._db = fs.Client(database=database)
        self._rules = self._db.collection("shops").document(shop_id).collection("rules")
        self._events = (
            self._db.collection("shops").document(shop_id).collection("rule_events")
        )
        self._rulings = (
            self._db.collection("shops").document(shop_id).collection("lot_rulings")
        )
        self._ruling_events = (
            self._db.collection("shops").document(shop_id).collection("ruling_events")
        )
        if seed and not list(self._rules.limit(1).stream()):
            for rec in _seed_records(seed, shop_id).values():
                self.put(rec)

    def active_rules(self, shop_id: str) -> list[StandingRule]:
        if shop_id != self._shop_id:
            return []
        out = []
        for doc in self._rules.where("active", "==", True).stream():
            out.append(StandingRuleRecord.from_dict(doc.to_dict()).to_standing_rule())
        return out

    def put(
        self, rule: StandingRuleRecord, expected_revision: int | None = None,
    ) -> StandingRuleRecord:
        from google.cloud import firestore as fs
        ref = self._rules.document(rule.rule_id)
        txn = self._db.transaction()

        @fs.transactional
        def _write(transaction):
            snap = ref.get(transaction=transaction)
            current_rev = int(snap.to_dict()["revision"]) if snap.exists else 0
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
            transaction.set(ref, stored.as_dict())
            event_ref = self._events.document()
            transaction.set(event_ref, {
                "rule_id": stored.rule_id,
                "shop_id": stored.shop_id,
                "kind": stored.kind.value,
                "category": stored.category,
                "answer": stored.answer,
                "revision": stored.revision,
                "source_question_id": stored.source_question_id,
                "actor": stored.actor,
                "at": fs.SERVER_TIMESTAMP,
            })
            return stored

        return _write(txn)

    def history(self, shop_id: str, rule_key: str) -> list[dict]:
        if shop_id != self._shop_id:
            return []
        rows = []
        for doc in self._events.where("rule_id", "==", rule_key).stream():
            data = doc.to_dict()
            data.pop("at", None)
            rows.append(data)
        rows.sort(key=lambda e: e.get("revision", 0))
        return rows

    def active_rulings(self, shop_id: str, cycle_id: str) -> list[LotRuling]:
        if shop_id != self._shop_id:
            return []
        out = []
        query = self._rulings.where("cycle_id", "==", cycle_id).where(
            "active", "==", True)
        for doc in query.stream():
            out.append(LotRulingRecord.from_dict(doc.to_dict()).to_lot_ruling())
        return out

    def put_ruling(
        self, ruling: LotRulingRecord, expected_revision: int | None = None,
    ) -> LotRulingRecord:
        from google.cloud import firestore as fs

        ref = self._rulings.document(ruling.ruling_id)
        txn = self._db.transaction()

        @fs.transactional
        def _write(transaction):
            snap = ref.get(transaction=transaction)
            current_rev = int(snap.to_dict()["revision"]) if snap.exists else 0
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
            transaction.set(ref, stored.as_dict())
            event_ref = self._ruling_events.document()
            transaction.set(event_ref, {**stored.as_dict(), "at": fs.SERVER_TIMESTAMP})
            return stored

        return _write(txn)

    def ruling_history(self, shop_id: str, ruling_id: str) -> list[dict]:
        if shop_id != self._shop_id:
            return []
        rows = []
        for doc in self._ruling_events.where(
            "ruling_id", "==", ruling_id).stream():
            data = doc.to_dict()
            data.pop("at", None)
            rows.append(data)
        rows.sort(key=lambda event: event.get("revision", 0))
        return rows
