"""
Blue Toad bid math — pure, dependency-free, testable.

Implements Richmond General's documented sourcing rule:
  * max bid  ~= 35-40% of the low-mid resale estimate, adjusted by a
    per-category calibration multiplier
  * all-in   = max_bid * (1 + absentee_fee) * (1 + tax_rate)
  * priority = A / B / C by fit score and comp confidence
  * allocation = greedy against a hard budget cap, priority then value density
  * auto-send = lots at or below a configured all-in threshold need no human

Every number here comes from the business's own process. Nothing is inferred
by a model. The model's job upstream is identification and estimation; this
module turns an estimate into a decision, deterministically, so the decision
is auditable and unit-testable.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable

# Blue Toad absentee terms.
ABSENTEE_FEE = 0.15

# Walworth County, WI: 5.0% state + 0.5% county. Richmond General has a resale
# exemption on file with Blue Toad, so its purchases are not taxed. The nominal
# rate is kept beside the default so the exemption is visible rather than
# implied by a bare zero — and so a buyer without one can pass it explicitly.
WI_SALES_TAX_RATE = 0.055
DEFAULT_TAX_RATE = 0.0

# Documented base rule: 35-40% of low-mid resale. We take the midpoint of that
# band as the base and let calibration move it per category.
BASE_BID_FRACTION_LOW = 0.35
BASE_BID_FRACTION_HIGH = 0.40


class Confidence(str, Enum):
    NONE = "none"      # no external comp found
    LOW = "low"        # single source
    MEDIUM = "medium"  # two sources
    HIGH = "high"      # three or more, tight spread


class Priority(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    SKIP = "SKIP"


@dataclass(frozen=True)
class CompEstimate:
    """What the Comps agent produced for one lot. Advisory by design."""
    low: float | None
    high: float | None
    source_count: int
    confidence: Confidence

    @property
    def has_external_comp(self) -> bool:
        return self.source_count > 0 and self.low is not None and self.high is not None

    @property
    def low_mid(self) -> float | None:
        """Low-mid of the resale range: the midpoint of low and the low-high mean."""
        if not self.has_external_comp:
            return None
        return (self.low + (self.low + self.high) / 2) / 2


@dataclass(frozen=True)
class Lot:
    lot_id: str
    caption: str
    category: str
    fit_score: float          # 0..1, from the Appraiser
    condition_penalty: float  # 0..1, fraction knocked off for condition
    comp: CompEstimate


@dataclass(frozen=True)
class Decision:
    lot_id: str
    category: str
    priority: Priority
    max_bid: float | None
    all_in: float | None
    bid_fraction: float | None
    reason: str
    needs_human_pricing: bool
    auto_send: bool = False
    allocated: bool = False


def bid_fraction_for(category: str, calibration: dict[str, float] | None = None) -> float:
    """
    Calibration multiplier per category, learned from prior cycles
    (estimate vs actual hammer). Absent data, use the midpoint of the
    documented 35-40% band.
    """
    base = (BASE_BID_FRACTION_LOW + BASE_BID_FRACTION_HIGH) / 2
    if not calibration:
        return base
    return max(0.05, min(0.90, calibration.get(category, base)))


def all_in_cost(max_bid: float, tax_rate: float = DEFAULT_TAX_RATE) -> float:
    """Hammer plus the 15% absentee fee plus tax. Rounded to cents."""
    return round(max_bid * (1 + ABSENTEE_FEE) * (1 + tax_rate), 2)


def _priority_for(lot: Lot) -> Priority:
    if lot.fit_score < 0.35:
        return Priority.SKIP
    if lot.fit_score >= 0.75 and lot.comp.confidence in (Confidence.HIGH, Confidence.MEDIUM):
        return Priority.A
    if lot.fit_score >= 0.55:
        return Priority.B
    return Priority.C


def price_lot(
    lot: Lot,
    calibration: dict[str, float] | None = None,
    tax_rate: float = DEFAULT_TAX_RATE,
) -> Decision:
    """
    Turn one appraised lot into a bid decision.

    A lot with no external comp is NOT priced. It is surfaced for human
    pricing with its reason stated. Refusing to guess is a feature: the
    bid sheet's job is to inform a person who knows the market.
    """
    priority = _priority_for(lot)

    if priority is Priority.SKIP:
        return Decision(
            lot_id=lot.lot_id, category=lot.category, priority=Priority.SKIP,
            max_bid=None, all_in=None, bid_fraction=None,
            reason=f"fit {lot.fit_score:.2f} below threshold",
            needs_human_pricing=False,
        )

    if not lot.comp.has_external_comp:
        return Decision(
            lot_id=lot.lot_id, category=lot.category, priority=priority,
            max_bid=None, all_in=None, bid_fraction=None,
            reason="no external comp — human pricing required",
            needs_human_pricing=True,
        )

    fraction = bid_fraction_for(lot.category, calibration)
    base = lot.comp.low_mid * fraction
    # Clamp before it touches money. The field is documented 0..1 but nothing
    # enforced it, and `1 - penalty` turns a NEGATIVE penalty into a bid
    # INCREASE — a model slip of -0.5 raised a $41.25 max to $61.88. Values >1
    # would go negative. Neither is a bid we would ever intend to place.
    penalty = min(max(lot.condition_penalty, 0.0), 1.0)
    max_bid = round(base * (1 - penalty), 2)

    if max_bid < 1:
        return Decision(
            lot_id=lot.lot_id, category=lot.category, priority=Priority.SKIP,
            max_bid=None, all_in=None, bid_fraction=fraction,
            reason="computed max below $1 — not worth an absentee slot",
            needs_human_pricing=False,
        )

    return Decision(
        lot_id=lot.lot_id, category=lot.category, priority=priority,
        max_bid=max_bid, all_in=all_in_cost(max_bid, tax_rate),
        bid_fraction=fraction,
        reason=(
            f"low-mid ${lot.comp.low_mid:.0f} x {fraction:.0%} "
            f"less {penalty:.0%} condition, "
            f"{lot.comp.source_count} source(s), {lot.comp.confidence.value} confidence"
        ),
        needs_human_pricing=False,
    )


_PRIORITY_RANK = {Priority.A: 0, Priority.B: 1, Priority.C: 2, Priority.SKIP: 3}


def allocate(
    decisions: Iterable[Decision],
    budget_cap: float,
    auto_send_threshold: float = 0.0,
) -> list[Decision]:
    """
    Greedy allocation against a hard all-in budget cap: priority first,
    then cheapest (most lots for the money) within a priority band.

    auto_send_threshold: allocated lots whose all-in is at or below this
    value are marked auto_send. The rest wait for a human. A threshold of
    0 means every bid needs approval, which is the safe default and what
    production should start at.
    """
    priced = [d for d in decisions if d.max_bid is not None]
    unpriced = [d for d in decisions if d.max_bid is None]

    priced.sort(key=lambda d: (_PRIORITY_RANK[d.priority], d.all_in))

    spent = 0.0
    out: list[Decision] = []
    for d in priced:
        if spent + d.all_in <= budget_cap:
            spent = round(spent + d.all_in, 2)
            out.append(replace(
                d,
                allocated=True,
                auto_send=(auto_send_threshold > 0 and d.all_in <= auto_send_threshold),
            ))
        else:
            out.append(replace(d, allocated=False, auto_send=False,
                               reason=d.reason + " — over budget cap"))
    return out + unpriced


@dataclass
class SheetSummary:
    total_lots: int = 0
    allocated: int = 0
    auto_send: int = 0
    needs_approval: int = 0
    needs_human_pricing: int = 0
    skipped: int = 0
    committed_max: float = 0.0
    committed_all_in: float = 0.0
    by_priority: dict[str, int] = field(default_factory=dict)


def summarize(decisions: Iterable[Decision]) -> SheetSummary:
    s = SheetSummary()
    for d in decisions:
        s.total_lots += 1
        s.by_priority[d.priority.value] = s.by_priority.get(d.priority.value, 0) + 1
        if d.needs_human_pricing:
            s.needs_human_pricing += 1
        elif d.priority is Priority.SKIP:
            s.skipped += 1
        if d.allocated:
            s.allocated += 1
            s.committed_max = round(s.committed_max + d.max_bid, 2)
            s.committed_all_in = round(s.committed_all_in + d.all_in, 2)
            if d.auto_send:
                s.auto_send += 1
            else:
                s.needs_approval += 1
    return s
