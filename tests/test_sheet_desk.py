"""Envelope desk: operator in/out of the $600 sheet, human caps, sent frozen."""

import pytest
from starlette.testclient import TestClient

from src.server import app, get_aug22_state, reset_rule_store
from src import server as server_mod


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_desk():
    server_mod.reset_operator_sheet()
    yield
    server_mod.reset_operator_sheet()


def test_elect_drops_an_allocated_lot_from_the_full_envelope_only(client):
    server_mod.reset_operator_sheet()
    reset_rule_store()
    before = client.get("/api/lots").json()
    target = min(
        (row for row in before["lots"] if row["allocated"]),
        key=lambda row: row["all_in"] or 0,
    )
    response = client.post("/api/sheet/elect", json={
        "lot_id": target["lot_id"], "want": False,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["lot_id"] == target["lot_id"]
    assert data["after"]["decisions"][target["lot_id"]]["allocated"] is False
    assert data["after"]["committed_all_in"] < data["before"]["committed_all_in"]
    assert data["money_changed"] is True

    full = client.get("/api/lots").json()
    assert next(row for row in full["lots"] if row["lot_id"] == target["lot_id"])["allocated"] is False

    _, _, _, _, sent, _, _ = get_aug22_state(sheet="sent")
    assert sent.allocated == 9
    assert sent.committed_max == 275.0
    assert sent.committed_all_in == 316.25
    server_mod.reset_operator_sheet()


def test_elect_puts_a_dropped_lot_back_if_allocate_still_fits(client):
    server_mod.reset_operator_sheet()
    reset_rule_store()
    target = min(
        (row for row in client.get("/api/lots").json()["lots"] if row["allocated"]),
        key=lambda row: row["all_in"] or 0,
    )
    client.post("/api/sheet/elect", json={"lot_id": target["lot_id"], "want": False})
    response = client.post("/api/sheet/elect", json={
        "lot_id": target["lot_id"], "want": True,
    })
    assert response.status_code == 200
    assert response.json()["after"]["decisions"][target["lot_id"]]["allocated"] is True
    server_mod.reset_operator_sheet()


def test_elect_refuses_a_pending_lot_until_it_has_a_number(client):
    server_mod.reset_operator_sheet()
    reset_rule_store()
    pending = next(
        row for row in client.get("/api/lots").json()["lots"]
        if row["decision"] == "PENDING DEEP COMPS"
    )
    response = client.post("/api/sheet/elect", json={
        "lot_id": pending["lot_id"], "want": True,
    })
    assert response.status_code == 409
    assert "number" in response.json()["detail"].lower()
    server_mod.reset_operator_sheet()


def test_human_cap_prices_a_pending_lot_and_lets_allocate_consider_it(client):
    server_mod.reset_operator_sheet()
    reset_rule_store()
    pending = next(
        row for row in client.get("/api/lots").json()["lots"]
        if row["decision"] == "PENDING DEEP COMPS"
    )
    before = client.get("/api/lots").json()["summary"]["committed_all_in"]
    response = client.post("/api/sheet/price", json={
        "lot_id": pending["lot_id"], "max_bid": 5,
    })
    assert response.status_code == 200
    data = response.json()
    after_row = data["after"]["decisions"][pending["lot_id"]]
    assert after_row["max_bid"] == 5.0
    assert after_row["allocated"] is True
    assert data["money_changed"] is True
    assert client.get("/api/lots").json()["summary"]["committed_all_in"] > before
    _, _, _, _, sent, _, _ = get_aug22_state(sheet="sent")
    assert sent.allocated == 9
    assert sent.committed_all_in == 316.25
    server_mod.reset_operator_sheet()


def test_console_exposes_envelope_controls_and_answer_money_delta(client):
    server_mod.reset_operator_sheet()
    html = client.get("/").text
    assert 'data-act="elect"' in html
    assert 'data-act="price"' in html
    assert "money_changed" in html
    server_mod.reset_operator_sheet()
