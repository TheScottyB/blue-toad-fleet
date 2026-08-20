"""
Unit tests for Blue Toad Fleet FastAPI server & endpoints.
"""

import pytest
from starlette.testclient import TestClient
from src.server import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health_endpoints(client):
    r1 = client.get("/health")
    assert r1.status_code == 200
    assert r1.json()["status"] == "healthy"
    assert r1.json()["service"] == "blue-toad-fleet"

    r2 = client.get("/healthz")
    assert r2.status_code == 200
    assert r2.json()["status"] == "healthy"

def test_root_console_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Blue Toad Fleet" in r.text
    assert "Pole Barn Showroom Topology" in r.text
    assert "Curator's Negotiation" in r.text

def test_api_lots_summary_and_bids(client):
    r = client.get("/api/lots")
    assert r.status_code == 200
    data = r.json()
    summary = data["summary"]
    assert summary["committed_max"] == 335.0
    assert summary["committed_all_in"] == 385.25
    assert summary["allocated"] == 12
    assert len(data["lots"]) > 0

def test_api_questions(client):
    r = client.get("/api/questions")
    assert r.status_code == 200
    data = r.json()
    assert "asked" in data
    assert "auto_answered_from_memory" in data
    assert len(data["auto_answered_from_memory"]) >= 3

def test_api_answer_promotion(client):
    payload = {
        "kind": "mark",
        "category": "stoneware",
        "answer": "Only bid if wing mark is clearly visible"
    }
    r = client.post("/api/answer", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "learned"
    assert data["rule"]["category"] == "stoneware"

def test_api_answer_invalid(client):
    r = client.post("/api/answer", json={"kind": "invalid_kind"})
    assert r.status_code in (400, 422)

def test_api_email_draft(client):
    r = client.get("/api/email")
    assert r.status_code == 200
    text = r.text
    assert "info@bluetoadauctions.com" in text
    assert "$335.00" in text or "Richmond General" in text
