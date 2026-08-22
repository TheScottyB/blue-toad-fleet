"""Stable IDs for questions and standing rules. Pure functions, no I/O."""

from __future__ import annotations

import hashlib

QUESTION_SCHEMA = "q1"


def normalize_category(category: str) -> str:
    return " ".join((category or "").casefold().split())


def make_rule_id(shop_id: str, kind: str, category: str) -> str:
    key = f"{shop_id}|{kind}|{normalize_category(category)}"
    return hashlib.sha256(key.encode()).hexdigest()


def make_ruling_id(
    shop_id: str,
    cycle_id: str,
    kind: str,
    lot_ids: tuple[str, ...] | list[str],
    cluster_id: str | None = None,
) -> str:
    """Stable identity for a ruling that must never generalise by category."""
    scope = cluster_id or ",".join(sorted(str(lot_id) for lot_id in lot_ids))
    key = f"{shop_id}|{cycle_id}|{kind}|{scope}"
    return hashlib.sha256(key.encode()).hexdigest()


def make_question_id(cycle_id: str, question) -> str:
    lots = ",".join(sorted(question.lot_ids))
    cluster = question.cluster_id or ""
    raw = (
        f"{cycle_id}|{question.kind.value}|{normalize_category(question.category)}"
        f"|{cluster}|{lots}|{QUESTION_SCHEMA}"
    )
    return "q_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
