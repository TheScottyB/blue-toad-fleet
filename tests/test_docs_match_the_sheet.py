"""
The submission's numbers against the sheet they describe.

A judging panel opened three artifacts in sequence and got three answers: the
README said 10 lots / $260.00 / $299.00, the video script said 12 / $335.00 /
$385.25, and the emails said 9 / $275.00 / $316.25. None were lies — each was a
correct snapshot of a different hour of 2026-08-20/21, frozen into a document
while the code kept moving.

Re-typing today's figures fixes today and re-breaks on the next commit. These
tests are the tie, in the same shape as test_sheet_matches_what_was_sent.py:
a number quoted in a submission document has to be a number the code produces.

Deliberately NOT covered: the narrated figures in VIDEO_SCRIPT.md. That file
transcribes a recording; asserting it matches the current sheet would demand
editing a document to disagree with the video it describes. Its recording note
carries both sets and says which is which.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DEVPOST = ROOT / "docs/DEVPOST.md"


def sheet():
    from src.bidmath import summarize
    from src.server import get_aug22_state
    _, _, _, decisions, _, _, _ = get_aug22_state()
    return summarize(decisions)


def test_readme_labels_local_money_as_sealed_and_distinct_from_sent():
    """The 2026-08-29 reseal made the fixture provenance-bearing, so the old
    'not publishable / blocked' labels became false. The contract now: the
    README's figures derive from the live sheet, name the seal, and keep the
    sent sheet unmistakably separate from the full-coverage computation."""
    current = sheet()
    text = README.read_text()
    assert "Historical August fixture reconciliation" in text
    assert f"**{current.allocated} allocated bids (${current.committed_max:,.2f} max)**" in text
    assert f"**${current.committed_all_in:,.2f}** all-in" in text
    assert "provenance-sealed" in text
    assert "only artifact ever sent" in " ".join(text.split())


def test_devpost_labels_local_money_as_sealed_and_distinct_from_sent():
    current = sheet()
    text = DEVPOST.read_text()
    assert "Historical August fixture, provenance-sealed" in text
    assert f"**{current.allocated} allocations" in text
    assert f"${current.committed_max:,.2f} max / ${current.committed_all_in:,.2f} all-in" in text
    assert "seat" in text and "first by design" in text


def test_judged_copy_does_not_freeze_test_counts():
    combined = README.read_text() + "\n" + DEVPOST.read_text()
    assert "Unit%20Tests-release--gated" in combined
    for stale in ("298 passing", "565 passing", "730 unit tests", "737 collected"):
        assert stale not in combined.lower()


def test_devpost_does_not_describe_grouping_as_a_funnel():
    text = DEVPOST.read_text().lower()
    assert "narrows 462" not in text
    assert "11,900" not in text
    assert "puzzle loop" in text


def test_devpost_lists_gemma_among_google_models():
    text = DEVPOST.read_text()
    assert "Gemma 4" in text
    assert "gemini-embedding-2" in text.lower() or "Gemini Embedding 2" in text


def test_devpost_additional_info_names_the_sdk_and_cloud_services():
    text = DEVPOST.read_text()
    extra = text.split("## Additional Info", 1)[-1]
    assert "google-genai" in extra
    assert "not ADK" in extra
    assert "Cloud Run" in extra
    assert "Firestore" in extra
    assert "Pub/Sub" in extra
    assert "Not Cloud SQL" in extra
    assert "Not GKE" in extra
    assert "Gemma 4" in extra
    assert "make test" in extra


def test_readme_does_not_label_the_checked_in_video_stale():
    text = README.read_text()
    assert "it is not current submission evidence" not in text
    assert "2026-08-20" not in text.split("Demo Video", 1)[-1].split("## Try it", 1)[0]
