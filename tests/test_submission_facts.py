import json

import pytest

from scripts.collect_submission_facts import _decision_facts, _publication_facts
from scripts.video_common import VideoBuildError


def _state():
    return {
        "decisions": [
            {
                "lot_id": "BT-001", "allocated": True, "speculative": False,
                "committed_max": 25.0, "committed_all_in": 28.75,
                "comp": {"low": 60.0, "high": 80.0,
                         "provenance": "grounded_search"},
            },
            {
                "lot_id": "BT-002", "allocated": False, "speculative": False,
                "committed_max": 10.0, "committed_all_in": 11.5,
                "comp": {"low": 20.0, "high": 30.0,
                         "provenance": "grounded_search"},
            },
        ],
    }


def test_resale_and_return_multiple_come_from_allocated_decisions_once():
    money, ids = _decision_facts(_state())
    assert ids == ["BT-001"]
    assert money == {
        "committed_max": 25.0,
        "committed_all_in": 28.75,
        "estimated_gross_resale_low": 60.0,
        "estimated_gross_resale_high": 80.0,
        "gross_resale_multiple_low": 2.09,
        "gross_resale_multiple_high": 2.78,
    }


def test_allocated_lot_without_comp_provenance_is_refused():
    state = _state()
    state["decisions"][0]["comp"]["provenance"] = None
    with pytest.raises(VideoBuildError, match="invalid resale provenance"):
        _decision_facts(state)


def test_missing_sealed_manifest_is_not_release_eligible(tmp_path):
    gallery = tmp_path / "manifest.json"
    gallery.write_text(json.dumps({"photos": []}))
    result = _publication_facts(
        {"sources": {"gallery_manifest": str(gallery)}},
        {"gallery_manifest": gallery},
    )
    assert result["status"] == "unpublished_local_snapshot"
    assert result["release_eligible"] is False
