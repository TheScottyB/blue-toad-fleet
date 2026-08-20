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


class TestTheModelReachesTheQueue:
    """
    Nothing caught it when the Vertex questions were unhooked from build_queue —
    the console rendered three hand-written prompts, all of them absorbed by
    standing rules, and reported an empty queue as if the cycle were clean.
    A console that cannot show what the model asked is a console showing a demo.
    """

    def test_model_emitted_questions_reach_the_console_queue(self):
        from src.server import get_aug22_state

        _, _, _, _, _, queue, _ = get_aug22_state()
        surfaced = queue.asked + [q for q, _ in queue.auto_answered] + queue.dropped

        hand_written = {
            "sports memorabilia", "dinnerware / pottery", "vintage tools",
        }
        from_model = [q for q in surfaced if q.category not in hand_written]

        assert from_model, (
            "the queue contains only the hard-coded domain questions; "
            "nothing the appraiser emitted reached it"
        )

    def test_the_queue_is_not_empty_while_lots_carry_questions(self):
        import json
        from pathlib import Path
        from src.server import get_aug22_state

        cache = Path("data/aug22_gallery_4160518/appraisal_results.json")
        emitted = sum(len(lot.get("questions", []))
                      for lot in json.loads(cache.read_text()))
        assert emitted, "fixture has no questions; this test proves nothing"

        _, _, _, _, _, queue, _ = get_aug22_state()
        assert queue.asked, (
            f"the appraiser emitted {emitted} question(s) and the console asks none"
        )
