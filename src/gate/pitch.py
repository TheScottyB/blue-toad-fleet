"""
The curator's pitch — what to say about the sheet, and who decides it.

Two jobs, deliberately split:

`build_pitch` selects. It reads the allocated decisions and sorts them into the
three tiers the owner sees on a Friday afternoon: the alpha picks worth arguing
about, the fast smalls that go without discussion, and the categories a standing
rule has already ruled out. Pure Python, no model, same answer every time.

The writer only phrases what it is given. A model that could pick the lots could
also invent one; a model handed a finished list can only word it. And because
telling a model not to invent a figure is not the same as it not inventing one,
`invented_amounts` checks the prose against the numbers the sheet actually
computed. The guard is code, not a sentence in a prompt.
"""

import re
from dataclasses import dataclass, field

from src.gate.challenge import ChallengeFacts

ALPHA_PICKS = 3

# Money in prose: $1,250.00 / $100 / $25.50. Requires the dollar sign, so a
# margin target written "38%" or a lot id like "BT-181" is never read as a price.
_MONEY = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")


@dataclass(frozen=True)
class PitchLot:
    lot_id: str
    caption: str
    category: str
    max_bid: float
    committed_max: float = 0.0
    """What the lot actually commits. Equals max_bid on a straight lot; on a
    per-unit lot it is max_bid x units, and BOTH figures are legitimate for the
    writer to state — the per-unit price and the lot's total."""


@dataclass
class PitchFacts:
    """Everything the writer is allowed to know. Notably: no comps."""
    alpha: list[PitchLot] = field(default_factory=list)
    fast_smalls: list[PitchLot] = field(default_factory=list)
    ruled_out: list[str] = field(default_factory=list)
    committed_max: float = 0.0
    committed_all_in: float = 0.0
    challenge: ChallengeFacts | None = None

    @property
    def allowed_amounts(self) -> set[float]:
        """Every figure the writer may legitimately repeat."""
        out = {self.committed_max, self.committed_all_in}
        for l in (*self.alpha, *self.fast_smalls):
            out.add(l.max_bid)
            out.add(l.committed_max)
        if self.challenge:
            out.update(self.challenge.allowed_amounts)
        return {round(v, 2) for v in out if v}


def build_pitch(decisions, captions: dict[str, str],
                standing_rules=(), challenge: ChallengeFacts | None = None) -> PitchFacts:
    """
    Sort the allocated sheet into what the owner is actually asked to weigh in on.

    Alpha picks are the largest commitments — the ones worth his attention and
    the only ones he is likely to argue with. Fast smalls are the auto-send
    remainder: real bids, but not worth a conversation each. Ruled out names the
    categories a standing rule already closed, so the pitch does not re-open a
    decision he has made.

    Ordering breaks ties on lot id so the same sheet always pitches the same way;
    a pitch that reshuffles between runs reads as indecision.
    """
    allocated = [d for d in decisions if d.allocated and d.max_bid]
    ranked = sorted(allocated, key=lambda d: (-d.max_bid, d.lot_id))

    def as_lot(d):
        return PitchLot(lot_id=d.lot_id,
                        caption=captions.get(d.lot_id, "") or d.category,
                        category=d.category, max_bid=float(d.max_bid),
                        committed_max=float(d.committed_max or d.max_bid))

    alpha = [as_lot(d) for d in ranked[:ALPHA_PICKS]]
    alpha_ids = {l.lot_id for l in alpha}
    fast = [as_lot(d) for d in ranked if d.lot_id not in alpha_ids and d.auto_send]

    ruled_out = [f"{r.category} — {r.answer}" for r in standing_rules]

    # Sum COMMITTED money, not one unit's worth. Everything else in the lane
    # moved to committed_* — allocate budgets on it, summarize totals it,
    # clerk_directive prints it — and this call site did not. That made the
    # banner disagree with the sheet header on the same page, and did something
    # worse: these figures seed allowed_amounts, so invented_amounts flagged the
    # TRUE total as a hallucination, curator_voice discarded the honest
    # sentence, and the deterministic fallback printed the understated one. The
    # guard built to stop a model inventing numbers was enforcing the wrong one.
    committed_max = round(sum(d.committed_max or 0.0 for d in allocated), 2)
    committed_all_in = round(sum(d.committed_all_in or 0.0 for d in allocated), 2)

    return PitchFacts(alpha=alpha, fast_smalls=fast, ruled_out=ruled_out,
                      committed_max=committed_max,
                      committed_all_in=committed_all_in, challenge=challenge)


def invented_amounts(text: str, allowed: set[float]) -> list[float]:
    """
    Dollar figures in the prose that the sheet never computed.

    Returned rather than raised so the caller decides what to do with a writer
    that has started making numbers up — on the Gate console that means throwing
    the sentence away and showing the deterministic line instead.
    """
    seen = []
    for raw in _MONEY.findall(text or ""):
        value = round(float(raw.replace(",", "")), 2)
        if value not in {round(a, 2) for a in allowed}:
            seen.append(value)
    return seen


_CURATOR_SYSTEM = """You are the buyer's colleague at a heritage resale shop, \
talking to the owner on a Friday afternoon about the absentee sheet he is about \
to send.

You are given the finished sheet. The lots are already chosen and the bids are \
already set by the shop's own math — you are not deciding anything, you are \
saying what it amounts to in two or three sentences he can read at a glance.

Hard rules:
- Use ONLY the dollar figures listed under FIGURES YOU MAY USE. Do not compute, \
estimate, extrapolate or infer any other number. If a figure is not on that \
list, it does not go in the text.
- Never state what a lot is worth, what it might resell for, or what margin it \
carries. You have not been shown that and you cannot know it.
- Refer to lots by their id and caption as given.
- Sound like a colleague who knows the shop, not a brochure. No superlatives, \
no exclamation marks."""


def build_curator_prompt(facts: PitchFacts) -> str:
    """
    Everything the writer is allowed to know, and nothing else.

    Deliberately absent: comparable sales, resale bands, margin targets. The
    writer's job is to phrase a decision, and a writer that could see the
    valuation would start justifying it.
    """
    lines = ["THE SHEET, as the shop's bid math settled it.", ""]

    if facts.alpha:
        lines.append("Worth his attention:")
        for l in facts.alpha:
            lines.append(f"  {l.lot_id} — {l.caption} — bid set at ${l.max_bid:,.2f}")
    if facts.fast_smalls:
        lines.append("")
        lines.append(f"Going without discussion: {len(facts.fast_smalls)} smaller lots.")
        for l in facts.fast_smalls[:6]:
            lines.append(f"  {l.lot_id} — {l.caption} — ${l.max_bid:,.2f}")
    if facts.ruled_out:
        lines.append("")
        lines.append("Already ruled out by his own standing instructions:")
        lines.extend(f"  {r}" for r in facts.ruled_out)

    lines.append("")
    lines.append(f"Total committed: ${facts.committed_max:,.2f}, "
                 f"${facts.committed_all_in:,.2f} once the house fee is added.")
    lines.append("")
    lines.append("FIGURES YOU MAY USE (no others exist): "
                 + ", ".join(f"${a:,.2f}" for a in sorted(facts.allowed_amounts)))
    lines.append("")
    lines.append("Write two or three sentences.")
    return "\n".join(lines)


def deterministic_line(facts: PitchFacts) -> str:
    """
    What the console shows when the writer is unavailable or made a number up.

    Flat, and always true, because it is assembled from the same fields the
    prompt was built from.
    """
    if not facts.alpha and not facts.fast_smalls:
        return "Nothing allocated this cycle — no absentee bids to send."
    lead = ", ".join(f"{l.lot_id} ({l.caption})" for l in facts.alpha) or "none"
    return (f"Top picks: {lead}. "
            f"{len(facts.fast_smalls)} smaller lot(s) ship without discussion. "
            f"${facts.committed_max:,.2f} committed, "
            f"${facts.committed_all_in:,.2f} all-in.")


def curator_voice(facts: PitchFacts, writer) -> str:
    """
    Prose for the pitch banner, or the deterministic line if it cannot be trusted.

    `writer` takes the prompt and returns text — Gemma in production, a stub in
    tests. Three ways to fall back, and all of them are silent to the owner
    because a console that degrades into a plain sentence is still correct:

      - nothing allocated: there is nothing to write about, so no call is made
      - the writer raises: the model is down and the sheet still has to render
      - the writer invents a figure: it has put a number in front of him that no
        part of this system computed, which is the one thing it must never do
    """
    if not facts.alpha and not facts.fast_smalls:
        return deterministic_line(facts)

    try:
        text = (writer(build_curator_prompt(facts)) or "").strip()
    except Exception:
        return deterministic_line(facts)

    if not text or invented_amounts(text, facts.allowed_amounts):
        return deterministic_line(facts)
    return text
