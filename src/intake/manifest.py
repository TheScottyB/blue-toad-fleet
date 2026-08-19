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
    return _PREVIEW.sub("", (raw or "").strip()).strip()


def lot_number_from(caption: str) -> str | None:
    m = _LOT_NO.search(caption or "")
    return m.group(1) if m else None


def parse_drop(cycle_id: str, listing_id: str,
               entries: list[dict]) -> GalleryDrop:
    """
    Normalise a raw drop listing into photos.

    Entries look like {"name": "fp0007.jpg", "uri": "gs://...", "caption": "..."}.
    Non-images are skipped and recorded rather than silently dropped — a run that
    quietly ignored half the drop is worse than one that says what it ignored.
    """
    drop = GalleryDrop(cycle_id=cycle_id, listing_id=listing_id)

    for e in sorted(entries, key=lambda x: x.get("name", "")):
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
