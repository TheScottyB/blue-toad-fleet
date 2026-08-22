"""
The code's sheet against the sheet Blue Toad actually received.

`data/aug22_absentee_bid_email_REVISED.txt` is the artifact that went to the
auctioneer on 2026-08-21. It is the authoritative record of what the operator
authorised, and nothing tied the code to it — which is exactly how BT-087 came
to be capped at $25.00 in `OPERATOR_APPROVED` while the sent sheet reads
"MAX $15.00 (revised down from $25.00)". `apply_operator_cap` assigns the cap
unconditionally rather than clamping down, so that $10 was going out ABOVE
authorisation, on the operator's own cash, with nothing failing.

A number in a table that disagrees with a number in a sent email is not a style
question. These tests are the tie.
"""

import re
from pathlib import Path

import pytest

SENT = Path("data/aug22_absentee_bid_email_REVISED.txt")


@pytest.fixture(scope="module")
def sent():
    if not SENT.is_file():
        pytest.skip("no sent sheet on disk")
    return SENT.read_text()


@pytest.fixture(scope="module")
def sheet():
    from src.server import get_aug22_state
    from src.bidmath import summarize
    _, _, _, decisions, _, _, _ = get_aug22_state()
    return [d for d in decisions if d.allocated], summarize(decisions)


def test_the_same_lots_are_bid(sent, sheet):
    decisions, _ = sheet
    assert {d.lot_id for d in decisions} == set(re.findall(r"\[(BT-\d{3})\]", sent))


def test_every_max_bid_matches_what_was_authorised(sent, sheet):
    """Per-unit maxes, lot by lot. A cap in the table that exceeds the sent
    sheet is a bid going out above authorisation."""
    decisions, _ = sheet
    authorised = {m.group(1): float(m.group(2))
                  for m in re.finditer(r"\[(BT-\d{3})\][\s\S]{0,500}?MAX\s+\$([\d,.]+)", sent)}
    for d in decisions:
        want = authorised.get(d.lot_id)
        if want is not None:
            assert d.max_bid == pytest.approx(want), (
                f"{d.lot_id}: code bids ${d.max_bid:.2f}, sent sheet "
                f"authorised ${want:.2f}")


def test_the_totals_reconcile_to_the_sent_footer(sent, sheet):
    _, summary = sheet
    m = re.search(r"TOTAL COMMITTED PROXY BIDS:\s*\$([\d,]+\.\d{2})\s*"
                  r"\(\$([\d,]+\.\d{2})\s*all-in", sent)
    assert m, "sent sheet has no total footer"
    committed, all_in = (float(g.replace(",", "")) for g in m.groups())
    assert summary.committed_max == pytest.approx(committed)
    assert summary.committed_all_in == pytest.approx(all_in)


def test_the_times_the_money_lot_commits_what_the_sent_sheet_says(sent, sheet):
    """BT-002's three trays, the ruling this whole lane exists to carry."""
    decisions, _ = sheet
    d = next((x for x in decisions if x.lot_id == "BT-002"), None)
    assert d is not None
    assert "x 3 TRAYS" in sent and "$75.00 TOTAL" in sent
    assert d.committed_max == pytest.approx(75.00)


def test_a_lot_the_sent_sheet_dropped_is_not_bid(sheet):
    """BT-181 is a close-up of trays already inside BT-002. The sent sheet
    dropped it; the code kept bidding it until eb8bd7a."""
    decisions, _ = sheet
    assert "BT-181" not in {d.lot_id for d in decisions}
