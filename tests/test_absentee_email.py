"""
The absentee email is the only artifact with real money behind it.

A human clerk at Blue Toad reads it and matches each line to a physical lot on
a Saturday morning. Blue Toad's published terms ask for "a brief description of
the item(s), your start bid, and your max bid" — so the description has to
survive intact. A line reading "Cardboard multi-row storage box containing bulk"
is a bid on an unidentified object.
"""

import re
from pathlib import Path

import pytest

EMAIL = Path("data/aug22_absentee_bid_email.txt")

pytestmark = pytest.mark.skipif(
    not EMAIL.exists(), reason="no compiled absentee email; run scripts/run_vertex_pipeline.py"
)


@pytest.fixture(scope="module")
def email() -> str:
    return EMAIL.read_text()


def bid_lines(text: str) -> list[str]:
    """Lines carrying a MAX figure — one per bid, whatever the layout."""
    return [ln for ln in text.splitlines() if re.search(r"MAX\s*\$|\$\s*\d+\.\d{2}\s*$", ln)]


class TestDescriptionsSurvive:
    def test_every_bid_carries_its_complete_appraised_description(self, email):
        """
        The real invariant: whatever the appraiser concluded about a lot must
        reach the clerk whole. Anchoring on line endings misses this, because
        the truncation sits mid-line with the columns padded around it.
        """
        import json
        appraisals = {
            lot["lot_id"]: " ".join(lot["identification"].split())
            for lot in json.loads(
                Path("data/aug22_gallery_4160518/appraisal_results.json").read_text())
        }
        flat = " ".join(email.split())
        missing = [
            lot_id for lot_id in re.findall(r"\bBT-\d{3}\b", email)
            if lot_id in appraisals and appraisals[lot_id] not in flat
        ]
        assert not missing, (
            "description truncated before it reached the clerk for: "
            + ", ".join(sorted(set(missing)))
        )

    def test_every_bid_names_its_lot_id(self, email):
        ids = set(re.findall(r"\bBT-\d{3}\b", email))
        assert len(ids) >= 12, f"only {len(ids)} lot id(s) in the email"

    def test_the_full_identification_text_is_present(self, email):
        """Spot-check the two lots that were previously cut off."""
        assert "sports trading cards" in email, "BT-016 lost what is in the box"
        assert "Century of Progress" in email, "BT-235 lost the fair name"


class TestTheCommercialTerms:
    def test_addressed_to_the_letterhead_address(self, email):
        assert "info@bluetoadauctions.com" in email

    def test_states_the_fifteen_percent_absentee_fee(self, email):
        assert "15%" in email

    def test_totals_reconcile_to_the_listed_bids(self, email):
        maxes = [float(m) for m in re.findall(r"MAX\s*\$\s*([\d,]+\.\d{2})", email)]
        if not maxes:  # fixed-width layout: last figure on each bid line
            maxes = [float(re.findall(r"\$\s*([\d,]+\.\d{2})", ln)[-1].replace(",", ""))
                     for ln in bid_lines(email) if re.findall(r"\$\s*([\d,]+\.\d{2})", ln)]
        stated = re.search(r"TOTAL COMMITTED PROXY BIDS:\s*\$([\d,]+\.\d{2})", email)
        assert stated, "no stated total"
        assert abs(sum(maxes) - float(stated.group(1).replace(",", ""))) < 0.01, (
            f"listed bids sum to {sum(maxes):.2f}, email claims {stated.group(1)}"
        )

    def test_the_all_in_figure_is_the_total_plus_fifteen_percent(self, email):
        m = re.search(r"\$([\d,]+\.\d{2})\s*\(\$([\d,]+\.\d{2})\s*all-in", email)
        assert m, "no total / all-in pair"
        total, all_in = (float(g.replace(",", "")) for g in m.groups())
        assert abs(all_in - total * 1.15) < 0.01

    def test_every_bid_is_a_five_dollar_increment(self, email):
        for ln in bid_lines(email):
            for fig in re.findall(r"\$\s*([\d,]+\.\d{2})", ln):
                v = float(fig.replace(",", ""))
                assert v % 5 == 0, f"{v} is not a $5 increment: {ln.strip()}"
