"""Spatial isolation and itemization for box, tub, tray, and case lots.

A container lot is still one auction lot.  Decomposition describes what is
inside that lot; it must never manufacture one bid per visible object.  The
two-pass boundary is deliberate: the first model call finds the physical sale
boundary, then :func:`crop_to_container` removes neighboring table clutter
before the second call is allowed to name contents.

Coordinates use Gemini's normalized 0..1000 image space.  Keeping that format
at the model boundary makes results resolution-independent while the crop
itself remains deterministic and testable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, Mapping

from src.appraiser.pricing import usable_sources


CONTAINER_TYPES = ["box", "tub", "tray", "case", "basket", "shelf", "other", "none"]
MARKET_ROLES = ["alpha", "supporting", "filler"]


@dataclass(frozen=True)
class ContainerValueEvidence:
    """Evidence-backed lot range after conservative alpha confirmation."""
    low: float
    high: float
    source_count: int
    citations: tuple[str, ...]
    alpha_confirmed: bool
    alpha_name: str | None
    upside_note: str | None = None


_PLACEHOLDER_MARKS = frozenset({
    "", "none", "unmarked", "no mark", "no marks", "illegible", "unreadable",
    "obscured", "unknown", "n/a", "na", "not visible", "none visible",
})
_MARK_QUESTION_KEYWORDS = (
    "mark", "hallmark", "signature", "maker", "stamp", "authentic",
    "genuine", "reproduction", "copy", "karat", "14k", "18k", "sterling",
    "gold-filled", "plate", "serial", "label",
)


def _usable_comp(raw: Mapping | None) -> tuple[float, float, int, tuple[str, ...]] | None:
    if not isinstance(raw, Mapping):
        return None
    raw_low = raw.get("low")
    raw_high = raw.get("high")
    raw_count = raw.get("source_count") if "source_count" in raw else raw.get("sources")
    if isinstance(raw_low, bool) or isinstance(raw_high, bool) or isinstance(raw_count, bool):
        return None
    try:
        low = float(raw["low"])
        high = float(raw["high"])
        count = int(raw.get("source_count") or raw.get("sources") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(low) or not math.isfinite(high):
        return None
    citations = tuple(usable_sources(raw.get("citations") or ()))
    if low <= 0 or high < low or count < 1 or not citations:
        return None
    return low, high, count, citations


def container_alpha_status(
    decomposition: Mapping | None,
    appraisal_questions: Iterable[Mapping] | None = None,
) -> tuple[bool, str | None]:
    """Return (alpha_confirmed, alpha_name) for a container decomposition."""
    if not isinstance(decomposition, Mapping):
        return False, None
    questions = " ".join(str(value).casefold()
                         for value in decomposition.get("questions") or ())
    open_mark_question = any(word in questions for word in _MARK_QUESTION_KEYWORDS)
    for q in appraisal_questions or ():
        if not isinstance(q, Mapping):
            continue
        kind = str(q.get("kind") or "").strip().lower()
        prompt = str(q.get("prompt") or q.get("question") or "").casefold()
        if kind in {"mark", "policy", "scope"} or any(
            word in prompt for word in _MARK_QUESTION_KEYWORDS
        ):
            open_mark_question = True
            break
    alphas = [
        item for item in decomposition.get("contents") or ()
        if isinstance(item, Mapping) and item.get("market_role") == "alpha"
    ]
    alpha = alphas[0] if len(alphas) == 1 else None
    alpha_name = (str(alpha.get("item_name") or "").strip() if alpha else None)
    raw_marks = alpha.get("marks_observed") if alpha else None
    if isinstance(raw_marks, str):
        mark_items = [raw_marks]
    elif isinstance(raw_marks, Iterable):
        mark_items = [str(m) for m in raw_marks if m is not None]
    else:
        mark_items = []
    real_marks = [
        m.strip() for m in mark_items
        if m.strip() and m.strip().casefold() not in _PLACEHOLDER_MARKS
    ]
    alpha_conf = str((alpha or {}).get("confidence") or "high").strip().lower()
    alpha_confirmed = bool(
        alpha
        and alpha_name
        and real_marks
        and alpha_conf not in {"none", "low"}
        and not open_mark_question
    )
    return alpha_confirmed, alpha_name


def price_container_evidence(
    decomposition: Mapping,
    *,
    alpha_comp: Mapping | None,
    bulk_floor: Mapping,
    appraisal_questions: Iterable[Mapping] | None = None,
) -> ContainerValueEvidence:
    """Price one container as alpha-plus-bulk, or bulk-only when unconfirmed.

    An alpha is confirmed only when the item carries an observed mark and no
    determining mark/maker/hallmark question remains open. Model prominence or
    an attractive name alone is upside, never money-bearing evidence.
    """
    bulk = _usable_comp(bulk_floor)
    if bulk is None:
        raise ValueError("container bulk floor requires cited sold evidence")
    alpha_confirmed, alpha_name = container_alpha_status(
        decomposition, appraisal_questions=appraisal_questions,
    )
    confirmed_comp = _usable_comp(alpha_comp) if alpha_confirmed else None
    bulk_low, bulk_high, bulk_count, bulk_citations = bulk
    if confirmed_comp is None:
        return ContainerValueEvidence(
            low=bulk_low,
            high=bulk_high,
            source_count=bulk_count,
            citations=bulk_citations,
            alpha_confirmed=False,
            alpha_name=alpha_name,
            upside_note=(f"Unconfirmed alpha upside: {alpha_name}" if alpha_name else None),
        )
    alpha_low, alpha_high, alpha_count, alpha_citations = confirmed_comp
    return ContainerValueEvidence(
        low=round(alpha_low + bulk_low, 2),
        high=round(alpha_high + bulk_high, 2),
        source_count=alpha_count + bulk_count,
        citations=tuple(dict.fromkeys((*alpha_citations, *bulk_citations))),
        alpha_confirmed=True,
        alpha_name=alpha_name,
    )


@dataclass(frozen=True)
class NormalizedBox:
    """A validated rectangular boundary in normalized 0..1000 coordinates."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @classmethod
    def from_mapping(cls, raw: Mapping | None) -> "NormalizedBox | None":
        if not isinstance(raw, Mapping):
            return None
        try:
            box = cls(*(float(raw[k]) for k in ("x_min", "y_min", "x_max", "y_max")))
        except (KeyError, TypeError, ValueError):
            return None
        if not all(0.0 <= n <= 1000.0 for n in (
                box.x_min, box.y_min, box.x_max, box.y_max)):
            return None
        if box.x_max <= box.x_min or box.y_max <= box.y_min:
            return None
        return box

    def pixel_box(self, width: int, height: int, padding: float = 0.015) -> tuple[int, int, int, int]:
        """Convert to a Pillow crop box, adding a small bounded rim margin."""
        if width < 1 or height < 1:
            raise ValueError("image dimensions must be positive")
        if not 0.0 <= padding <= 0.25:
            raise ValueError("padding must be between 0 and 0.25")

        span_x = self.x_max - self.x_min
        span_y = self.y_max - self.y_min
        x1 = max(0.0, self.x_min - span_x * padding)
        y1 = max(0.0, self.y_min - span_y * padding)
        x2 = min(1000.0, self.x_max + span_x * padding)
        y2 = min(1000.0, self.y_max + span_y * padding)

        # int() floors the near edge; the +999 form implements integer ceil on
        # the far edge without importing floating-point rounding conventions.
        left = int(x1 * width / 1000.0)
        top = int(y1 * height / 1000.0)
        right = int((x2 * width + 999.0) / 1000.0)
        bottom = int((y2 * height + 999.0) / 1000.0)
        return left, top, min(width, max(left + 1, right)), min(height, max(top + 1, bottom))

    def as_dict(self) -> dict[str, float]:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
        }


def crop_to_container(
    image_bytes: bytes,
    boundary: NormalizedBox | Mapping,
    *,
    padding: float = 0.015,
) -> bytes:
    """Return an appraisal-grade JPEG containing only the container boundary."""
    box = boundary if isinstance(boundary, NormalizedBox) else NormalizedBox.from_mapping(boundary)
    if box is None:
        raise ValueError("container boundary is missing or invalid")
    if not image_bytes:
        raise ValueError("container crop requires image bytes")

    # Pillow is a dev dependency (requirements-dev.txt). Cloud Run installs
    # only requirements.txt; GET / uses visible_contents, never this crop.
    from PIL import Image, ImageOps

    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        cropped = image.crop(box.pixel_box(image.width, image.height, padding=padding))
        output = BytesIO()
        cropped.save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue()


def visible_contents(
    payload: Mapping | None,
    *,
    include_unconfirmed_alpha: bool = True,
    appraisal_questions: Iterable[Mapping] | None = None,
) -> tuple[str, ...]:
    """Produce conservative clerk-line item strings from a decomposition.

    Filler remains in the audit payload, but not in the identifying clause used
    for appraisal research or the absentee clerk line.  Background exclusions
    are never contents.  This function intentionally has no cross-lot state:
    decomposition is not duplicate detection.
    """
    if not isinstance(payload, Mapping) or not payload.get("is_container_lot"):
        return ()

    alpha_ok, _ = container_alpha_status(
        payload, appraisal_questions=appraisal_questions,
    )
    out: list[str] = []
    seen: set[str] = set()
    for raw in payload.get("contents") or []:
        if (not isinstance(raw, Mapping)
                or raw.get("market_role") not in {"alpha", "supporting"}):
            continue
        if raw.get("market_role") == "alpha" and not include_unconfirmed_alpha and not alpha_ok:
            continue
        name = " ".join(str(raw.get("item_name") or "").split())
        if not name:
            continue
        try:
            quantity = max(1, int(raw.get("quantity") or 1))
        except (TypeError, ValueError):
            quantity = 1
        item = f"{quantity}× {name}" if quantity > 1 else name
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return tuple(out)


def append_visible_contents(description: str, payload: Mapping | None) -> str:
    """Append in-boundary contents to one lot description, without duplication."""
    description = " ".join((description or "").split())
    contents = [item for item in visible_contents(payload)
                if item.casefold() not in description.casefold()]
    if not contents:
        return description
    prefix = f"{description} — " if description else ""
    return prefix + "contents: " + ", ".join(contents)


__all__ = [
    "CONTAINER_TYPES", "MARKET_ROLES", "ContainerValueEvidence", "NormalizedBox",
    "container_alpha_status", "crop_to_container", "visible_contents",
    "append_visible_contents", "price_container_evidence",
]
