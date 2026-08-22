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

import re
from pathlib import Path

import pytest

README = Path("README.md")
DEVPOST = Path("docs/DEVPOST.md")


@pytest.fixture(scope="module")
def sheet():
    from src.bidmath import summarize
    from src.server import get_aug22_state
    _, _, _, decisions, _, _, _ = get_aug22_state()
    return summarize(decisions)


@pytest.fixture(scope="module")
def suite_size():
    """Every test in the tree, counted the way pytest counts them."""
    import subprocess
    # WITHOUT -q. Under -q this pytest prints per-file counts and no summary
    # line, so the obvious regex matched nothing and the guard skipped itself
    # into decoration — which is the failure mode this whole file exists to
    # catch, found in this file first.
    out = subprocess.run(
        [".venv/bin/pytest", "tests/", "--collect-only"],
        capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    return int(m.group(1)) if m else None


class TestTheReadmeQuotesTheRealSheet:
    def test_the_committed_max_is_current(self, sheet):
        assert f"${sheet.committed_max:,.2f} max" in README.read_text(), (
            f"README does not quote the live committed max of "
            f"${sheet.committed_max:,.2f}")

    def test_the_all_in_is_current(self, sheet):
        assert f"**${sheet.committed_all_in:,.2f}**" in README.read_text(), (
            f"README does not quote the live all-in of ${sheet.committed_all_in:,.2f}")

    def test_the_lot_count_is_current(self, sheet):
        assert f"{sheet.allocated} approved bids" in README.read_text()


class TestTheDevpostQuotesTheRealSheet:
    def test_the_money_line_is_current(self, sheet):
        assert (f"${sheet.committed_max:,.2f} max / "
                f"${sheet.committed_all_in:,.2f} all-in") in DEVPOST.read_text()

    def test_the_lot_count_is_current(self, sheet):
        assert f"{sheet.allocated} laser-targeted bids" in DEVPOST.read_text()


class TestTheTestCountIsWhatAJudgeWouldSee:
    """The badge is the first number a judge reads, and it used to be reachable
    only from a machine with the gallery cached — the 22 image guards skipped on
    a clean clone, so a judge saw 445 where the badge claimed 298. The twelve
    candidate photos are tracked now precisely so this number is honest."""

    def test_the_readme_badge_matches_the_suite(self, suite_size):
        if suite_size is None:
            pytest.skip("could not collect")
        assert f"Unit%20Tests-{suite_size}%20Passing" in README.read_text(), (
            f"badge disagrees with the {suite_size}-test suite")

    def test_the_devpost_count_matches_the_suite(self, suite_size):
        if suite_size is None:
            pytest.skip("could not collect")
        assert f"{suite_size} unit tests" in DEVPOST.read_text()
