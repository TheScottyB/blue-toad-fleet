"""
tests/test_engine.py — Unit tests for AppraisalEngine and live Vertex AI integration.
"""

import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from src.appraisal import StandingRule, QuestionKind, Confidence
from src.appraiser import AppraisalEngine
from src.appraiser.images import ImageTooSmall, is_appraisal_grade
from src.server import app
from tests.test_images import drop_is_cached, webp_of


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


@drop_is_cached
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
        lambda lot_id, caption, image_bytes, category_hint, standing_rules: mock_resp,
    )

    r = client.post("/api/appraise", json={"lot_id": "BT-041", "caption": "Edison rolls"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["appraisal"]["lot_id"] == "BT-041"
    assert data["model_used"] == "gemini-3.6-flash"
    assert len(data["questions"]) == 1


class TestTheEngineRefusesToAppraiseBlind:
    """
    The choke point. Every path to Vertex goes through appraise_lot, so the size
    check goes there — not in each caller, where the next caller forgets it.
    """

    def test_refuses_a_gallery_thumbnail(self):
        engine = AppraisalEngine()
        with pytest.raises(ImageTooSmall) as exc:
            engine.appraise_lot(
                lot_id="BT-002", caption="costume jewelry trays",
                image_bytes=webp_of(140, 105),
            )
        assert "140x105" in str(exc.value)

    def test_refuses_when_handed_no_photo_at_all(self):
        engine = AppraisalEngine()
        with pytest.raises(ImageTooSmall):
            engine.appraise_lot(lot_id="BT-002", caption="costume jewelry trays")

    def test_the_size_check_runs_before_the_client_check(self):
        """
        A thumbnail must fail as a thumbnail, not as 'no Vertex credentials'.
        Getting this backwards is how the defect stayed invisible offline.
        """
        engine = AppraisalEngine(project="no-such-project")
        engine._client = None
        with pytest.raises(ImageTooSmall):
            engine.appraise_lot(lot_id="BT-002", caption="x", image_bytes=webp_of(140, 105))


@drop_is_cached
class TestTheAppraiseEndpointSuppliesAPhoto:
    def test_it_passes_appraisal_grade_bytes_to_the_engine(self, monkeypatch):
        seen = {}

        def capture(lot_id, caption, image_bytes=None, category_hint=None, standing_rules=None):
            seen["bytes"] = image_bytes
            return {"lot_id": lot_id, "identification": "x", "category": "jewelry",
                    "confidence": "high", "value_magnitude_hint": 10.0, "questions": [],
                    "model_used": "gemini-3.6-flash"}

        monkeypatch.setattr("src.server.engine.appraise_lot", capture)
        r = TestClient(app).post("/api/appraise",
                                 json={"lot_id": "BT-002", "caption": "jewelry trays"})

        assert r.status_code == 200
        assert is_appraisal_grade(seen["bytes"]), (
            "the endpoint appraised without an appraisal-grade photo"
        )
