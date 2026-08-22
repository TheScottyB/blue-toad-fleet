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

from dataclasses import dataclass
from io import BytesIO
from typing import Mapping


CONTAINER_TYPES = ["box", "tub", "tray", "case", "basket", "shelf", "other", "none"]
MARKET_ROLES = ["alpha", "supporting", "filler"]


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


def visible_contents(payload: Mapping | None) -> tuple[str, ...]:
    """Produce conservative clerk-line item strings from a decomposition.

    Filler remains in the audit payload, but not in the identifying clause used
    for appraisal research or the absentee clerk line.  Background exclusions
    are never contents.  This function intentionally has no cross-lot state:
    decomposition is not duplicate detection.
    """
    if not isinstance(payload, Mapping) or not payload.get("is_container_lot"):
        return ()

    out: list[str] = []
    seen: set[str] = set()
    for raw in payload.get("contents") or []:
        if (not isinstance(raw, Mapping)
                or raw.get("market_role") not in {"alpha", "supporting"}):
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
    "CONTAINER_TYPES", "MARKET_ROLES", "NormalizedBox",
    "crop_to_container", "visible_contents", "append_visible_contents",
]
