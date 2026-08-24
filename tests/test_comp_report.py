"""
comp_report's selection accounting, with the network stubbed out.

The guard under test: a PARTIAL verdict list — the model judged some rows and
not others — must never present itself as a fully screened set. Measured
2026-08-24: two sold rows plus a one-verdict model response yielded
comp_units=1, excluded_count=0, excluded=[] — the unjudged row silently left
both the price band and the exclusion accounting. That breaks the module's
own rule that absence is stated, never hidden (selection failure = UNFILTERED,
capture failure = CAPTURE FAILED), so a hole in the verdict list is a
selection failure.

read_sold / _read_active / select_comps are stubbed because they are the I/O
boundary (CDP Chrome and Vertex); comp_report's branching runs unmodified.
"""

import pytest

from src.comps import ActivePage, SoldPage, SoldRow
from src.comps import live

UNFILTERED = "UNAVAILABLE — figures above are UNFILTERED"


@pytest.fixture
def two_row_market(monkeypatch):
    sold = SoldPage(
        window="Aug 21, 2025 – Aug 21, 2026",
        rows=[
            SoldRow(title="Vintage Boston Champion Pencil Sharpener NOS",
                    price=33.30, qty=6, date="Jul 15, 2026"),
            SoldRow(title="Boston Champion Pencil Sharpener",
                    price=12.50, qty=1, date="Aug 12, 2026"),
        ],
        avg_price=24.11,
        avg_shipping=8.83,
    )
    monkeypatch.setattr(live, "read_sold", lambda query: sold)

    async def fake_active(query):
        return ActivePage(total_active=46)

    monkeypatch.setattr(live, "_read_active", fake_active)
    return sold


class TestPartialSelection:
    def test_a_verdict_hole_is_a_failure_not_a_screened_set(
            self, two_row_market, monkeypatch):
        """One judged row, one hole. The response must say UNFILTERED, not
        pose as a screened set that quietly dropped a row from the band and
        the exclusion accounting."""
        monkeypatch.setattr(live, "select_comps", lambda ident, titles: [
            {"index": 0, "verdict": "comp", "reason": "same item"},
            None,
        ])
        out = live.comp_report("Boston Champion sharpener", "boston champion")
        assert out["comp_selection"] == UNFILTERED

    def test_raw_figures_survive_a_failed_selection(
            self, two_row_market, monkeypatch):
        """Absorption is raw by design — it must still be reported when the
        screen fails, labelled as unfiltered by the branch above."""
        monkeypatch.setattr(live, "select_comps",
                            lambda ident, titles: [None, None])
        out = live.comp_report("Boston Champion sharpener", "boston champion")
        assert out["comp_selection"] == UNFILTERED
        assert out["sold_units_365d"] == 7
        assert out["absorption"] == pytest.approx(7 / 46, abs=0.01)

    def test_a_complete_screen_still_reports_as_screened(
            self, two_row_market, monkeypatch):
        """The guard must not over-fire: every row judged means the screened
        dict, with every non-comp row in the exclusion accounting."""
        monkeypatch.setattr(live, "select_comps", lambda ident, titles: [
            {"index": 0, "verdict": "comp", "reason": "same item"},
            {"index": 1, "verdict": "not_comp", "reason": "parts lot"},
        ])
        out = live.comp_report("Boston Champion sharpener", "boston champion")
        sel = out["comp_selection"]
        assert sel["comp_units"] == 6
        assert sel["excluded_count"] == 1
        assert sel["comp_price_band"] == [33.30, 33.30]
