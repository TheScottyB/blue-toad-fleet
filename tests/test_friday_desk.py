"""Friday desk: walk → grouping/scope questions → envelope → clerk draft."""

import re

import pytest
from starlette.testclient import TestClient

from src.appraisal import build_queue
from src.bidmath import CompEstimate, Confidence, Lot, allocate, price_lot, summarize
from src.gate import CycleView, render_console
from src.intake.spatial import PhotoMember, Seat, Zone
from src.server import app, get_aug22_state
from src import server as server_mod


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_desk_loop():
    server_mod.reset_walk_edits()
    server_mod.reset_operator_sheet()
    yield
    server_mod.reset_walk_edits()
    server_mod.reset_operator_sheet()


def _desk_view(seats=()):
    lot = Lot(
        lot_id="BT-002", caption="trays", category="stoneware",
        fit_score=0.85, condition_penalty=0.1,
        comp=CompEstimate(100.0, 140.0, 3, Confidence.HIGH),
    )
    decisions = allocate([price_lot(lot)], 600.0, 40.0)
    return CycleView(
        cycle_id="2026-08-22",
        auction_date="Sat 2026-08-22",
        photos_ingested=462,
        queue=build_queue([], []),
        decisions=decisions,
        summary=summarize(decisions),
        budget_cap=600.0,
        auto_send_threshold=40.0,
        captions={"BT-002": "trays"},
        seats=list(seats),
        clerk_draft="TOTAL COMMITTED PROXY BIDS",
    )


def _walk_stage(html: str) -> str:
    start = html.find('data-stage="walk"')
    end = html.find('data-stage="questions"')
    assert start >= 0 and end > start
    return html[start:end]


def test_walk_stage_renders_return_thumbs_and_edge_controls():
    """A far-apart pair on one seat is a walk return the operator can rule
    on the Friday desk, without loading the 462-tile strip."""
    html = render_console(_desk_view([
        Seat(lot_id="BT-002", zone=Zone.UNKNOWN, walk_index=2,
             photo_ids=("BT-002", "BT-003", "BT-181")),
    ]))
    walk = _walk_stage(html)
    assert 'data-seq-a="2"' in walk
    assert 'data-seq-b="181"' in walk
    assert 'src="/walk/photo/2"' in walk
    assert 'src="/walk/photo/181"' in walk
    assert not re.search(r'src="https?://', walk)
    assert 'data-act="same"' in walk
    assert 'data-act="not-same"' in walk
    assert 'fetch("/api/walk/edge"' in html
    assert html.count('id="cycle-token"') == 1
    assert '<figure class="tile' not in html
    assert walk.count('src="/walk/photo/') == 2


def test_adjacent_members_are_not_walk_returns_on_the_desk():
    html = render_console(_desk_view([
        Seat(lot_id="BT-005", zone=Zone.UNKNOWN, walk_index=5,
             photo_ids=("BT-005", "BT-006", "BT-008")),
    ]))
    walk = _walk_stage(html)
    assert 'data-act="same"' not in walk
    assert 'src="/walk/photo/' not in walk


def test_friday_desk_stages_run_in_order(client):
    html = client.get("/").text
    walk = html.find('data-stage="walk"')
    questions = html.find('data-stage="questions"')
    envelope = html.find('data-stage="envelope"')
    clerk = html.find('data-stage="clerk"')
    assert 0 <= walk < questions < envelope < clerk


def test_grouping_and_scope_questions_sort_ahead_of_appetite(client):
    html = client.get("/").text
    kinds = re.findall(r'<div class="meta">(\w+) &middot;', html)
    if "lot_grouping" in kinds and "appetite" in kinds:
        assert kinds.index("lot_grouping") < kinds.index("appetite")
    if "scope" in kinds and "appetite" in kinds:
        assert kinds.index("scope") < kinds.index("appetite")


def test_clerk_draft_is_on_the_desk(client):
    html = client.get("/").text
    assert 'data-stage="clerk"' in html
    assert "TOTAL COMMITTED PROXY BIDS" in html or "absentee" in html.lower()


def test_one_operator_token_on_the_friday_desk(client):
    html = client.get("/").text
    assert html.count('id="cycle-token"') == 1
    assert 'href="/walk"' in html


def test_friday_desk_has_in_page_stage_nav(client):
    html = client.get("/").text
    for stage in ("walk", "questions", "envelope", "clerk"):
        assert f'href="#stage-{stage}"' in html
        assert f'id="stage-{stage}"' in html
    assert not re.search(r'href="https?://', html)


def test_friday_desk_lists_live_walk_returns_not_the_full_strip(client):
    html = client.get("/").text
    walk = _walk_stage(html)
    assert 'data-seq-a="2"' in walk
    assert 'data-seq-b="181"' in walk
    assert 'src="/walk/photo/2"' in walk
    assert 'src="/walk/photo/181"' in walk
    assert 'data-act="same"' in walk
    assert 'data-act="not-same"' in walk
    assert 'fetch("/api/walk/edge"' in html
    assert '<figure class="tile' not in html
    assert html.count('src="/walk/photo/') <= 120
    assert html.count('id="cycle-token"') == 1
    assert 'href="/walk"' in html


def test_walk_returns_stay_open_and_the_holding_strip_is_folded(client):
    walk = _walk_stage(client.get("/").text)
    assert "spatial observations unavailable" in walk
    assert 'id="unplaced"' in walk
    open_walk = walk.split("<details", 1)[0]
    assert 'class="walk-return"' in open_walk
    assert 'id="unplaced"' not in open_walk
    assert 'data-seq-a="2"' in open_walk


def test_envelope_opens_seated_lots_and_collapses_the_rest(client):
    html = client.get("/").text
    start = html.find('data-stage="envelope"')
    end = html.find('data-stage="clerk"')
    env = html[start:end]
    assert "<details" in env
    open_env = env.split("<details", 1)[0]
    assert 'data-allocated="1"' in open_env
    assert 'data-allocated="0"' not in open_env


def test_walk_return_uses_member_sequence_not_bt_id_parse():
    """Gallery photo ids are not BT-00N. Sequence lives on the member."""
    html = render_console(_desk_view([
        Seat(
            lot_id="lot-a", zone=Zone.UNKNOWN, walk_index=2,
            photo_ids=("p2", "p181"),
            members=(PhotoMember("p2", 2), PhotoMember("p181", 181)),
        ),
    ]))
    walk = _walk_stage(html)
    assert 'data-seq-a="2"' in walk
    assert 'data-seq-b="181"' in walk
    assert 'src="/walk/photo/2"' in walk
    assert 'src="/walk/photo/181"' in walk


def test_seated_envelope_card_shows_the_lot_photo():
    html = render_console(_desk_view([
        Seat(lot_id="BT-002", zone=Zone.UNKNOWN, walk_index=2,
             photo_ids=("BT-002", "BT-003", "BT-181")),
    ]))
    env = html[html.find('data-stage="envelope"'):html.find('data-stage="clerk"')]
    assert 'src="/walk/photo/2"' in env
    assert 'src="/walk/photo/181"' in env
    assert not re.search(r'src="https?://', env)
    assert env.count('src="/walk/photo/') == 2


def test_rejecting_a_desk_walk_return_drops_it_from_stage_one(client):
    before = _walk_stage(client.get("/").text)
    assert 'data-seq-a="2"' in before and 'data-seq-b="181"' in before
    response = client.post("/api/walk/edge", json={
        "seq_a": 2, "seq_b": 181, "status": "rejected",
    })
    assert response.status_code == 200
    after = _walk_stage(client.get("/").text)
    assert not re.search(r'data-seq-a="2"[^>]*data-seq-b="181"', after)
    _, _, _, _, sent, _, _ = get_aug22_state(sheet="sent")
    assert sent.allocated == 9
    assert sent.committed_max == 275.0
    assert sent.committed_all_in == 316.25


def test_sent_sheet_stays_frozen_on_the_friday_desk():
    _, _, _, _, sent, _, _ = get_aug22_state(sheet="sent")
    assert sent.allocated == 9
    assert sent.committed_max == 275.0
    assert sent.committed_all_in == 316.25
