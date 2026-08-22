"""Bounded, source-backed facts for curator challenge prose.

Selection is deterministic.  A language model may phrase a selected challenge,
but it cannot choose the rule, lot, evidence, or action and it cannot expand the
set of figures that the operator sees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping


_LOT_ID = re.compile(r"^BT-\d{3,}$")
_LOT_IN_TEXT = re.compile(r"\bBT-\d{3,}\b", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:,\d{3})*(?:\.\d+)?")
_UNSUPPORTED_ACTION = re.compile(r"\b(?:buy|bid|purchase|acquire)\b", re.IGNORECASE)
_MARGIN = re.compile(r"\b(?:margin|roi|return multiple)\b", re.IGNORECASE)
_VELOCITY = re.compile(r"\b(?:velocity|absorption)\b", re.IGNORECASE)


def _numbers(text: str) -> set[float]:
    return {round(float(raw.replace(",", "")), 4) for raw in _NUMBER.findall(text)}


@dataclass(frozen=True)
class ChallengeEvidence:
    """One current evidence revision that may support a challenge."""

    revision: str
    citations: tuple[str, ...]
    source_sha256: tuple[str, ...]
    cycle_id: str
    manifest_sha256: str
    comp_low: float | None = None
    comp_high: float | None = None
    absorption: float | None = None

    def __post_init__(self) -> None:
        if not all((self.revision, self.cycle_id, self.manifest_sha256)):
            raise ValueError("challenge evidence is missing its revision identity")
        if not self.citations or not self.source_sha256:
            raise ValueError("challenge evidence requires citations and source hashes")
        has_comp = self.comp_low is not None or self.comp_high is not None
        if has_comp and not (
            self.comp_low is not None
            and self.comp_high is not None
            and 0 < self.comp_low <= self.comp_high
        ):
            raise ValueError("challenge comp evidence must be a positive low/high pair")
        if self.absorption is not None and self.absorption <= 0:
            raise ValueError("challenge absorption must be positive")
        if not has_comp and self.absorption is None:
            raise ValueError("challenge evidence has neither a comp nor absorption")


@dataclass(frozen=True)
class ChallengeFacts:
    """The complete and only vocabulary allowed in curator pushback."""

    rule_id: str
    skip_rule: str
    category: str
    lot_id: str
    caption: str
    current_decision: str
    max_bid: float
    evidence: ChallengeEvidence
    selection_reason: str
    action: str = "REVIEW_CONFLICT"

    def __post_init__(self) -> None:
        if not _LOT_ID.fullmatch(self.lot_id):
            raise ValueError("challenge lot id is invalid")
        if "skip" not in self.skip_rule.lower():
            raise ValueError("challenge rule must be an exact SKIP rule")
        if self.current_decision != "ALLOCATED" or self.max_bid <= 0:
            raise ValueError("challenge requires a conflicting allocated decision")
        if self.action != "REVIEW_CONFLICT":
            raise ValueError("curator challenges cannot authorize buying")
        if not all((self.rule_id, self.category, self.caption, self.selection_reason)):
            raise ValueError("challenge facts are incomplete")

    @property
    def allowed_amounts(self) -> set[float]:
        values = {self.max_bid}
        if self.evidence.comp_low is not None:
            values.add(self.evidence.comp_low)
        if self.evidence.comp_high is not None:
            values.add(self.evidence.comp_high)
        return {round(value, 2) for value in values}

    def as_prompt_dict(self) -> dict:
        evidence = {
            "revision": self.evidence.revision,
            "citations": list(self.evidence.citations),
            "comp_low": self.evidence.comp_low,
            "comp_high": self.evidence.comp_high,
            "absorption": self.evidence.absorption,
        }
        return {
            "rule_id": self.rule_id,
            "skip_rule": self.skip_rule,
            "category": self.category,
            "lot_id": self.lot_id,
            "caption": self.caption,
            "current_decision": self.current_decision,
            "max_bid": self.max_bid,
            "evidence": evidence,
            "selection_reason": self.selection_reason,
            "action": self.action,
        }

    def deterministic_text(self) -> str:
        return (
            f"Review the conflict: {self.skip_rule}; {self.lot_id} "
            f"({self.caption}) is currently allocated at ${self.max_bid:,.2f}. "
            f"Evidence revision {self.evidence.revision} is attached."
        )


def select_challenge(
    decisions: Iterable,
    captions: Mapping[str, str],
    standing_rules: Iterable,
    evidence_by_lot: Mapping[str, ChallengeEvidence],
    *,
    cycle_id: str,
    manifest_sha256: str,
) -> ChallengeFacts | None:
    """Return the first exact, current rule/decision conflict in stable order."""
    rules = sorted(
        (
            rule for rule in standing_rules
            if "skip" in str(getattr(rule, "answer", "")).lower()
        ),
        key=lambda rule: (
            str(getattr(rule, "category", "")),
            str(getattr(rule, "kind", "")),
            str(getattr(rule, "answer", "")),
        ),
    )
    allocated = sorted(
        (decision for decision in decisions if decision.allocated and decision.max_bid),
        key=lambda decision: decision.lot_id,
    )
    for rule in rules:
        for decision in allocated:
            if decision.category.casefold() != str(rule.category).casefold():
                continue
            evidence = evidence_by_lot.get(decision.lot_id)
            if evidence is None:
                continue
            if (
                evidence.cycle_id != cycle_id
                or evidence.manifest_sha256 != manifest_sha256
            ):
                continue
            rule_kind = getattr(getattr(rule, "kind", ""), "value", getattr(rule, "kind", ""))
            return ChallengeFacts(
                rule_id=f"{rule_kind}:{rule.category}",
                skip_rule=str(rule.answer),
                category=str(rule.category),
                lot_id=decision.lot_id,
                caption=captions.get(decision.lot_id) or decision.category,
                current_decision="ALLOCATED",
                max_bid=float(decision.max_bid),
                evidence=evidence,
                selection_reason="allocated lot conflicts with an exact standing SKIP rule",
            )
    return None


def challenge_text_is_trusted(text: str | None, facts: ChallengeFacts) -> bool:
    """Reject prose that exceeds the challenge's exact facts or authority."""
    if not text or facts.lot_id not in text:
        return False
    lot_ids = {lot_id.upper() for lot_id in _LOT_IN_TEXT.findall(text)}
    if lot_ids - {facts.lot_id.upper()}:
        return False
    if _UNSUPPORTED_ACTION.search(text) or _MARGIN.search(text):
        return False
    if _VELOCITY.search(text) and facts.evidence.absorption is None:
        return False

    supplied = str(facts.as_prompt_dict())
    allowed_numbers = _numbers(supplied)
    return not (_numbers(text) - allowed_numbers)
