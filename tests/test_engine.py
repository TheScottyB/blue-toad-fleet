"""
tests/test_engine.py — Unit tests for AppraisalEngine and live Vertex AI integration.
"""

import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from src.appraisal import StandingRule, QuestionKind, Confidence
from src.appraiser import AppraisalEngine
from src.server import app


def test_engine_init():
    engine = AppraisalEngine(project="test-proj", location="us-central1")
    assert engine.project == "test-proj"
    assert engine.location == "us-central1"


def test_parse_appraisal_to_domain():
    engine = AppraisalEngine()
    sample_data = {
        "lot_id": "BT-001",
        "category": "vintage toys",
        "identification": "Vintage Topps Baseball Cards (1960s)",
        "maker": "Topps Chewing Gum, Inc.",
        "period": "1960s",
        "condition_notes": ["Top loaders", "Corners sharp"],
        "condition_penalty": 0.15,
        "fit_score": 0.85,
        "confidence": "high",
        "value_magnitude_hint": 350.0,
        "questions": [
            {
                "kind": "condition",
                "prompt": "Can you check card corners on Mickey Mantle?",
                "wants_photo": True,
                "confidence_gap": 0.4,
            }
        ],
    }

    appraisal, questions = engine.parse_appraisal_to_domain(sample_data)
    assert appraisal.lot_id == "BT-001"
    assert appraisal.category == "vintage toys"
    assert appraisal.confidence == Confidence.HIGH
    assert appraisal.est_value_hint == 350.0
    assert len(questions) == 1
    assert questions[0].kind == QuestionKind.CONDITION
    assert questions[0].wants_photo is True


def test_api_appraise_endpoint(monkeypatch):
    client = TestClient(app)

    mock_resp = {
        "lot_id": "BT-041",
        "identification": "Edison cylinder phonograph rolls in canisters",
        "maker": "National Phonograph Co.",
        "period": "c. 1900-1910",
        "marks_observed": ["Edison Gold Moulded Record"],
        "category": "other",
        "condition_notes": ["Canisters show minor surface wear"],
        "condition_penalty": 0.10,
        "fit_score": 0.85,
        "confidence": "high",
        "value_magnitude_hint": 120.0,
        "questions": [
            {
                "kind": "condition",
                "prompt": "Any mold or cracks on bare cylinders?",
                "wants_photo": False,
                "confidence_gap": 0.3,
            }
        ],
        "model_used": "gemini-3.6-flash",
    }

    monkeypatch.setattr(
        "src.server.engine.appraise_lot",
        lambda lot_id, caption, category_hint, standing_rules: mock_resp,
    )

    r = client.post("/api/appraise", json={"lot_id": "BT-041", "caption": "Edison rolls"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["appraisal"]["lot_id"] == "BT-041"
    assert data["model_used"] == "gemini-3.6-flash"
    assert len(data["questions"]) == 1
