"""
Appraisal and the intake clarification loop.

The Appraiser's job is *identification and attribution* — maker's marks,
hallmarks, patterns, form, period, condition — not valuation. That is the
thing a multimodal model is genuinely good at, and it is a checkable claim:
"Red Wing, 5 gallon, wing mark, hairline to base" can be verified. A dollar
range can only be taken on faith.

Where the appraisal is uncertain in a way a human can cheaply resolve, the
Appraiser emits a Question instead of guessing. Guessing is what turned the
last attempt into "a total mess" — one bad row in sixty costs trust in the
whole sheet, not one sixtieth of it.

The queue is ranked, grouped and hard-capped. A naive implementation emits one
question per uncertain lot, produces forty, and is the same mess relocated.

Answers are promoted to StandingRules keyed by (kind, category). Next cycle
the matching questions are never asked. That is the whole memory model, and it
is deliberately dumb: a keyed lookup, not a vector store.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable

MAX_QUESTIONS_PER_CYCLE = 12


class Confidence(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_CONF_GAP = {
    Confidence.HIGH: 0.0,
    Confidence.MEDIUM: 0.35,
    Confidence.LOW: 0.7,
    Confidence.NONE: 1.0,
}


class QuestionKind(str, Enum):
    """Roughly ordered by reach. Breadth dominates in practice; this is a tiebreak."""
    POLICY = "policy"               # uncertified risk / house rules / bidding policy
    LOT_GROUPING = "lot_grouping"   # are these N photos one lot or N lots?
    SCOPE = "scope"                 # whole shelf, or just the crock?
    MARK = "mark"                   # is there a maker's mark I can't see?
    CONDITION = "condition"         # can't see the reverse — any damage?
    APPETITE = "appetite"           # new category — do you want these surfaced?


# How much a resolved answer of this kind repairs, per affected lot.
_KIND_WEIGHT = {
    QuestionKind.POLICY: 1.00,
    QuestionKind.LOT_GROUPING: 1.00,
    QuestionKind.SCOPE: 0.90,
    QuestionKind.MARK: 0.70,
    QuestionKind.CONDITION: 0.45,
    QuestionKind.APPETITE: 0.35,
}


@dataclass(frozen=True)
class Appraisal:
    """What the Appraiser concluded about one lot. No price here, by design."""
    lot_id: str
    category: str
    identification: str
    attributes: dict[str, str] = field(default_factory=dict)
    confidence: Confidence = Confidence.MEDIUM
    est_value_hint: float = 0.0   # rough magnitude only, for ranking impact

    @property
    def confidence_gap(self) -> float:
        return _CONF_GAP[self.confidence]


# Kinds whose questions are about a specific cluster of photos, not a whole
# category. Two unrelated shelves of stoneware are two questions, not one.
_CLUSTER_SCOPED = frozenset({QuestionKind.LOT_GROUPING, QuestionKind.SCOPE})


# What a person can actually answer at a desk on Friday night, holding nothing
# but the same gallery photos the model saw.
#
# House convention and shop policy live in the owner's head: whether trays 12,
# 14 and 16 sell as one lot, whether the shop wants costume jewellery at all.
# A hallmark on a clasp or a hairline on a reverse does not — that needs the
# object in hand at Saturday's preview, which is after the cutoff.
#
# Asking those anyway is what makes a queue look like an AI reciting a
# checklist. The questions are not wrong; they are addressed to the wrong
# person at the wrong hour. They defer, and their lots ship flagged.
DESK_ANSWERABLE = frozenset({
    QuestionKind.POLICY,
    QuestionKind.LOT_GROUPING,
    QuestionKind.SCOPE,
    QuestionKind.APPETITE,
})


@dataclass(frozen=True)
class Question:
    kind: QuestionKind
    category: str
    prompt: str
    lot_ids: tuple[str, ...]
    value_at_stake: float = 0.0
    confidence_gap: float = 0.5
    wants_photo: bool = False
    cluster_id: str | None = None

    @property
    def merge_key(self) -> tuple:
        """
        How questions collapse together for asking.

        Distinct from rule_key on purpose. "Is there a mark on the base?" asked
        of nine crocks is one question about nine lots. But "are these six
        photos one lot?" asked of two different shelves is two questions —
        merging them produces a prompt naming one shelf while covering both,
        which is unanswerable, and the single answer would silently govern both.
        """
        if self.kind in _CLUSTER_SCOPED:
            return (self.kind.value, self.category,
                    self.cluster_id or (self.lot_ids[0] if self.lot_ids else ""))
        return (self.kind.value, self.category)

    @property
    def rule_key(self) -> tuple[str, str]:
        """How an answer generalises into memory. Always (kind, category)."""
        return (self.kind.value, self.category)

    @property
    def impact(self) -> float:
        """
        Rank by how much of the sheet this repairs.

        Lots affected drives it — a grouping question covering six photos is
        worth more than a condition question on one. Value at stake and the
        confidence gap scale it. A square-root damping on value keeps
        one expensive lot from monopolising the queue.
        """
        breadth = len(self.lot_ids)
        value = 1.0 + (self.value_at_stake ** 0.5) / 10.0
        return round(
            _KIND_WEIGHT[self.kind] * breadth * value * (0.25 + self.confidence_gap),
            4,
        )


@dataclass(frozen=True)
class StandingRule:
    """An answer promoted to a reusable rule. Scoped by (kind, category)."""
    kind: QuestionKind
    category: str
    answer: str
    learned_cycle: str

    @property
    def rule_key(self) -> tuple[str, str]:
        return (self.kind.value, self.category)


@dataclass
class QueueResult:
    asked: list[Question] = field(default_factory=list)
    auto_answered: list[tuple[Question, StandingRule]] = field(default_factory=list)
    dropped: list[Question] = field(default_factory=list)
    deferred: list[Question] = field(default_factory=list)

    @property
    def flagged_lot_ids(self) -> set[str]:
        """
        Lots that ship flagged low-confidence.

        Two ways to get here, and the distinction matters to the operator:
        dropped means the queue ran out of room, deferred means nobody at a
        desk could have answered it before the cutoff. Neither blocks the sheet.
        """
        out: set[str] = set()
        for q in (*self.dropped, *self.deferred):
            out.update(q.lot_ids)
        return out


def group(questions: Iterable[Question]) -> list[Question]:
    """
    Collapse questions sharing (kind, category) into one, merging the lots.

    "Is there a mark on the base?" asked of nine pieces of stoneware is one
    question about nine lots, not nine questions.
    """
    merged: dict[tuple, Question] = {}
    bases: dict[tuple, str] = {}
    for q in questions:
        key = q.merge_key
        if key not in merged:
            merged[key] = q
            bases[key] = q.prompt
            continue
        prev = merged[key]
        lots = tuple(dict.fromkeys(prev.lot_ids + q.lot_ids))
        merged[key] = replace(
            prev,
            lot_ids=lots,
            value_at_stake=prev.value_at_stake + q.value_at_stake,
            confidence_gap=max(prev.confidence_gap, q.confidence_gap),
            wants_photo=prev.wants_photo or q.wants_photo,
            prompt=(bases[key] if len(lots) == 1
                    else f"{bases[key]} ({len(lots)} lots)"),
        )
    return list(merged.values())


def build_queue(
    questions: Iterable[Question],
    standing_rules: Iterable[StandingRule] = (),
    cap: int = MAX_QUESTIONS_PER_CYCLE,
    desk_answerable: frozenset[QuestionKind] = DESK_ANSWERABLE,
) -> QueueResult:
    """
    Group, suppress anything a standing rule already answers, set aside what the
    desk cannot answer, rank the rest by impact, and hard-cap.

    Order matters. A standing rule wins first: if the owner has already ruled on
    it, the kind is beside the point. Deferral comes next, and deliberately does
    not consume the cap — otherwise a dozen hallmark questions crowd out the
    grouping question that actually decides how the sheet is built.
    """
    rules = {r.rule_key: r for r in standing_rules}
    result = QueueResult()

    for q in sorted(group(questions), key=lambda x: x.impact, reverse=True):
        rule = rules.get(q.rule_key)
        if rule is not None:
            result.auto_answered.append((q, rule))
        elif q.kind not in desk_answerable:
            result.deferred.append(q)
        elif len(result.asked) < cap:
            result.asked.append(q)
        else:
            result.dropped.append(q)

    return result


def learn(
    answered: Iterable[tuple[Question, str]],
    cycle: str,
    generalisable: frozenset[QuestionKind] = frozenset(
        {QuestionKind.LOT_GROUPING, QuestionKind.SCOPE, QuestionKind.APPETITE}
    ),
) -> list[StandingRule]:
    """
    Promote answers to standing rules.

    Only some kinds generalise. "Shelf lots mean the whole shelf" is a
    convention that holds next cycle. "Is there a mark on *this* base" is
    about one object and teaches nothing reusable — asking it again next
    cycle is correct behaviour, not a failure of memory.
    """
    return [
        StandingRule(kind=q.kind, category=q.category, answer=a, learned_cycle=cycle)
        for q, a in answered
        if q.kind in generalisable
    ]
