"""Google cost reporting and operator/agent audit trail on the Friday desk."""

import pytest
from starlette.testclient import TestClient

from src.server import app, get_aug22_state
from src import server as server_mod


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_audit():
    server_mod.reset_audit()
    server_mod.reset_operator_sheet()
    server_mod.reset_walk_edits()
    yield
    server_mod.reset_audit()
    server_mod.reset_operator_sheet()
    server_mod.reset_walk_edits()


def test_audit_api_starts_empty_and_reports_no_google_calls(client):
    data = client.get("/api/audit").json()
    assert data["google"]["process"]["cost_status"] == "no_calls"
    assert data["google"]["process"]["measured_cost_usd"] is None
    assert data["google"]["cycle_artifact"]["cost_status"] == "no_calls"
    assert data["events"] == []


def test_walk_ruling_is_on_the_audit_trail(client):
    response = client.post("/api/walk/edge", json={
        "seq_a": 2, "seq_b": 181, "status": "rejected",
    })
    assert response.status_code == 200
    events = client.get("/api/audit").json()["events"]
    assert len(events) == 1
    event = events[0]
    assert event["actor"] == "operator"
    assert event["kind"] == "walk_edge"
    assert event["detail"]["seq_a"] == 2
    assert event["detail"]["seq_b"] == 181
    assert event["detail"]["status"] == "rejected"
    assert event["measured_cost_usd"] is None


def test_envelope_drop_is_on_the_audit_trail(client):
    target = max(
        (row for row in client.get("/api/lots").json()["lots"] if row["allocated"]),
        key=lambda row: row["all_in"] or 0,
    )
    response = client.post("/api/sheet/elect", json={
        "lot_id": target["lot_id"], "want": False,
    })
    assert response.status_code == 200
    events = client.get("/api/audit").json()["events"]
    assert any(
        e["kind"] == "sheet_elect" and e["detail"]["lot_id"] == target["lot_id"]
        for e in events
    )


def test_friday_desk_shows_google_spend_and_audit(client):
    html = client.get("/").text
    assert "Google spend" in html
    assert "no_calls" in html
    client.post("/api/walk/edge", json={
        "seq_a": 2, "seq_b": 181, "status": "rejected",
    })
    html = client.get("/").text
    assert "walk_edge" in html
    _, _, _, _, sent, _, _ = get_aug22_state(sheet="sent")
    assert sent.allocated == 9
    assert sent.committed_max == 275.0
    assert sent.committed_all_in == 316.25
