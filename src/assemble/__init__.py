"""
Assemble — appraised photos become priceable lots.

This is the seam between the Appraiser (which sees one photo at a time) and
bidmath (which prices one lot at a time). Nothing occupied it before: `Lot`
objects existed only in hand-authored demo seed JSON, so the triage signal
`same_lot_as_previous` was collected and thrown away, and several photos of one
physical lot would have become several independent bids on one absentee sheet.

The bias here is conservative on purpose. An absentee sheet is committed before
the auctioneer opens the floor, so an optimistic merge is not discovered until
the invoice arrives.

Three rules decide what a group of photos says about one lot:

  * **Condition takes the worst angle.** Damage visible in any photo is real
    damage; a photo that did not show the chip is not evidence there is no
    chip. So the group's condition_penalty is the maximum, not the first and
    not the mean.
  * **Identification comes from the best-evidence photo** — highest appraiser
    confidence, ties resolved to the primary (earliest) photo. A blurry angle
    must not define what the lot is or how well it fits the shop.
  * **Comps are looked up, never blended.** A comp range is a matched set of
    low/high/source_count; mixing lows from one appraisal with highs from
    another manufactures a range no appraisal produced. A lot with no comp gets
    an explicit empty estimate and bidmath routes it to human pricing, which is
    the honest outcome rather than an invented number.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping

from src.bidmath import CompEstimate, Confidence, Lot
from src.intake.manifest import TriagedPhoto, group_into_lots

_CONFIDENCE_RANK = {
    Confidence.NONE: 0,
    Confidence.LOW: 1,
    Confidence.MEDIUM: 2,
    Confidence.HIGH: 3,
}

# An explicit "we found nothing" rather than a fabricated range. has_external_comp
# is False for this, so price_lot returns needs_human_pricing instead of a bid.
NO_COMP = CompEstimate(low=None, high=None, source_count=0,
                       confidence=Confidence.NONE)


@dataclass(frozen=True)
class AppraisedPhoto:
    """One photo after triage and appraisal.

    `is_lot` / `same_lot_as_previous` come from TRIAGE_SCHEMA; the rest from
    APPRAISAL_SCHEMA. Note the appraiser produces no price — comps are a
    separate component, so they arrive alongside rather than inside this.
    """
    photo_id: str
    caption: str = ""
    is_lot: bool = True
    same_lot_as_previous: bool = False
    identification: str = ""
    category: str = "unsorted"
    condition_penalty: float = 0.0
    fit_score: float = 0.0
    confidence: Confidence = Confidence.NONE
    # Spatially isolated alpha/supporting contents from this physical lot.
    # These refine the clerk line; they are not independently priceable lots.
    contents: tuple[str, ...] = ()


def assemble_lots(
    appraised: Iterable[AppraisedPhoto],
    comps: Mapping[str, CompEstimate] | None = None,
) -> list[Lot]:
    """Collapse per-photo appraisals into one `Lot` per physical lot.

    `comps` is keyed by lot id — the auctioneer's lot number where the caption
    carried one. Missing keys are expected, not an error.
    """
    appraised = list(appraised)
    comps = comps or {}
    by_id = {p.photo_id: p for p in appraised}

    groups = group_into_lots([
        TriagedPhoto(
            photo_id=p.photo_id,
            caption=p.caption,
            is_lot=p.is_lot,
            same_lot_as_previous=p.same_lot_as_previous,
        )
        for p in appraised
    ])

    lots: list[Lot] = []
    for group in groups:
        members = [by_id[pid] for pid in group.photo_ids]

        # max() returns the FIRST maximal element, so a tie falls back to the
        # primary photo rather than to whichever angle happened to come last.
        best = max(members, key=lambda p: _CONFIDENCE_RANK.get(p.confidence, 0))
        primary = by_id[group.primary_photo_id]

        # Worst angle wins, then clamp: a model slip must not reach the Lot,
        # or any sheet or console rendered straight from it.
        worst = max(m.condition_penalty for m in members)
        penalty = min(max(worst, 0.0), 1.0)

        contents: list[str] = []
        seen_contents: set[str] = set()
        for member in members:
            for item in member.contents:
                item = " ".join(str(item).split())
                key = item.casefold()
                if item and key not in seen_contents:
                    seen_contents.add(key)
                    contents.append(item)

        description = best.identification or primary.caption
        new_contents = [item for item in contents
                        if item.casefold() not in description.casefold()]
        if new_contents:
            prefix = f"{description} — " if description else ""
            description = prefix + f"contents: {', '.join(new_contents)}"

        lots.append(Lot(
            lot_id=group.lot_key,
            caption=description,
            category=best.category,
            fit_score=best.fit_score,
            condition_penalty=penalty,
            comp=comps.get(group.lot_key, NO_COMP),
        ))

    return lots


__all__ = ["AppraisedPhoto", "NO_COMP", "assemble_lots"]
