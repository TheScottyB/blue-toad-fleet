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


def test_devpost_skill_gathers_media_and_fills_the_form():
    """The skill must capture shots, render the diagram, and load DEVPOST.md onto the live form."""
    skill = (ROOT / ".grok/skills/devpost-submission/SKILL.md").read_text()
    fill = (ROOT / ".grok/skills/devpost-submission/references/fill-form.md").read_text()
    combined = skill + "\n" + fill
    assert "capture_screenshots.mjs" in combined
    assert "capture_raw_gallery.mjs" in combined
    assert "generate_architecture_diagram.py" in combined
    assert "docs/architecture_diagram.png" in combined
    assert "project_details/edit" in combined
    assert "additional-info/edit" in combined
    assert "9222" in combined
    assert "Save" in fill
    assert "Submit" in fill
    recipe = skill.lower()
    assert "fill" in recipe or "load" in recipe
    assert "login wall, stop" not in skill.lower()


def test_blog_stays_inside_the_claim_boundary():
    blog = (ROOT / "docs/blog/index.html").read_text()
    social = (ROOT / "docs/blog/SOCIAL_POST.md").read_text()
    current = sheet()
    assert "All Things Agentic Hackathon" in blog
    assert "I created this piece of content for the purposes of entering" in blog
    assert "Gemma 4" in blog
    assert "pending deep comps" in blog
    assert "google-genai" in blog
    assert "puzzle loop" in blog
    assert "462 photos" in blog
    assert f"{current.allocated} lots" in blog
    assert "$275.00" in blog and "$316.25" in blog
    assert "450 Photos" not in blog
    assert "POLE BARN SHOWROOM TOPOLOGY" not in blog.upper()
    assert "video predates" not in blog
    assert "select_challenge" in blog and "not wired" in blog
    assert "Sending a bid is a human action" in blog
    assert "#AllThingsAgentic" in blog and "#AllThingsAgenticHackathon" in blog
    assert "thescottyb.github.io/blue-toad-fleet/blog" in social
    assert "pole barn" not in social.lower()
    extra = (ROOT / "docs/DEVPOST.md").read_text().split("## Additional Info", 1)[-1]
    assert "https://thescottyb.github.io/blue-toad-fleet/blog/" in extra


def test_todo_names_the_devpost_deadline_as_7pm_cdt():
    """Devpost labels 5:00pm PDT; the operator-local page shows 7:00pm CDT."""
    todo = (ROOT / "docs/TODO.md").read_text()
    assert "7:00pm CDT" in todo
    assert "Monday Aug 31, 2026" in todo
    assert "Sunday" not in todo.split("Submission deadline", 1)[-1].split("\n", 2)[0]
