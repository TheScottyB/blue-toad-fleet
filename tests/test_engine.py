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


class TestCacheReporting:
    """
    The pipeline printed "(cached: True)" after a --live run because it was
    reporting whether the cache *file existed*, not whether it had been used.
    A run that quietly reused stale results while claiming to be live is how
    you spend an afternoon comparing a file against itself.
    """

    def test_a_populated_cache_is_used_when_not_forcing(self, tmp_path):
        cache = tmp_path / "appraisal_results.json"
        cache.write_text('[{"lot_id": "BT-001"}]')
        assert AppraisalEngine.will_use_cache(cache, force_refresh=False)

    def test_forcing_a_refresh_bypasses_a_populated_cache(self, tmp_path):
        cache = tmp_path / "appraisal_results.json"
        cache.write_text('[{"lot_id": "BT-001"}]')
        assert not AppraisalEngine.will_use_cache(cache, force_refresh=True)

    def test_an_empty_cache_is_not_usable(self):
        """An empty list is a file, not results; the batch falls through to live."""
        import tempfile, pathlib as _pl
        with tempfile.TemporaryDirectory() as d:
            cache = _pl.Path(d) / "appraisal_results.json"
            cache.write_text("[]")
            assert not AppraisalEngine.will_use_cache(cache, force_refresh=False)

    def test_an_unparseable_cache_is_not_usable(self, tmp_path):
        cache = tmp_path / "appraisal_results.json"
        cache.write_text("{ not json")
        assert not AppraisalEngine.will_use_cache(cache, force_refresh=False)

    def test_a_missing_cache_is_never_used(self, tmp_path):
        assert not AppraisalEngine.will_use_cache(tmp_path / "nope.json", force_refresh=False)

    def test_no_cache_path_is_never_used(self):
        assert not AppraisalEngine.will_use_cache(None, force_refresh=False)

    def test_the_batch_serves_the_cache_it_says_it_will(self, tmp_path):
        """The reporting helper and the batch must agree, or the print lies again."""
        cache = tmp_path / "appraisal_results.json"
        cache.write_text('[{"lot_id": "BT-001", "questions": []}]')

        engine = AppraisalEngine()
        engine._client = None  # no credentials: only the cache path can succeed

        assert AppraisalEngine.will_use_cache(cache, force_refresh=False)
        served = engine.run_appraisal_batch(candidates=[], cache_path=cache)
        assert served == [{"lot_id": "BT-001", "questions": []}]


class TestTheCacheMustCoverWhatWasAsked:
    """
    will_use_cache asked "is this a non-empty list" and nothing more. When the
    candidate set grew from 214 to 228 the cache answered yes and 14 lots were
    never appraised — including one carrying a $25 bid on the sheet. Nothing
    errored, the run reported success, and the count was in the log where nobody
    was subtracting.
    """

    def test_a_cache_missing_requested_lots_is_not_used(self, tmp_path):
        cache = tmp_path / "appraisal_results.json"
        cache.write_text('[{"lot_id": "BT-001"}]')
        assert not AppraisalEngine.will_use_cache(
            cache, force_refresh=False, required_ids={"BT-001", "BT-002"})

    def test_a_cache_covering_every_requested_lot_is_used(self, tmp_path):
        cache = tmp_path / "appraisal_results.json"
        cache.write_text('[{"lot_id": "BT-001"}, {"lot_id": "BT-002"}]')
        assert AppraisalEngine.will_use_cache(
            cache, force_refresh=False, required_ids={"BT-001", "BT-002"})

    def test_extra_lots_in_the_cache_are_harmless(self, tmp_path):
        cache = tmp_path / "appraisal_results.json"
        cache.write_text('[{"lot_id": "BT-001"}, {"lot_id": "BT-999"}]')
        assert AppraisalEngine.will_use_cache(
            cache, force_refresh=False, required_ids={"BT-001"})

    def test_with_no_requirement_stated_the_old_behaviour_stands(self, tmp_path):
        cache = tmp_path / "appraisal_results.json"
        cache.write_text('[{"lot_id": "BT-001"}]')
        assert AppraisalEngine.will_use_cache(cache, force_refresh=False)

    def test_a_cache_missing_required_fields_is_not_used(self, tmp_path):
        """462 triage rows predating zone/surface would otherwise serve as a hit
        and every photo would land Zone.UNKNOWN with nothing erroring."""
        cache = tmp_path / "triage_results.json"
        cache.write_text('[{"photo_id": "fp1", "is_lot": true}]')
        assert not AppraisalEngine.will_use_cache(
            cache, force_refresh=False, required_fields={"zone", "surface_signature"})

    def test_a_cache_with_required_fields_is_used(self, tmp_path):
        cache = tmp_path / "triage_results.json"
        cache.write_text(
            '[{"photo_id": "fp1", "zone": "center_island_1", '
            '"surface_signature": "blue_vinyl"}]'
        )
        assert AppraisalEngine.will_use_cache(
            cache, force_refresh=False, required_fields={"zone", "surface_signature"})

    def test_the_batch_refuses_a_short_cache_rather_than_serving_it(self, monkeypatch, tmp_path):
        """
        A partial cache must not look like a completed run. With no credentials
        the batch has only the cache to fall back on, so a short one has to
        raise rather than quietly return fewer lots than were asked for.
        """
        cache = tmp_path / "appraisal_results.json"
        cache.write_text('[{"lot_id": "BT-001", "questions": []}]')
        monkeypatch.setattr(AppraisalEngine, "client", property(lambda self: None))
        with pytest.raises(RuntimeError, match="2 requested"):
            AppraisalEngine().run_appraisal_batch(
                candidates=[{"lot_id": "BT-001", "local_path": ""},
                            {"lot_id": "BT-002", "local_path": ""}],
                cache_path=cache)


def test_appraisal_error_stub_includes_container_fields():
    """The except stub must satisfy APPRAISAL_SCHEMA required keys."""
    engine = AppraisalEngine()
    engine._client = object()

    def boom(*args, **kwargs):
        raise RuntimeError("vertex down")

    engine.appraise_lot = boom
    results = engine.run_appraisal_batch(
        candidates=[{"lot_id": "BT-999", "caption": "x"}],
        force_refresh=True,
    )
    stub = results[0]
    assert stub["lot_id"] == "BT-999"
    assert stub["is_container"] is False
    assert stub["contents"] == []

