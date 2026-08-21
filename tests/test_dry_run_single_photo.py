"""
Tests for the single-photo dry runner.

Two seams are worth pinning here, and both exist because of a real mistake:

  - Sequence lookup. The photopanel's `_th` image tags do NOT appear in sequence
    order, so indexing by position in the match list returned the wrong photo —
    off by two, silently, while looking entirely correct. The auctioneer's own
    `DisplayFullImage(listing, N, feed)` argument is the sequence.

  - WAF detection. AuctionZip answers 202 with `x-amzn-waf-action: challenge`
    once it wants a browser. An earlier note recorded that as a flat 403 without
    reading the response, and that one wrong word hardened into a gate that
    stopped work it should never have stopped. A challenge is a distinct,
    recoverable condition and has to be named as one.
"""

import pytest

from scripts.dry_run_single_photo import WafChallenge, row_for_sequence


def panel_entry(seq, photo_id, caption, listing="4160518", feed="129"):
    return (f'onClick="DisplayFullImage({listing},{seq},{feed})">'
            f'<img src="//content.auctionzip.com/listing/{listing}/{photo_id}_th">'
            f'<br></td></tr><tr><td><center><b>{caption}</b></center></td></tr>')


# Deliberately NOT in sequence order, which is how the real markup arrives.
PANEL = "".join([
    panel_entry(182, "838424323", ""),
    panel_entry(184, "838424370", "Wonder Woman shield"),
    panel_entry(183, "838424308", ""),
    panel_entry(185, "838424439", "hummingbird window"),
])


class TestRowForSequence:
    def test_finds_by_displayfullimage_argument_not_list_position(self):
        # 183 is third in the markup; positional indexing would return 838424308
        # only by luck, and returns the wrong row for 184.
        assert row_for_sequence(PANEL, 184) == ("838424370", "Wonder Woman shield")

    def test_returns_photo_id_and_caption(self):
        assert row_for_sequence(PANEL, 185) == ("838424439", "hummingbird window")

    def test_uncaptioned_photo_yields_empty_caption_not_none(self):
        photo_id, caption = row_for_sequence(PANEL, 183)
        assert photo_id == "838424308"
        assert caption == ""

    def test_accepts_a_string_sequence(self):
        assert row_for_sequence(PANEL, "182")[0] == "838424323"

    def test_missing_sequence_is_none_not_a_wrong_row(self):
        assert row_for_sequence(PANEL, 999) == (None, None)

    def test_strips_the_preview_wrapper_from_captions(self):
        html = panel_entry(7, "1234", "Preview image for Hamm's sign")
        assert row_for_sequence(html, 7) == ("1234", "Hamm's sign")


class TestWafChallenge:
    def test_is_distinct_from_a_generic_error(self):
        assert issubclass(WafChallenge, RuntimeError)

    def test_carries_the_url_so_the_log_says_what_was_refused(self):
        err = WafChallenge("WAF challenge on https://example.test/fi1.cgi (HTTP 202)")
        assert "202" in str(err) and "fi1.cgi" in str(err)

    def test_is_not_caught_as_a_404_or_403(self):
        # The point of the type: callers fall back and keep going, rather than
        # treating it as "the site is closed to us".
        with pytest.raises(WafChallenge):
            raise WafChallenge("challenge")
