"""The release gate reports blockers without mutating an external system."""

from pathlib import Path

from scripts.build_release_report import _facts_blockers, build_report


def _junit(path: Path) -> Path:
    path.write_text(
        '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="1"/>'
        '</testsuites>'
    )
    return path


def test_facts_blockers_require_release_eligibility_and_clean_tree():
    assert _facts_blockers({
        "publication": {"release_eligible": True},
        "git": {"dirty": False},
    }) == []
    blockers = _facts_blockers({
        "publication": {
            "release_eligible": False,
            "reason": "allocated lots have unresolved questions",
            "blocking_lot_ids": ["BT-002"],
        },
        "git": {"dirty": True},
    })
    assert any("unresolved questions" in item for item in blockers)
    assert any("BT-002" in item for item in blockers)
    assert any("dirty working tree" in item for item in blockers)


def test_current_historical_fixture_produces_a_written_blocked_report(tmp_path):
    output, blockers = build_report(_junit(tmp_path / "pytest.xml"), tmp_path / "RELEASE.md")
    text = output.read_text()
    assert blockers
    assert "**Status:** NOT READY" in text
    assert "Collected: 3" in text
    assert "Canonical cycle facts" in text
    assert "does not deploy" in text
