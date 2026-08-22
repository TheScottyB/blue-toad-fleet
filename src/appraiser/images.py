"""
What counts as an image the Appraiser is allowed to look at.

The gallery publishes two variants of every photo: `_th` at 140x105 and `_fl` at
560x420. The cache only ever pulled `_th`, so three live Vertex runs appraised
14,700-pixel thumbnails. The model behaved correctly — it reported that corner
wear, hallmarks and date stamps were not legible, and asked about each one. A
queue of generic questions was the symptom; a 5KB thumbnail was the cause.

So the size check lives here, next to the appraiser, and it raises. Appraising
blind is the failure mode that hid this for three cycles, and a failure that
prints nothing is worse than one that stops the run.

Pillow is a dev dependency, not a runtime one — Cloud Run installs only
requirements.txt — so dimensions are read straight out of the file header.

Note the gallery serves WebP under a `.jpg` filename. Trusting the extension is
what a reader that only understood JPEG would do, and it would report every
photo as unreadable, which is a different way of failing quietly. Sniff the
magic bytes, not the name.
"""

from pathlib import Path

# Shortest edge, in pixels, below which a photo cannot carry a determining
# attribute. The gallery's own two variants sit either side of it: `_th` is
# 105px short-edge, `_fl` is 420px.
MIN_APPRAISAL_EDGE = 300

_THUMB_SUFFIX = "_th"
_FULL_SUFFIX = "_fl"

# Start-of-frame markers, in all their baseline/progressive/lossless flavours.
# The four excluded values in these ranges (C4, C8, CC) are DHT, JPG and DAC.
_SOF_MARKERS = frozenset(
    (*range(0xC0, 0xC4), *range(0xC5, 0xC8),
     *range(0xC9, 0xCC), *range(0xCD, 0xD0))
)

# Markers that carry no length field: TEM and the eight restart markers.
_STANDALONE_MARKERS = frozenset((0x01, *range(0xD0, 0xD8)))


class ImageTooSmall(ValueError):
    """Raised rather than appraising a lot from a thumbnail, or from nothing."""


def image_dimensions(data: bytes | None) -> tuple[int, int] | None:
    """
    (width, height) for a WebP or JPEG, or None if the bytes aren't readable.

    None is the safe answer: an unreadable photo is not appraisal grade, so an
    unrecognised format refuses the appraisal rather than passing it through.
    """
    if not data or len(data) < 16:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp_dimensions(data)
    if data[0] == 0xFF and data[1] == 0xD8:
        return _jpeg_dimensions(data)
    return None


def image_mime_type(data: bytes | None) -> str | None:
    """MIME type from image bytes, independent of the CDN's misleading suffix."""
    if not data:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    """Canvas size from a VP8 (lossy), VP8L (lossless) or VP8X (extended) chunk."""
    fourcc = data[12:16]

    if fourcc == b"VP8 ":
        # 3-byte frame tag, 3-byte sync code, then 14-bit width and height.
        if len(data) < 30 or data[23:26] != b"\x9d\x01\x2a":
            return None
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height

    if fourcc == b"VP8L":
        # 1 signature byte, then 14 bits of (width - 1) and 14 of (height - 1).
        if len(data) < 25 or data[20] != 0x2F:
            return None
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1

    if fourcc == b"VP8X":
        # 4 bytes of flags, then 24-bit (canvas width - 1) and height.
        if len(data) < 30:
            return None
        return (int.from_bytes(data[24:27], "little") + 1,
                int.from_bytes(data[27:30], "little") + 1)

    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """
    Size from the SOF segment.

    Walks the segment chain rather than scanning for a byte pattern — a
    thumbnail embedded in EXIF would otherwise be found before the real frame.
    """
    i, n = 2, len(data)
    while i + 3 < n:
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]

        if marker == 0xFF:          # fill byte; the marker starts later
            i += 1
            continue
        if marker in _STANDALONE_MARKERS:
            i += 2
            continue
        if marker == 0xD9:          # end of image, no frame found
            return None

        segment_length = (data[i + 2] << 8) | data[i + 3]
        if segment_length < 2:
            return None

        if marker in _SOF_MARKERS:
            if i + 9 > n:
                return None
            height = (data[i + 5] << 8) | data[i + 6]
            width = (data[i + 7] << 8) | data[i + 8]
            return width, height

        i += 2 + segment_length

    return None


def is_appraisal_grade(data: bytes | None) -> bool:
    """True when the photo is large enough for a determining attribute to show."""
    dims = image_dimensions(data)
    return dims is not None and min(dims) >= MIN_APPRAISAL_EDGE


def assert_appraisal_grade(data: bytes | None, lot_id: str) -> bytes:
    """Return the bytes, or refuse the appraisal and say exactly why."""
    if data is None:
        raise ImageTooSmall(
            f"{lot_id}: no photo supplied. Appraising from the caption alone "
            f"produces guesses, not attributions."
        )

    dims = image_dimensions(data)
    if dims is None:
        raise ImageTooSmall(
            f"{lot_id}: could not read image dimensions from {len(data)} byte(s); "
            f"refusing to appraise an unverifiable photo."
        )

    width, height = dims
    if min(dims) < MIN_APPRAISAL_EDGE:
        raise ImageTooSmall(
            f"{lot_id}: photo is {width}x{height}; the short edge must be at "
            f"least {MIN_APPRAISAL_EDGE}px to appraise. This is a gallery "
            f"thumbnail — re-cache the full-size variant."
        )

    return data


def read_local_image(local_path: str | None) -> bytes | None:
    """
    Bytes for a cached photo, or None if there isn't one.

    `Path("")` is `Path(".")`, and a directory reports that it exists, so the
    obvious one-liner raises IsADirectoryError instead of returning nothing.
    A candidate with no photo should be flagged by the size check downstream,
    not crash the batch that was reading it.
    """
    if not local_path:
        return None
    path = Path(local_path)
    return path.read_bytes() if path.is_file() else None


def full_size_url(url: str | None) -> str | None:
    """Promote a `_th` gallery URL to its `_fl` full-size sibling."""
    if url and url.endswith(_THUMB_SUFFIX):
        return url[: -len(_THUMB_SUFFIX)] + _FULL_SUFFIX
    return url
