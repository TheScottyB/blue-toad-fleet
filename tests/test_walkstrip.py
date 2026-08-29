"""The walk strip's contracts.

The strip is a claim about the walk: every photo, in shot order, lot runs
visible, returns badged at both ends, dropped photos shown rather than hidden.
Each test pins one of those sentences; the escaping tests exist because gallery
captions are third-party text and have already put `M&amp;Ms` into live HTML
once (F16).
"""

import pytest
from starlette.testclient import TestClient

import src.server as server
from src.gate.walkstrip import closure_pairs, render_walk_strip
from src.intake.spatial import Seat, Zone
from src.server import app


def _photo(seq: int, caption: str = "") -> dict:
    return {
        "sequence": seq,
        "photo_id": f"p{seq}",
        "caption": caption,
        "thumb_url": f"//cdn.example/{seq}_th",
        "local_path": "",
    }


def _seat(lot_id: str, *pids: str) -> Seat:
    return Seat(lot_id=lot_id, zone=Zone.UNKNOWN, walk_index=0,
                photo_ids=tuple(pids))


SEQS = {f"p{n}": n for n in range(1, 500)}


class TestClosurePairs:
    def test_far_apart_members_are_a_return(self):
        pairs = closure_pairs([_seat("BT-002", "p2", "p3", "p181")],
                              sequences=SEQS)
        assert pairs == [("BT-002", 2, 181)]

    def test_adjacent_members_are_not(self):
        assert closure_pairs([_seat("BT-005", "p5", "p6", "p8")],
                             sequences=SEQS) == []

    def test_two_returns_both_report_against_the_anchor(self):
        pairs = closure_pairs([_seat("BT-001", "p1", "p2", "p90", "p200")],
                              sequences=SEQS)
        assert pairs == [("BT-001", 1, 90), ("BT-001", 1, 200)]


class TestRender:
    def test_every_photo_renders_once_in_walk_order(self):
        photos = [_photo(n) for n in (3, 1, 2)]
        html = render_walk_strip(photos, [_seat("BT-001", "p1", "p2", "p3")],
                                 cycle_id="c", listing_id="l")
        assert html.count('<figure class="tile') == 3
        assert html.index(">001</span>") < html.index(">002</span>") \
            < html.index(">003</span>")

    def test_serpentine_rows_alternate_direction_markers(self):
        photos = [_photo(n) for n in range(1, 8)]
        html = render_walk_strip(photos, [], cycle_id="c", listing_id="l",
                                 row_len=3)
        assert html.count('<div class="row rev">') == 1
        assert html.count('<div class="row">') == 2

    def test_third_party_caption_text_is_escaped(self):
        photos = [_photo(1, caption='<script>alert(1)</script> M&Ms "tray"')]
        html = render_walk_strip(photos, [_seat("BT-001", "p1")],
                                 cycle_id="c", listing_id="l")
        assert "<script>alert(1)</script>" not in html
        assert "M&amp;Ms" in html
        assert "&quot;tray&quot;" in html

    def test_ungrouped_photo_is_shown_dashed_not_hidden(self):
        photos = [_photo(1), _photo(2)]
        html = render_walk_strip(photos, [_seat("BT-001", "p1")],
                                 cycle_id="c", listing_id="l")
        assert html.count('<figure class="tile') == 2
        assert 'class="tile ungrouped"' in html
        assert "1 not grouped by the current pass" in html

    def test_walk_return_is_badged_at_both_ends(self):
        photos = [_photo(n) for n in (2, 3, 181)]
        html = render_walk_strip(photos, [_seat("BT-002", "p2", "p3", "p181")],
                                 cycle_id="c", listing_id="l")
        assert html.count("&#10554; BT-002</span>") == 2
        assert "the walk returned at 181" in html

    def test_lot_boundary_starts_a_new_run_color_and_label(self):
        photos = [_photo(1), _photo(2), _photo(3)]
        seats = [_seat("BT-001", "p1", "p2"), _seat("BT-003", "p3")]
        html = render_walk_strip(photos, seats, cycle_id="c", listing_id="l")
        assert 'class="tile run-a"' in html and 'class="tile run-b"' in html
        assert html.count('<span class="lot">') == 2


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def manifest_cache_reset():
    yield
    server._MANIFEST_BY_SEQ = None


class TestRoutes:
    def test_walk_page_serves(self, client):
        r = client.get("/walk")
        assert r.status_code == 200
        assert "The Walk" in r.text
        assert 'class="tile' in r.text

    def test_walk_page_joins_seats_to_manifest_photos(self, client):
        # Seats carry BT-<seq> ids, the manifest carries gallery ids; without
        # the route's translation every tile rendered ungrouped (found live:
        # "462 not grouped by the current pass").
        r = client.get("/walk")
        assert 'class="tile run-' in r.text
        assert "462 not grouped" not in r.text

    def test_unknown_sequence_is_404(self, client):
        assert client.get("/walk/photo/99999").status_code == 404

    def test_missing_local_bytes_redirect_to_the_recorded_cdn_thumb(
            self, client, manifest_cache_reset):
        server._manifest_by_sequence()
        server._MANIFEST_BY_SEQ[99998] = {
            "sequence": 99998, "photo_id": "px", "local_path": "",
            "thumb_url": "//content.auctionzip.com/listing/x/px_th",
        }
        r = client.get("/walk/photo/99998", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == \
            "https://content.auctionzip.com/listing/x/px_th"

    def test_cached_bytes_serve_with_a_sniffed_mime(self, client):
        r = client.get("/walk/photo/1")
        assert r.status_code in (200, 302)
        if r.status_code == 200:
            assert r.headers["content-type"] in ("image/jpeg", "image/webp")
            assert len(r.content) > 100
