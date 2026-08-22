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

import re
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


# Caption detector only. It does not elect k and does not distinguish CHOICE
# from TIMES_THE_MONEY — mechanic_from_ruling is what settles those. When this
# is True and nobody has ruled, the standing absentee default is CHOICE with
# units_wanted=1 (take one; remainder goes back to the floor).
_CAPTION_PER_UNIT_RE = re.compile(
    r"buyer's choice|buyers choice|times the money|\bttm\b|\bchoice of\b",
    re.IGNORECASE,
)


def is_choice_lot(*texts: str) -> bool:
    blob = " ".join(t for t in texts if t)
    return bool(_CAPTION_PER_UNIT_RE.search(blob))


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
    def needs_deep_comps(self) -> bool:
        """Pricing research is unfinished; this is not a skip decision."""
        return self.needs_human_pricing and not self.needs_mechanic_ruling

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


def opening_bid(max_bid: float) -> float:
    """What the clerk opens at, on the house's grid, never above the ceiling.

    A fraction of the max, floored at one bidding increment so an opening bid is
    always callable. Lived open-coded as `max(5.0, bid * 0.35)` in the pipeline
    twice and the single-photo runner once — three copies of the increment and
    the bid fraction, each free to drift from the constants that document them.
    """
    return snap_to_increment(max(BID_INCREMENT, max_bid * BASE_BID_FRACTION_LOW))


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

    # An unestablished mechanic is not a pricing problem, it is an unanswered
    # question about how the house sells the lot — and the answer multiplies the
    # money. Refuse until somebody rules.
    #
    # This deliberately does NOT require unit_count > 1. The parser cannot
    # establish a count from an unreadable ruling, so it handed back 1 meaning
    # "nobody counted", and this gate read that as "there is exactly one
    # object" — making the refusal dead code on both production paths. Every
    # unreadable ruling became a clean, allocated, auto-sendable bid.
    #
    # UNKNOWN and "but it is definitely one unit" cannot both be true: if you
    # know there is one object, the mechanic does not matter and the lot is
    # STRAIGHT. So there is nothing left for this branch to let through.
    if lot.mechanic is BidMechanic.UNKNOWN:
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
            reason="pending deep comps — verified sold-price evidence is still needed",
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
    priced = [d for d in decisions if d.max_bid is not None and not d.speculative]
    contingent = [d for d in decisions if d.max_bid is not None and d.speculative]
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
    # A contingent remainder does not exist unless the primary lot comes back
    # up. Keep it visible and human-approved without consuming the committed
    # envelope as though both instructions were unconditional firm bids.
    out.extend(replace(d, allocated=True, auto_send=False) for d in contingent)
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
    contingent: int = 0
    contingent_max: float = 0.0
    contingent_all_in: float = 0.0
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
            if d.speculative:
                s.contingent += 1
                s.contingent_max = round(
                    s.contingent_max + (d.committed_max or 0.0), 2)
                s.contingent_all_in = round(
                    s.contingent_all_in + (d.committed_all_in or 0.0), 2)
                continue
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


# --------------------------------------------------------------------------
# Reading a ruling into a commitment.
#
# The appraiser asks the right question — "is this one lot or all of them?" —
# and a human or the auctioneer answers it in words. Nothing carried that answer
# to the fields that decide what gets spent, so the operator typed it into the
# absentee email by hand instead. This is the wire.
#
# It parses free text into money, so it is built to refuse. Anything it cannot
# read confidently becomes UNKNOWN, which budgets every unit and asks for a
# ruling. The tempting default, STRAIGHT, silently books one unit of a lot that
# may charge five, and does it without erroring.
# --------------------------------------------------------------------------

MAX_PLAUSIBLE_UNITS = 60
"""Above this a parsed count is a misread, not an auction lot. Blue Toad sells
shelves and tray runs, not hundreds of identical units."""

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

_TTM_RE = re.compile(r"times[\s-]+the[\s-]+money|times[\s-]+money", re.I)
# A multiplier must be attached to auction vocabulary, never to a dollar figure
# or a dimension. "MAX $25 x 3 TRAYS" — the operator's own bid format — parsed as
# 25 units, priced them at $5.00 each, and wrote ">> I am taking ALL 50 <<" into
# an outgoing draft with every refusal flag reading clean. "8 x 10 frames" read
# as 8 units; "3 xylophones" as 3. A currency lookbehind alone does not fix it:
# `$30 x 2` still yields 30, because \b matches after a dollar sign.
_UNIT_WORD = r"(?:units?|trays?|lots?|shel(?:f|ves)|pieces?|items?|boxes|bins?|money|times?|bids?)"
_MULT_RE = re.compile(
    rf"(?:^|[^a-z0-9$.])(?:x|×)\s*(\d{{1,3}})(?=\s*(?:{_UNIT_WORD}\b|$|[^\w$]))"
    rf"|(?<![\d.$])\b(\d{{1,3}})\s*(?:x|×)\s*(?=(?:the\s+)?{_UNIT_WORD}\b)",
    re.I)
_CHOICE_RE = re.compile(r"(?:buyer'?s?|winner'?s?|bidder'?s?)[\s-]+choice|\bchoice\s+of\b", re.I)
_CHOICE_COUNT_RE = re.compile(
    r"(?:buyer'?s?|winner'?s?|bidder'?s?)[\s-]+choice\s+of\s+"
    r"(\d{1,3}|[a-z]+)\b",
    re.I,
)
_STRAIGHT_RE = re.compile(
    r"\bsingle\s+lot\b|\bone\s+lot\b|\ball\s+together\b|\bas\s+one\b|"
    r"\bas\s+a\s+unit\b|\bcombined\b|\bgoes\s+as\s+a\s+unit\b", re.I)
_TAKE_RE = re.compile(r"\btak(?:e|ing)\s+(?:all\s+)?(\d{1,3}|[a-z]+)\b", re.I)
_MAXQTY_RE = re.compile(r"max(?:imum)?\s+quantity\s+is\s+(\d{1,3}|[a-z]+)", re.I)
_ALL_RE = re.compile(r"\ball\s+(\d{1,3}|[a-z]+)\b", re.I)
# A ruling that names a mechanic in order to REJECT it settles nothing, and
# reading it as agreement is the worst available direction. Negation must scope
# the mechanic phrase itself: "do NOT limit me to one unit" affirms taking all
# units and must not be rejected merely because the sentence contains "not".
_MECHANIC_PHRASE = (
    r"(?:an?\s+)?(?:x\s*\d{1,3}(?:\s+bid)?|times[\s-]+(?:the[\s-]+)?money|"
    r"(?:buyer'?s?|winner'?s?|bidder'?s?)[\s-]+choice|choice\s+of|"
    r"single\s+lot|one\s+lot|all\s+together|as\s+one)"
)
_NEGATED_MECHANIC_RE = re.compile(
    rf"^\s*no\s*,?\s+(?:that\s+is\s+)?(?:sold\s+)?(?:as\s+)?{_MECHANIC_PHRASE}"
    rf"|\b(?:not|isn'?t|aren'?t|won'?t|no\s+longer|never)\s+"
    rf"(?:sold\s+)?(?:as\s+)?{_MECHANIC_PHRASE}"
    rf"|{_MECHANIC_PHRASE}\s+(?:is|are|was|were)\s+not\b",
    re.I,
)
_OF_THEM_RE = re.compile(r"\b(\d{1,3}|[a-z]+)\s+of\s+(?:them|these|those)\b", re.I)


def _as_count(token) -> int | None:
    if token is None:
        return None
    t = str(token).strip().lower()
    if t.isdigit():
        n = int(t)
    elif t in _WORD_NUMBERS:
        n = _WORD_NUMBERS[t]
    else:
        return None
    return n if 1 <= n <= MAX_PLAUSIBLE_UNITS else None


def mechanic_from_ruling(
    answer: str | None,
    units_available: int | None = None,
) -> tuple["BidMechanic", int, int | None]:
    """
    (mechanic, unit_count, units_wanted) from an auctioneer's or operator's words.

    `units_available` is what the photograph showed, used when the words name a
    mechanic but no count. Returns UNKNOWN whenever the text does not settle it,
    including when it names two mechanics at once — "is it buyer's choice or a
    single lot?" is the question being restated, not answered, and letting word
    order break that tie decides money on a coin flip.
    """
    text = (answer or "").strip()
    fallback_n = units_available if units_available and units_available > 0 else 1
    unknown = (BidMechanic.UNKNOWN, fallback_n, None)
    if not text:
        return unknown

    if _NEGATED_MECHANIC_RE.search(text):
        return unknown

    # Collect EVERY multiplier, not the first. Taking the first meant
    # "trays 12 x 14 x 16 go as a x3 bid" read 14 units and silently discarded
    # the x3 that was the actual ruling. Two multipliers that disagree is the
    # same shape as two mechanics named at once — the sentence has not settled
    # the count, and letting position break the tie decides money on word order.
    found = []
    for m in _MULT_RE.finditer(text):
        n = _as_count(m.group(1) or m.group(2))
        if n is None:                          # x0, x900 — a misread, not a lot
            return unknown
        found.append(n)
    if len(set(found)) > 1:
        return unknown
    mult = found[0] if found else None

    says_ttm = bool(_TTM_RE.search(text)) or mult is not None
    says_choice = bool(_CHOICE_RE.search(text))
    says_straight = bool(_STRAIGHT_RE.search(text))

    # CHOICE and TIMES_THE_MONEY are the same family — both price per unit, and
    # they differ only in who picks the quantity. Naming both, as the operator
    # does in "any OTHER 'Buyer's Choice / Times the Money' shelf lot", is a
    # category label, not an ambiguity, and the actionable part is the quantity
    # that follows it.
    #
    # The genuine conflict is per-unit against STRAIGHT: "is it buyer's choice
    # or sold as a single lot?" is the question restated, and letting word order
    # break that tie decides money on a coin flip.
    if says_straight and (says_ttm or says_choice):
        return unknown

    wanted = None
    for pattern in (_MAXQTY_RE, _TAKE_RE):
        w = pattern.search(text)
        if w:
            wanted = _as_count(w.group(1))
            if wanted is None:
                return unknown
            break

    if says_straight:
        return (BidMechanic.STRAIGHT, 1, 1)

    if says_ttm and says_choice and mult is None:
        says_ttm = False        # no multiplier stated: read it as the elective form

    if says_ttm:
        n = mult
        if n is None:
            for pat in (_ALL_RE, _OF_THEM_RE):
                hit = pat.search(text)
                if hit:
                    n = _as_count(hit.group(1))
                    if n is None:
                        return unknown
                    break
        if n is None:
            n = units_available if units_available and units_available > 1 else None
        if n is None:
            # A per-unit charge over an unknown number of units is unpriceable.
            return unknown
        if wanted is None and _ALL_RE.search(text):
            wanted = n
        return (BidMechanic.TIMES_THE_MONEY, n, min(wanted, n) if wanted else None)

    if says_choice:
        n = units_available if units_available and units_available > 0 else mult
        if n is None and (choice_count := _CHOICE_COUNT_RE.search(text)):
            n = _as_count(choice_count.group(1))
            if n is None:
                return unknown
        if n is None:
            for pat in (_ALL_RE, _OF_THEM_RE):
                hit = pat.search(text)
                if hit and (n := _as_count(hit.group(1))) is not None:
                    break
        if n is None:
            # Never fabricate 1. price_lot only divides the group comp down to
            # one unit when unit_count > 1, so an invented 1 makes the WHOLE
            # group's value the ceiling for a single unit — five times the
            # per-unit ceiling, in the overbid direction, on a lot nobody
            # counted. Both production callers pass no count, so this was the
            # live path.
            return unknown
        return (BidMechanic.CHOICE, n, min(wanted, n) if wanted else None)

    return unknown
