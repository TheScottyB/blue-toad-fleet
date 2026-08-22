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

    def test_every_bid_line_names_its_lot_id(self, email):
        """
        One id per bid, however many bids there are. Pinning the count just
        breaks the test every time the owner changes his mind about a lot.
        """
        numbered = re.findall(r"^\s*\d+\)\s*\[(BT-\d{3})\]", email, re.M)
        starts = len(re.findall(r"\bSTART \$", email))
        assert numbered, "no numbered bid blocks found"
        assert len(numbered) == starts == len(set(numbered)), (
            f"{len(numbered)} numbered block(s), {starts} START line(s), "
            f"{len(set(numbered))} distinct lot id(s) — these must match"
        )

    def test_a_long_description_survives_the_wrap(self, email):
        """
        BT-235's name was cut at "A Century of Pro" by the old fixed-width
        table. Spot-checked on a lot the owner has not declined, so the test
        fails on truncation rather than on him changing his mind about a lot.
        """
        assert "Century of Progress" in email, "BT-235 lost the fair name"


class TestTheCommercialTerms:
    def test_addressed_to_the_letterhead_address(self, email):
        assert "info@bluetoadauctions.com" in email

    def test_states_the_fifteen_percent_absentee_fee(self, email):
        assert "15%" in email

    def test_totals_reconcile_to_the_listed_bids(self, email):
        """What is printed on the page has to add up to the total on the page.

        A per-unit lot contributes its COMMITTED total, not its per-unit max.
        "MAX $25.00 PER UNIT x 3 = $75.00 TOTAL" puts two figures on one line and
        only the second one is money the sheet has committed; summing the first
        understates the page by $50 and the clerk cannot see why. That mismatch
        is exactly what this assertion caught when times-the-money first reached
        the compiler, so read the committed figure where a line states one.
        """
        maxes = [float(m.replace(",", "")) for m in
                 re.findall(r"MAX\s*\$\s*[\d,]+\.\d{2}[^\n]*?=\s*\$\s*([\d,]+\.\d{2})\s*TOTAL"
                            r"|MAX\s*\$\s*([\d,]+\.\d{2})(?![^\n]*TOTAL)", email)
                 for m in (m[0] or m[1],) if m]
        if not maxes:  # fixed-width layout: last figure on each bid line
            maxes = [float(re.findall(r"\$\s*([\d,]+\.\d{2})", ln)[-1].replace(",", ""))
                     for ln in bid_lines(email) if re.findall(r"\$\s*([\d,]+\.\d{2})", ln)]
        stated = re.search(r"TOTAL COMMITTED PROXY BIDS:\s*\$([\d,]+\.\d{2})", email)
        assert stated, "no stated total"
        assert abs(sum(maxes) - float(stated.group(1).replace(",", ""))) < 0.01, (
            f"listed bids sum to {sum(maxes):.2f}, email claims {stated.group(1)}"
        )

    def test_per_unit_lines_state_arithmetic_that_actually_multiplies(self, email):
        """A line claiming "$25.00 PER UNIT x 3 = $75.00" must be true.

        The clerk acts on this sentence. If the stated product is wrong he bids
        the wrong money and nothing downstream would ever catch it.
        """
        for per, units, total in re.findall(
                r"MAX\s*\$\s*([\d,]+\.\d{2})\s*PER UNIT\s*x\s*(\d+)"
                r"[^\n]*?=\s*\$\s*([\d,]+\.\d{2})\s*TOTAL", email):
            got = float(per.replace(",", "")) * int(units)
            assert abs(got - float(total.replace(",", ""))) < 0.01, (
                f"${per} x {units} is ${got:.2f}, line claims ${total}")

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


from src.assemble.email import compile_absentee_email
from src.bidmath import (
    CompEstimate, Confidence, Lot, allocate, price_lot, snap_to_increment, summarize,
)


def _lot(lot_id, caption, low, high):
    return Lot(
        lot_id=lot_id, caption=caption, category="vintage cards",
        fit_score=0.9, condition_penalty=0.0,
        comp=CompEstimate(low=low, high=high, source_count=3, confidence=Confidence.HIGH),
    )


def _compiled(lots):
    ds = allocate([price_lot(l) for l in lots], budget_cap=10_000)
    return compile_absentee_email(
        to="info@bluetoadauctions.com",
        subject="Absentee Bids - August 22 Antique & Estate Auction (Bidder: Richmond General)",
        auction_date="Saturday, August 22, 2026",
        venue="200 Elizabeth Lane, Genoa City, WI",
        lots=lots,
        decisions=ds,
    ), summarize(ds)


class TestCompilerKeepsTheClerkInformed:
    def test_a_description_longer_than_48_characters_survives_whole(self):
        caption = (
            "Cardboard multi-row storage box containing bulk sports trading cards "
            "including hockey, football, and baseball, produced by various manufacturers "
            "such as Score and Fleer Ultra, c. late 1980s to 2000s."
        )
        text, _ = _compiled([_lot("BT-016", caption, 40, 60)])
        assert caption in " ".join(text.split())
        assert "storage box containing bulk    " not in text

    def test_unallocated_lots_do_not_appear(self):
        cheap = _lot("BT-001", "Topps cards", 250, 400)
        dear = _lot("BT-999", "should not appear", 8000, 9000)
        ds = allocate([price_lot(cheap), price_lot(dear)], budget_cap=200.0)
        text = compile_absentee_email(
            to="info@bluetoadauctions.com", subject="Absentee Bids",
            auction_date="Saturday, August 22, 2026",
            venue="200 Elizabeth Lane, Genoa City, WI",
            lots=[cheap, dear], decisions=ds,
        )
        assert "BT-001" in text
        assert "BT-999" not in text

    def test_one_block_per_bid_not_a_fixed_width_table(self):
        text, _ = _compiled([_lot("BT-001", "Topps cards", 250, 400)])
        assert "ITEM DESCRIPTION" not in text
        assert "1)" in text and "[BT-001]" in text

