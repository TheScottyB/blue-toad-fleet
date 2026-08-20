"""
Parsing a gallery drop into work items.

Real drops are messy: filenames in inconsistent order, captions missing on
extra angles, the occasional stray file. The rules here are the boring ones
that stop a mess reaching the model — and every one of them exists because
getting it wrong quietly poisons the sheet downstream.
"""

from dataclasses import dataclass, field
import re

# "Preview image for {caption}" is how AuctionZip embeds captions in the gallery
# export. Strip it so the model sees the caption, not the wrapper.
_PREVIEW = re.compile(r"^\s*preview image for\s+", re.IGNORECASE)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Lot numbers as they appear in Blue Toad captions: "Lot 47", "#47", "47."
_LOT_NO = re.compile(r"(?:^|\b)(?:lot\s*#?\s*|#)(\d{1,4})\b", re.IGNORECASE)


@dataclass(frozen=True)
class PhotoRef:
    photo_id: str
    uri: str
    caption: str = ""
    sequence: int = 0

    @property
    def has_caption(self) -> bool:
        return bool(self.caption.strip())


@dataclass
class GalleryDrop:
    cycle_id: str
    listing_id: str
    photos: list[PhotoRef] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def captioned(self) -> int:
        return sum(1 for p in self.photos if p.has_caption)


@dataclass(frozen=True)
class WorkItem:
    """One Pub/Sub message. Idempotency key is (cycle_id, photo_id)."""
    cycle_id: str
    photo_id: str
    uri: str
    caption: str
    sequence: int
    lot_hint: str | None = None
    previous_caption: str | None = None

    @property
    def idempotency_key(self) -> str:
        return f"{self.cycle_id}:{self.photo_id}"


def clean_caption(raw: str) -> str:
    cleaned = _PREVIEW.sub("", (raw or "").strip()).strip()
    cleaned = re.sub(r"\bnon-spoprt\b", "non-sport", cleaned, flags=re.IGNORECASE)
    return cleaned


def lot_number_from(caption: str) -> str | None:
    m = _LOT_NO.search(caption or "")
    return m.group(1) if m else None


def _natural_key(name: str) -> tuple:
    """Sort fp9 before fp10.

    Lexicographic order puts fp10 first, which silently rewires which photo is
    "previous" — and `same_lot_as_previous` is the signal that merges angles of
    one lot. Wrong order there means wrong merges, which means duplicate bids.
    Each part is tagged so an int is never compared against a str.
    """
    parts = re.split(r"(\d+)", (name or "").lower())
    return tuple((1, int(p), "") if p.isdigit() else (0, 0, p) for p in parts)


@dataclass(frozen=True)
class TriagedPhoto:
    """One photo after triage. `is_lot`/`same_lot_as_previous` come from the model."""
    photo_id: str
    caption: str = ""
    is_lot: bool = True
    same_lot_as_previous: bool = False


@dataclass(frozen=True)
class LotGroup:
    """Every photo of ONE physical lot. Exactly one bid slot per group."""
    lot_key: str
    photo_ids: tuple[str, ...]

    @property
    def primary_photo_id(self) -> str:
        return self.photo_ids[0]


def group_into_lots(triaged) -> list[LotGroup]:
    """Collapse per-photo triage into one group per physical lot.

    A gallery carries several photos of the same lot. Triage already asked the
    model `same_lot_as_previous`, but nothing read the answer, so two angles of
    one shelf became two independent Lots — separately priced, separately
    budgeted, and both bid. That is a duplicate absentee bid with real money on
    it, which is why grouping happens here, before anything reaches bidmath.

    Precedence, strongest signal first:
      1. An explicit lot number in the caption. The auctioneer's own numbering
         is ground truth and order-independent, so it merges across a gallery
         that interleaves lots and it overrides a wrong model flag.
      2. `same_lot_as_previous` — chains onto the group just opened. A duplicate
         angle is usually `is_lot=False` AND `same_lot_as_previous=True`; it is
         not its own lot but it IS evidence about the previous one, so it joins
         that group rather than being dropped.
      3. `is_lot=False` with no same-lot flag is signage or gallery filler and
         never reaches the sheet.
    """
    groups: list[dict] = []
    by_number: dict[str, dict] = {}
    last: dict | None = None

    for p in triaged:
        number = lot_number_from(p.caption)
        if number is not None:
            g = by_number.get(number)
            if g is None:
                g = {"key": number, "photos": []}
                by_number[number] = g
                groups.append(g)
            g["photos"].append(p.photo_id)
            last = g
            continue

        if p.same_lot_as_previous and last is not None:
            last["photos"].append(p.photo_id)
            continue

        if not p.is_lot:
            continue

        g = {"key": f"seq:{p.photo_id}", "photos": [p.photo_id]}
        groups.append(g)
        last = g

    return [LotGroup(lot_key=g["key"], photo_ids=tuple(g["photos"])) for g in groups]


def parse_drop(cycle_id: str, listing_id: str,
               entries: list[dict]) -> GalleryDrop:
    """
    Normalise a raw drop listing into photos.

    Entries look like {"name": "fp0007.jpg", "uri": "gs://...", "caption": "..."}.
    Non-images are skipped and recorded rather than silently dropped — a run that
    quietly ignored half the drop is worse than one that says what it ignored.
    """
    drop = GalleryDrop(cycle_id=cycle_id, listing_id=listing_id)

    for e in sorted(entries, key=lambda x: _natural_key(x.get("name", ""))):
        name = e.get("name", "")
        suffix = name[name.rfind("."):].lower() if "." in name else ""
        if suffix not in _IMAGE_SUFFIXES:
            drop.skipped.append(name)
            continue
        drop.photos.append(PhotoRef(
            photo_id=name.rsplit(".", 1)[0],
            uri=e.get("uri", ""),
            caption=clean_caption(e.get("caption", "")),
            sequence=len(drop.photos),
        ))
    return drop


def plan_fanout(drop: GalleryDrop) -> list[WorkItem]:
    """
    One work item per photo, carrying the previous photo's caption.

    That last part matters: uncaptioned photos in these galleries are almost
    always extra angles of the item above them. Handing the model the preceding
    caption is what lets it answer "another view of the same lot?" instead of
    inventing a lot that does not exist.
    """
    items: list[WorkItem] = []
    last_caption: str | None = None

    for p in drop.photos:
        items.append(WorkItem(
            cycle_id=drop.cycle_id,
            photo_id=p.photo_id,
            uri=p.uri,
            caption=p.caption,
            sequence=p.sequence,
            lot_hint=lot_number_from(p.caption),
            previous_caption=last_caption if not p.has_caption else None,
        ))
        if p.has_caption:
            last_caption = p.caption
    return items
