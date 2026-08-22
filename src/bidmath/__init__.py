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

# Blue Toad calls bids in standard $5.00 increments. A max bid is a CEILING, so
# it snaps DOWN to the highest callable bid at or below the computed number:
# snapping up would authorise spending above what the margin math allowed, and
# could breach the budget cap the allocator just checked against.
BID_INCREMENT = 5.0

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


class BidMechanic(str, Enum):
    """How many times the hammer price is charged, and for what.

    A rural auctioneer does not sell one lot as one thing. Modelling it that
    way understated a real commitment by a factor of N against a hard cap.
    """
    STRAIGHT = "straight"
    """Bid once, take the lot. One hammer, one charge."""

    CHOICE = "choice"
    """Winner's choice: bid high, then PICK one unit at that price; the rest go
    back to the floor. A five-shelf lantern unit photographed as one image is
    five lots sold this way. The bid is a ceiling you only reach if pushed, so
    walking it down to look prudent just loses the lot to the next bidder."""

    TIMES_THE_MONEY = "times_the_money"
    """The bid is PER UNIT and charged N times. Confirmed by the auctioneer on
    the labelled jewelry tray run (12/14/16) — "Yes, that is a x3 bid" — which
    moved one lot from $25 of committed money to $75 with no number on the
    sheet changing."""

    UNKNOWN = "unknown"
    """Not established. Never silently treated as STRAIGHT: see units_committed."""


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
    # ---- APPENDED WITH DEFAULTS, and they stay last ----------------------
    # Lot is constructed positionally in demo/ and scripts/, and test_gate.py
    # builds CompEstimate with four positional arguments. A field inserted
    # mid-struct binds the wrong value silently and every test still passes.
    mechanic: "BidMechanic" = BidMechanic.STRAIGHT
    unit_count: int = 1
    """Sellable UNITS available, not objects. A box of 40 books is one unit; a
    five-shelf rack sold winner's-choice-of-shelf is five."""
    units_wanted: int | None = None
    """k — how many of them the operator elects to take, 1..unit_count.

    A decision, not a property of the lot. The winner elects it standing at the
    block; an absentee bidder is not there, so it has to be written down and
    handed to the clerk. None means nobody has decided yet."""


def units_committed(mechanic: "BidMechanic", unit_count: int,
                    units_wanted: int | None = None) -> int:
    """How many times the hammer price is charged if this bid wins.

    Blue Toad prices CHOICE and TIMES_THE_MONEY per unit; what differs is who
    picks the quantity. An election caps it. Absent one, budget the whole group:
    assuming a single unit books a fifth of the exposure on a lot that could
    take the entire cap, and the cap exists to stop precisely that.

    UNKNOWN reads expensive for the same reason. Guessing STRAIGHT on a lot that
    turns out to be per-unit breaches the cap at the block where nobody can undo
    it; guessing dear only under-fills a sheet a human can still fix.
    """
    if mechanic is BidMechanic.STRAIGHT:
        return 1
    available = max(1, int(unit_count))
    if units_wanted is None:
        return available
    return max(1, min(int(units_wanted), available))


def elect(lot: "Lot", k: int) -> "Lot":
    """Record how many units the operator will take. Returns a new Lot."""
    if not 1 <= int(k) <= max(1, lot.unit_count):
        raise ValueError(
            f"{lot.lot_id}: cannot take {k} of {lot.unit_count} available. "
            f"Electing zero is declining the lot, which is done by not bidding.")
    return replace(lot, units_wanted=int(k))


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
    # ---- APPENDED WITH DEFAULTS, and they stay last (see Lot) -------------
    mechanic: "BidMechanic" = BidMechanic.STRAIGHT
    unit_count: int = 1
    units_wanted: int | None = None
    needs_mechanic_ruling: bool = False
    """The mechanic decides the money and nobody has ruled on it. Distinct from
    needs_human_pricing, which is about the comp."""
    needs_election: bool = False
    """Per-unit lot with more than one unit and no k. The price is known; how
    many to buy is not."""
    speculative: bool = False
    """This bid only exists if something else happens first — a remainder that
    materialises only when the winner declines part of the lot. Contingent money
    never auto-sends: a human should see a bid placed on an event that may not
    occur, however cheap it is."""

    @property
    def committed_all_in(self) -> float | None:
        """Total exposure if this bid wins — what the budget cap must see.

        `all_in` is one unit. The allocator summed that regardless of mechanic,
        so a x3 lot spent a third of what it claimed against the cap.
        """
        if self.all_in is None:
            return None
        return round(self.all_in * units_committed(
            self.mechanic, self.unit_count, self.units_wanted), 2)

    @property
    def committed_max(self) -> float | None:
        """Hammer total across every unit charged."""
        if self.max_bid is None:
            return None
        return round(self.max_bid * units_committed(
            self.mechanic, self.unit_count, self.units_wanted), 2)


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


def snap_to_increment(amount: float, increment: float = BID_INCREMENT) -> float:
    """Floor a bid ceiling onto the house's bidding grid."""
    return round((amount // increment) * increment, 2)


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
    carry = dict(mechanic=lot.mechanic, unit_count=lot.unit_count,
                 units_wanted=lot.units_wanted)

    if priority is Priority.SKIP:
        return Decision(
            lot_id=lot.lot_id, category=lot.category, priority=Priority.SKIP,
            max_bid=None, all_in=None, bid_fraction=None,
            reason=f"fit {lot.fit_score:.2f} below threshold",
            needs_human_pricing=False, **carry,
        )

    # An unestablished mechanic on a multi-unit lot is not a pricing problem,
    # it is an unanswered question about how the house sells it — and the
    # answer multiplies the money. Refuse until somebody rules.
    if lot.mechanic is BidMechanic.UNKNOWN and lot.unit_count > 1:
        return Decision(
            lot_id=lot.lot_id, category=lot.category, priority=priority,
            max_bid=None, all_in=None, bid_fraction=None,
            reason=(f"{lot.unit_count} units and the bid mechanic is not "
                    f"established — needs a ruling before pricing"),
            needs_human_pricing=True, needs_mechanic_ruling=True, **carry,
        )


    if not lot.comp.has_external_comp:
        return Decision(
            lot_id=lot.lot_id, category=lot.category, priority=priority,
            max_bid=None, all_in=None, bid_fraction=None,
            reason="no external comp — human pricing required",
            needs_human_pricing=True, **carry,
        )

    fraction = bid_fraction_for(lot.category, calibration)

    # On a per-unit lot the hammer is called PER UNIT, but the appraiser priced
    # what it saw in the photograph — the whole group. Bidding the group's value
    # per unit overbids by roughly the unit count, which is the most expensive
    # error available here, so the comp is divided down to one unit and the
    # reason says so. Dividing can only ever bid less than the group is worth;
    # not dividing can commit several times the cap.
    per_unit = lot.comp.low_mid
    scaled = False
    if lot.mechanic is not BidMechanic.STRAIGHT and lot.unit_count > 1:
        per_unit = per_unit / lot.unit_count
        scaled = True

    base = per_unit * fraction
    # Clamp before it touches money. The field is documented 0..1 but nothing
    # enforced it, and `1 - penalty` turns a NEGATIVE penalty into a bid
    # INCREASE — a model slip of -0.5 raised a $41.25 max to $61.88. Values >1
    # would go negative. Neither is a bid we would ever intend to place.
    penalty = min(max(lot.condition_penalty, 0.0), 1.0)
    max_bid = snap_to_increment(round(base * (1 - penalty), 2))

    if max_bid < BID_INCREMENT:
        return Decision(
            lot_id=lot.lot_id, category=lot.category, priority=Priority.SKIP,
            max_bid=None, all_in=None, bid_fraction=fraction,
            reason=(
                f"computed max below one ${BID_INCREMENT:.0f} bidding increment "
                "— not worth an absentee slot"
            ),
            needs_human_pricing=False, **carry,
        )

    if lot.mechanic is BidMechanic.CHOICE and lot.unit_count > 1 \
            and lot.units_wanted is None:
        return Decision(
            lot_id=lot.lot_id, category=lot.category, priority=priority,
            max_bid=max_bid, all_in=all_in_cost(max_bid, tax_rate),
            bid_fraction=fraction,
            reason=(f"winner's choice of {lot.unit_count} at ${max_bid:.0f} per "
                    f"unit — how many should the clerk take?"),
            needs_human_pricing=False, needs_election=True, **carry,
        )

    return Decision(
        lot_id=lot.lot_id, category=lot.category, priority=priority,
        max_bid=max_bid, all_in=all_in_cost(max_bid, tax_rate),
        bid_fraction=fraction,
        reason=(
            (f"group low-mid ${lot.comp.low_mid:.0f} / {lot.unit_count} units = "
             f"${per_unit:.0f} per unit" if scaled
             else f"low-mid ${lot.comp.low_mid:.0f}")
            + f" x {fraction:.0%} less {penalty:.0%} condition, "
            f"{lot.comp.source_count} source(s), {lot.comp.confidence.value} confidence"
        ),
        needs_human_pricing=False,
        needs_election=(lot.mechanic is BidMechanic.CHOICE
                        and lot.unit_count > 1 and lot.units_wanted is None),
        **carry,
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

    # Sort and spend on COMMITTED money, not one unit's worth. A x3 lot billed
    # itself at a third of its cost, so it both jumped the value-density queue
    # ahead of straight lots and left the cap looking like it had room it did
    # not have.
    priced.sort(key=lambda d: (_PRIORITY_RANK[d.priority], d.committed_all_in))

    spent = 0.0
    out: list[Decision] = []
    for d in priced:
        if spent + d.committed_all_in <= budget_cap:
            spent = round(spent + d.committed_all_in, 2)
            out.append(replace(
                d,
                allocated=True,
                auto_send=(auto_send_threshold > 0
                           and d.committed_all_in <= auto_send_threshold
                           and not d.needs_mechanic_ruling
                           and not d.needs_election
                           and not d.speculative),
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
            s.committed_max = round(s.committed_max + d.committed_max, 2)
            s.committed_all_in = round(s.committed_all_in + d.committed_all_in, 2)
            if d.auto_send:
                s.auto_send += 1
            else:
                s.needs_approval += 1
    return s


# House minimum opening bid. Blue Toad opens the re-auctioned remainder here, or
# at roughly half the last hammer; the operator has bought a remainder at $5.
HOUSE_MINIMUM_BID = 5.0


def clerk_directive(decision: Decision) -> str:
    """One plain-English line telling the clerk what to do with this lot.

    The absentee bidder is not standing at the block, so every choice he would
    make in the room has to be made here in writing. His own July 11 drafts
    closed with exactly this kind of instruction, in exactly this register — a
    sentence to Bill, not a field in a report.

    Silence is the dangerous default: a lot nobody should bid on, described in
    a bid sheet, is an invitation to bid on it. So the refusals say so out loud.
    """
    lid = decision.lot_id
    if decision.needs_mechanic_ruling:
        return (f"{lid} — DO NOT BID. How this lot is sold has not been "
                f"established, and the answer multiplies the money.")
    if decision.max_bid is None:
        return f"{lid} — DO NOT BID. {decision.reason}."
    if decision.needs_election:
        return (f"{lid} — HOLD. Buyer's choice of {decision.unit_count} at "
                f"${decision.max_bid:,.2f} per unit; nobody has said how many "
                f"to take.")

    if decision.speculative:
        # Contingent money reads exactly like committed money unless it says so,
        # and a clerk holding an unmarked contingent line will simply bid it.
        return (f"{lid} — ONLY IF IT COMES BACK UP: {decision.unit_count} unit(s) "
                f"at ${decision.max_bid:,.2f} each, ${decision.committed_all_in:,.2f} "
                f"all-in. Skip if the lot clears whole.")

    if decision.mechanic is BidMechanic.TIMES_THE_MONEY:
        k = units_committed(decision.mechanic, decision.unit_count,
                            decision.units_wanted)
        return (f"{lid} — times the money: ${decision.max_bid:,.2f} per unit "
                f"x {k}. All-in ${decision.committed_all_in:,.2f}.")
    if decision.mechanic is BidMechanic.CHOICE:
        k = units_committed(decision.mechanic, decision.unit_count,
                            decision.units_wanted)
        return (f"{lid} — buyer's choice: bid to ${decision.max_bid:,.2f} per "
                f"unit and take {k} of the {decision.unit_count}. All-in "
                f"${decision.committed_all_in:,.2f}.")
    return (f"{lid} — one lot, one bid, ${decision.max_bid:,.2f} max. "
            f"All-in ${decision.committed_all_in:,.2f}.")


def remainder_opportunity(decision: Decision,
                          floor: float = HOUSE_MINIMUM_BID,
                          tax_rate: float = DEFAULT_TAX_RATE) -> Decision | None:
    """The second bite: what is left after an election, bid at the house minimum.

    When the winner takes fewer than all of them, Blue Toad re-auctions the
    remainder — usually opening at the minimum or half the last hammer. That is
    already-appraised inventory going cheap, and no sheet has ever looked at it.
    The operator has taken one at $5 himself.

    Returns None whenever there is nothing to want: a straight lot, an election
    that took everything, a lot that was never priced, or a floor that is not
    actually a discount. A remainder bid at or above the lot's own max is not a
    bargain, it is a bug.
    """
    if decision.max_bid is None or decision.mechanic is BidMechanic.STRAIGHT:
        return None
    taken = units_committed(decision.mechanic, decision.unit_count,
                            decision.units_wanted)
    left = decision.unit_count - taken
    if left < 1:
        return None

    bid = snap_to_increment(min(floor, decision.max_bid))
    if bid < BID_INCREMENT or bid > decision.max_bid:
        return None

    return Decision(
        lot_id=f"{decision.lot_id}-R", category=decision.category,
        priority=Priority.C,
        max_bid=bid, all_in=all_in_cost(bid, tax_rate),
        bid_fraction=None,
        reason=(f"remainder of {decision.lot_id}: {left} unit(s) unsold after "
                f"taking {taken}, re-auctioned at the ${bid:,.0f} opening"),
        needs_human_pricing=False,
        mechanic=BidMechanic.TIMES_THE_MONEY, unit_count=left, units_wanted=left,
        speculative=True,
    )
