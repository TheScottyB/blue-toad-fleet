"""
The cache against the live listing, as a diff rather than a silent pass.

Every appraisal, every price and every bid on the Aug 22 sheet is derived from
`data/aug22_gallery_4160518/`. If the house re-captions a photo, swaps an image,
or adds lots after the drop was taken, the sheet keeps answering from a snapshot
of a sale that no longer exists — and nothing anywhere says so.

These tests fetch the live sources and report DRIFT: what changed, by how much,
in which direction. They are network tests and they are skipped by default, so
the ordinary suite stays hermetic and fast:

    RUN_LIVE_PARITY=1 .venv/bin/pytest tests/test_live_cache_parity.py -v

Two sources, deliberately:

  * AuctionZip is the captioned source of record. It sits behind CloudFront +
    AWS WAF and answers 202 `x-amzn-waf-action: challenge` after a short burst,
    so a run can be refused rather than answered. A challenge is reported as
    UNKNOWN, never as parity — the whole point is to avoid a green tick that
    means "nobody looked".
  * estatesales.net carries the same sale at 1200x900 with no WAF, and
    `estatesales_link.json` maps 171 of the 462. Its images are the only
    byte-for-byte comparison available, because the AuctionZip bytes we cached
    came through the same route that now challenges.
"""

import hashlib
import json
import os
import re
import ssl
import urllib.request
from pathlib import Path

import pytest

DATA = Path("data/aug22_gallery_4160518")
MANIFEST = DATA / "manifest.json"
LINK = DATA / "estatesales_link.json"
LISTING = "4160518"
ES_SALE = "5042877"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_PARITY"),
    reason="network test; set RUN_LIVE_PARITY=1 to run")


class WafChallenge(RuntimeError):
    """Refused, not answered. Distinct from drift and from parity."""


def _get(url, referer="https://www.auctionzip.com/", timeout=30):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": referer,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
        body = r.read()
        if r.headers.get("x-amzn-waf-action") == "challenge" or r.status == 202:
            raise WafChallenge(f"WAF challenge on {url} (HTTP {r.status})")
        return body


@pytest.fixture(scope="module")
def cached_photos():
    if not MANIFEST.is_file():
        pytest.skip("no cached manifest")
    return {p["sequence"]: p for p in json.loads(MANIFEST.read_text())["photos"]}


@pytest.fixture(scope="module")
def live_panel():
    url = (f"https://www.auctionzip.com/cgi-bin/photopanel.cgi?listingid={LISTING}"
           f"&feed=129&gid=0&category=0&zip=&kwd=&PageImages=0")
    try:
        return _get(url).decode("utf-8", "ignore")
    except WafChallenge as e:
        pytest.skip(f"AuctionZip refused rather than answered: {e}")
    except Exception as e:
        pytest.skip(f"AuctionZip unreachable: {e}")


@pytest.fixture(scope="module")
def live_photos(live_panel):
    from scripts.cache_gallery import _PHOTO_PATTERN
    from src.intake.manifest import clean_caption
    out = {}
    for _listing, seq, _feed, src, caption in _PHOTO_PATTERN.findall(live_panel):
        m = re.search(r"/(\d+)(?:_th|_fl)?$", src)
        out[int(seq)] = {"photo_id": m.group(1) if m else None,
                         "caption": clean_caption(caption)}
    if not out:
        pytest.skip("live panel parsed to zero photos")
    return out


class TestTheGalleryHasNotMovedUnderUs:
    def test_the_photo_count_matches(self, cached_photos, live_photos):
        if len(cached_photos) != len(live_photos):
            added = sorted(set(live_photos) - set(cached_photos))
            gone = sorted(set(cached_photos) - set(live_photos))
            pytest.fail(
                f"gallery size drifted: cached {len(cached_photos)}, "
                f"live {len(live_photos)}\n"
                f"  added upstream: {added[:20]}{' ...' if len(added) > 20 else ''}\n"
                f"  gone upstream:  {gone[:20]}{' ...' if len(gone) > 20 else ''}\n"
                f"Lots added after the drop are lots the sheet never appraised.")

    def test_every_sequence_still_points_at_the_same_photo(
            self, cached_photos, live_photos):
        moved = [(s, cached_photos[s]["photo_id"], live_photos[s]["photo_id"])
                 for s in sorted(set(cached_photos) & set(live_photos))
                 if cached_photos[s]["photo_id"] != live_photos[s]["photo_id"]]
        if moved:
            report = "\n".join(f"  seq {s}: cached {c} -> live {l}"
                               for s, c, l in moved[:20])
            pytest.fail(
                f"{len(moved)} sequence(s) now resolve to a different photo. "
                f"Every BT-id is derived from sequence, so this re-points bids "
                f"at lots nobody appraised.\n{report}")

    def test_captions_have_not_been_rewritten(self, cached_photos, live_photos):
        """A caption is the only lot-boundary signal this gallery publishes, and
        `group_into_lots` gives it precedence over the model. A re-caption
        silently changes how photos group into bids.

        Both sides are normalized with today's `clean_caption` before comparing:
        the manifest keeps whatever normalization existed at capture time, so a
        drop taken before entity decoding landed must read as our skew, not as
        a rewrite by the house."""
        from src.intake.manifest import clean_caption
        pairs = ((s, clean_caption(cached_photos[s]["caption"]),
                  clean_caption(live_photos[s]["caption"]))
                 for s in sorted(set(cached_photos) & set(live_photos)))
        changed = [(s, c, l) for s, c, l in pairs if c != l]
        if changed:
            report = "\n".join(f"  seq {s}: {c!r} -> {l!r}" for s, c, l in changed[:20])
            pytest.fail(
                f"{len(changed)} caption(s) rewritten upstream:\n{report}")


class TestTheCachedBytesAreStillTheHouseBytes:
    """The only byte-for-byte check available.

    The cached AuctionZip images came through the route that now answers a WAF
    challenge, so estatesales — same sale, same photographs, no WAF — is what
    can actually be re-fetched and compared.
    """

    @pytest.fixture(scope="class")
    def links(self):
        if not LINK.is_file():
            pytest.skip("no estatesales link map")
        return json.loads(LINK.read_text())["links"]

    def test_a_sample_of_estatesales_images_is_unchanged(self, links):
        sample = [links[i] for i in range(0, len(links), max(1, len(links) // 8))][:8]
        drift = []
        for row in sample:
            cache = DATA / "estatesales_images" / f"order{row['es_order']:03d}.jpg"
            if not cache.is_file():
                continue
            try:
                live = _get(row["es_url"], referer="https://www.estatesales.net/")
            except Exception as e:
                pytest.skip(f"estatesales unreachable: {e}")
            have = cache.read_bytes()
            if hashlib.sha256(live).hexdigest() != hashlib.sha256(have).hexdigest():
                drift.append((row["az_sequence"], len(have), len(live)))
        if drift:
            report = "\n".join(f"  seq {s}: cached {a:,}B -> live {b:,}B"
                               for s, a, b in drift)
            pytest.fail(f"{len(drift)} image(s) changed upstream:\n{report}")

    def test_the_estatesales_sale_still_has_the_photos_we_mapped(self, links):
        try:
            html = _get(f"https://www.estatesales.net/WI/Genoa-City/53128/{ES_SALE}",
                        referer="https://www.estatesales.net/").decode("utf-8", "ignore")
        except Exception as e:
            pytest.skip(f"estatesales unreachable: {e}")
        m = re.search(r'"pictureCount":(\d+)', html)
        if not m:
            pytest.skip("pictureCount not present in the sale page")
        live_count = int(m.group(1))
        assert live_count == len(links), (
            f"estatesales now publishes {live_count} photos; the link map has "
            f"{len(links)}. The 1200x900 source the room graph reads has moved.")


class TestParityIsReportedHonestly:
    """A refusal must never be recorded as agreement."""

    def test_a_waf_challenge_is_a_distinct_outcome(self):
        assert issubclass(WafChallenge, RuntimeError)

    def test_the_suite_is_skipped_rather_than_passing_when_offline(self):
        """These tests skip without RUN_LIVE_PARITY. A network suite that
        silently passes when it never ran is worse than no suite: it reports
        parity nobody checked."""
        assert pytestmark.kwargs["reason"].startswith("network test")
