import json

import pytest

from scripts.collect_submission_facts import (
    _decision_facts,
    _publication_facts,
    release_blocking_lots,
)
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


def test_release_blocks_only_on_askable_questions():
    """The queue's contract (src/appraisal/__init__.py:214-216): deferred and
    dropped ship flagged low-confidence — "Neither blocks the sheet." Blocking
    E1 on them made release unreachable by operator action: 44 of 46 allocated
    lots carried only desk-unanswerable or never-asked questions (2026-08-29,
    operator-ruled).

    The asked set itself is kept-lot-first by design (build_queue seats the
    owner's committed-money questions before impact ranking, 3fa541e chain) —
    this intersection is deliberately seating-agnostic: whatever the queue
    asked, only asked-and-allocated blocks. The gate consumes the SEALED
    state's queue section, never a live queue rebuild, so the blocker set
    cannot drift with whichever rule store an environment happens to load."""
    queue = {
        "asked": {"lot_ids": ["BT-165", "BT-385", "BT-999"]},
        "deferred": {"lot_ids": ["BT-001", "BT-165", "BT-777"]},
        "dropped": {"lot_ids": ["BT-002", "BT-888"]},
        "unresolved_lot_ids": [
            "BT-001", "BT-002", "BT-165", "BT-385", "BT-777", "BT-888", "BT-999",
        ],
    }
    allocated = ["BT-001", "BT-002", "BT-165", "BT-385"]
    blocking, flagged_deferred, flagged_dropped = release_blocking_lots(
        queue, allocated,
    )
    assert blocking == ["BT-165", "BT-385"]
    # The dropped-vs-deferred distinction matters to the operator and survives.
    assert flagged_deferred == ["BT-001", "BT-165"]
    assert flagged_dropped == ["BT-002"]


def test_release_blocking_tolerates_missing_queue_sections():
    assert release_blocking_lots({}, ["BT-001"]) == ([], [], [])
