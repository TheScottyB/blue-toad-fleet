"""
The appraiser must never be handed a thumbnail.

Three live Vertex runs were appraised against 140x105 gallery thumbnails — ~5KB,
14,700 pixels. At that size no hallmark, decal or date stamp is legible, so the
model correctly reported it could not see them and emitted a generic checklist
question per lot. The queue looked like a bad prompt. It was a bad input.

These tests make that failure loud instead of silent.
"""

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from src.appraiser.images import (
    MIN_APPRAISAL_EDGE,
    ImageTooSmall,
    assert_appraisal_grade,
    full_size_url,
    image_dimensions,
    is_appraisal_grade,
    read_local_image,
)

AUG22 = Path("data/aug22_gallery_4160518")

# The image drop is gitignored — it is a local cache, not a repo artifact. On a
# clean checkout there is nothing to measure, so the on-disk guards skip rather
# than reporting a red that only means "you have not run the cacher yet".
drop_is_cached = pytest.mark.skipif(
    not any(AUG22.glob("images/*.jpg")),
    reason="gallery drop not cached; run scripts/recache_full_size.py",
)

CANDIDATE_LOTS = [
    "BT-001", "BT-002", "BT-016", "BT-021", "BT-030", "BT-041",
    "BT-048", "BT-050", "BT-066", "BT-087", "BT-181", "BT-235",
]


def _encode(width: int, height: int, fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (90, 90, 90)).save(buf, format=fmt)
    return buf.getvalue()


def webp_of(width: int, height: int) -> bytes:
    """What the gallery CDN actually serves, whatever the .jpg extension claims."""
    return _encode(width, height, "WEBP")


def jpeg_of(width: int, height: int) -> bytes:
    return _encode(width, height, "JPEG")


class TestImageDimensions:
    """Read dimensions with the stdlib — Pillow is a dev dependency, not a runtime one."""

    def test_reads_a_webp_which_is_what_the_gallery_serves(self):
        assert image_dimensions(webp_of(560, 420)) == (560, 420)

    def test_reads_a_webp_thumbnail(self):
        assert image_dimensions(webp_of(140, 105)) == (140, 105)

    def test_reads_a_jpeg(self):
        assert image_dimensions(jpeg_of(560, 420)) == (560, 420)

    @drop_is_cached
    def test_reads_the_real_cached_gallery_files(self):
        """Every file in the drop is named .jpg and is in fact WebP."""
        path = next(iter(sorted((AUG22 / "images").glob("*.jpg"))))
        assert image_dimensions(path.read_bytes()) is not None

    def test_returns_none_for_bytes_that_are_not_an_image(self):
        assert image_dimensions(b"not an image at all") is None

    def test_returns_none_for_empty_bytes(self):
        assert image_dimensions(b"") is None


class TestIsAppraisalGrade:
    def test_a_gallery_thumbnail_is_not_appraisal_grade(self):
        assert not is_appraisal_grade(webp_of(140, 105))

    def test_a_full_size_gallery_image_is_appraisal_grade(self):
        assert is_appraisal_grade(webp_of(560, 420))

    def test_the_short_edge_is_what_counts(self):
        """A wide strip with a tiny short edge still cannot show a hallmark."""
        assert is_appraisal_grade(webp_of(2000, MIN_APPRAISAL_EDGE))
        assert not is_appraisal_grade(webp_of(2000, MIN_APPRAISAL_EDGE - 1))

    def test_unreadable_bytes_are_not_appraisal_grade(self):
        assert not is_appraisal_grade(b"junk")

    def test_no_image_at_all_is_not_appraisal_grade(self):
        assert not is_appraisal_grade(None)


class TestAssertAppraisalGrade:
    def test_raises_with_the_offending_size_in_the_message(self):
        with pytest.raises(ImageTooSmall) as exc:
            assert_appraisal_grade(webp_of(140, 105), lot_id="BT-002")
        msg = str(exc.value)
        assert "BT-002" in msg and "140x105" in msg

    def test_raises_when_there_is_no_image_at_all(self):
        """Appraising caption-only is the silent failure that hid this for three runs."""
        with pytest.raises(ImageTooSmall):
            assert_appraisal_grade(None, lot_id="BT-002")

    def test_passes_a_full_size_image_through_untouched(self):
        data = webp_of(560, 420)
        assert assert_appraisal_grade(data, lot_id="BT-002") is data


class TestFullSizeUrl:
    def test_promotes_a_thumbnail_url_to_the_full_size_variant(self):
        assert full_size_url(
            "//content.auctionzip.com/listing/4160518/838421457_th"
        ) == "//content.auctionzip.com/listing/4160518/838421457_fl"

    def test_leaves_an_already_full_size_url_alone(self):
        url = "//content.auctionzip.com/listing/4160518/838421457_fl"
        assert full_size_url(url) == url

    def test_only_rewrites_the_trailing_suffix(self):
        assert full_size_url(
            "//host/_th/listing/4160518/838421457_th"
        ) == "//host/_th/listing/4160518/838421457_fl"

    def test_leaves_a_url_with_no_suffix_alone(self):
        url = "//content.auctionzip.com/listing/4160518/838421457"
        assert full_size_url(url) == url


@drop_is_cached
class TestTheCachedDropIsAppraisalGrade:
    """
    The regression guard. This is the test that would have caught three bad runs.
    """

    @pytest.mark.parametrize("lot_id", CANDIDATE_LOTS)
    def test_every_appraised_lot_has_a_full_size_photo_on_disk(self, lot_id):
        manifest = json.loads((AUG22 / "manifest.json").read_text())
        by_lot = {f"BT-{p['sequence']:03d}": p for p in manifest["photos"]}

        photo = by_lot.get(lot_id)
        assert photo is not None, f"{lot_id} is appraised but absent from the manifest"

        path = Path(photo["local_path"])
        assert path.exists(), f"{lot_id}: no cached image at {path}"

        data = path.read_bytes()
        w, h = image_dimensions(data)
        assert is_appraisal_grade(data), (
            f"{lot_id} is appraised against a {w}x{h} image "
            f"({path}); the short edge must be >= {MIN_APPRAISAL_EDGE}px"
        )

    def test_the_manifest_records_a_full_size_url_for_every_photo(self):
        manifest = json.loads((AUG22 / "manifest.json").read_text())
        missing = [p["sequence"] for p in manifest["photos"] if not p.get("full_url")]
        assert not missing, f"{len(missing)} photo(s) carry no full_url: {missing[:5]}"

    def test_no_full_url_still_points_at_the_thumbnail_variant(self):
        manifest = json.loads((AUG22 / "manifest.json").read_text())
        thumbs = [p["sequence"] for p in manifest["photos"]
                  if str(p.get("full_url", "")).endswith("_th")]
        assert not thumbs, f"{len(thumbs)} full_url(s) still end in _th: {thumbs[:5]}"


@drop_is_cached
class TestReadingCandidateImages:
    """
    `Path(item.get("local_path", ""))` is `Path(".")`, which exists, so a missing
    path used to raise IsADirectoryError on the batch's main thread and take the
    whole run down. A candidate with no photo is a lot to flag, not a crash.
    """

    def test_a_missing_local_path_reads_as_no_image(self):
        assert read_local_image("") is None

    def test_a_none_local_path_reads_as_no_image(self):
        assert read_local_image(None) is None

    def test_a_directory_reads_as_no_image(self):
        assert read_local_image(str(AUG22 / "images")) is None

    def test_a_path_that_does_not_exist_reads_as_no_image(self):
        assert read_local_image(str(AUG22 / "images" / "nope_does_not_exist.jpg")) is None

    def test_a_real_photo_reads_as_its_bytes(self):
        path = next(iter(sorted((AUG22 / "images").glob("*.jpg"))))
        assert read_local_image(str(path)) == path.read_bytes()
