"""Walk membership desk: operator same-lot / not-same edges on /walk."""

import pytest
from starlette.testclient import TestClient

from src.server import app, get_aug22_state
from src import server as server_mod


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_walk():
    server_mod.reset_walk_edits()
    yield
    server_mod.reset_walk_edits()


def _lot_of(seats):
    out = {}
    for seat in seats:
        for pid in seat.photo_ids:
            out[pid] = seat.lot_id
    return out


def test_rejecting_the_2_181_edge_splits_them_on_full_only(client):
    _, seats, *_ = get_aug22_state()
    before = _lot_of(seats)
    assert before.get("BT-002") == before.get("BT-181")

    response = client.post("/api/walk/edge", json={
        "seq_a": 2, "seq_b": 181, "status": "rejected",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "applied"
    assert data["after"]["same_lot"] is False

    _, seats, *_ = get_aug22_state()
    after = _lot_of(seats)
    assert after.get("BT-002") != after.get("BT-181")

    _, _, _, _, sent, _, _ = get_aug22_state(sheet="sent")
    assert sent.allocated == 9
    assert sent.committed_max == 275.0
    assert sent.committed_all_in == 316.25


def test_approving_the_rejected_2_181_edge_restores_the_lot(client):
    client.post("/api/walk/edge", json={
        "seq_a": 2, "seq_b": 181, "status": "rejected",
    })
    response = client.post("/api/walk/edge", json={
        "seq_a": 2, "seq_b": 181, "status": "approved",
    })
    assert response.status_code == 200
    assert response.json()["after"]["same_lot"] is True
    _, seats, *_ = get_aug22_state()
    lots = _lot_of(seats)
    assert lots.get("BT-002") == lots.get("BT-181")


def test_unknown_sequence_is_404(client):
    response = client.post("/api/walk/edge", json={
        "seq_a": 2, "seq_b": 99999, "status": "approved",
    })
    assert response.status_code == 404


def test_walk_page_exposes_membership_controls(client):
    html = client.get("/walk").text
    assert "data-seq=" in html
    assert 'data-act="same"' in html
    assert 'data-act="not-same"' in html
