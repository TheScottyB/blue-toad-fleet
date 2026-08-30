"""
comp_report's selection accounting and the live layer's own guards, with the
network stubbed out.

Guards under test:

  - a PARTIAL verdict list — the model judged some rows and not others — must
    never present itself as a fully screened set. Measured 2026-08-24: two
    sold rows plus a one-verdict model response yielded comp_units=1,
    excluded_count=0, excluded=[] — the unjudged row silently left both the
    price band and the exclusion accounting.
  - the printed date window is the only authority (playbook G1) on the LIVE
    path too, not just the capture-import path: probed 2026-08-29, a 30-day
    printed window flowed through comp_report and returned absorption
    normally — a ~12x understatement labelled `sold_units_365d`.
  - read_sold's pagination: an exact-multiple-of-50 market has no short last
    page, so the phantom next page (zero rows, no message) is termination,
    not SuspectEmpty; and the _MAX_SOLD_PAGES cap must mark the read
    truncated, never pose as the whole market.

read_sold / _read_text / _read_active / select_comps are stubbed because they
are the I/O boundary (CDP Chrome and Vertex); everything else runs unmodified.
"""

import re

import pytest

from src.comps import (ActivePage, NonAnnualWindow, SoldPage, SoldRow,
                       SuspectEmpty)
from src.comps import live

UNFILTERED = "UNAVAILABLE — figures above are UNFILTERED"


SOLD_FILTERS = ["Filter Applied", "Condition filter (1 Selected)", "Used"]
ACTIVE_FILTERS = ["Filter Applied"]


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
        filters=SOLD_FILTERS,
    )
    active = ActivePage(total_active=46, filters=ACTIVE_FILTERS)
    monkeypatch.setattr(live, "read_sold", lambda query: sold)
    monkeypatch.setattr(live, "read_active", lambda query: active)

    async def fake_active(query):
        return active

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

    def test_the_judged_comps_are_listed_not_just_the_excluded(
            self, two_row_market, monkeypatch):
        """When the band moves between runs, the row that entered it must be
        visible. A borderline listing flipped unsure -> comp between the
        2026-08-24 and 2026-08-29 RG-0144 runs and only the band betrayed
        it — the accepted rows were nowhere in the output to diff."""
        monkeypatch.setattr(live, "select_comps", lambda ident, titles: [
            {"index": 0, "verdict": "comp", "reason": "same item"},
            {"index": 1, "verdict": "not_comp", "reason": "parts lot"},
        ])
        out = live.comp_report("Boston Champion sharpener", "boston champion")
        assert out["comp_selection"]["comps"] == [
            {"title": "Vintage Boston Champion Pencil Sharpener NOS",
             "price": 33.30, "qty": 6, "date": "Jul 15, 2026"}]


class TestFilterSurfacing:
    """Both tools surface the page-printed filter markers — the page's own
    claim about its scope, which can be a display-only ghost (measured
    2026-08-29). A claimed scope must reach the caller as printed."""

    def test_comp_report_carries_the_printed_filters(
            self, two_row_market, monkeypatch):
        monkeypatch.setattr(live, "select_comps", lambda ident, titles: None)
        out = live.comp_report("Boston Champion sharpener", "boston champion")
        assert out["filters_as_printed"] == {
            "sold": SOLD_FILTERS, "active": ACTIVE_FILTERS}

    def test_ebay_absorption_carries_the_printed_filters(
            self, two_row_market):
        from scripts import comps_mcp_server
        out = comps_mcp_server.ebay_absorption("boston champion")
        assert out["filters_as_printed"] == {
            "sold": SOLD_FILTERS, "active": ACTIVE_FILTERS}


# --- the live path must enforce the printed window, like the import path ----

ANNUAL_WINDOW = "Aug 21, 2025 – Aug 21, 2026"
THIRTY_DAY_WINDOW = "Jul 23, 2026 – Aug 21, 2026"

ONE_ROW = [SoldRow(title="Synthetic sold listing title",
                   price=10.00, qty=1, date="Jul 15, 2026")]


def _stub_market(monkeypatch, sold: SoldPage) -> None:
    active = ActivePage(total_active=46, filters=[])
    monkeypatch.setattr(live, "read_sold", lambda query: sold)
    monkeypatch.setattr(live, "read_active", lambda query: active)

    async def fake_active(query):
        return active

    monkeypatch.setattr(live, "_read_active", fake_active)
    monkeypatch.setattr(live, "select_comps", lambda ident, titles: None)


class TestWindowAuthority:
    """GOTCHA 1 on the live path: the printed date line is the only authority
    on the window. evidence/model.py already refuses a non-annual window on
    the capture-import path; comp_report and ebay_absorption must refuse the
    same fact, not compute `sold_units_365d` off a 30-day page."""

    def test_a_non_annual_printed_window_is_refused(self, monkeypatch):
        _stub_market(monkeypatch, SoldPage(window=THIRTY_DAY_WINDOW,
                                           rows=list(ONE_ROW)))
        with pytest.raises(NonAnnualWindow):
            live.comp_report("synthetic item", "synthetic query")

    def test_an_absent_window_with_rows_is_refused(self, monkeypatch):
        """Rows without a date line is an unloaded or mutant page — fail
        closed, never label the count 365d on faith."""
        _stub_market(monkeypatch, SoldPage(window=None, rows=list(ONE_ROW)))
        with pytest.raises(NonAnnualWindow):
            live.comp_report("synthetic item", "synthetic query")

    def test_a_genuine_zero_prints_no_window_and_still_reports(
            self, monkeypatch):
        """The zero-results page prints no date line at all; refusing it
        would make every dead market unreadable. Its report already states
        the absence: window_as_printed None, genuine_zero True."""
        _stub_market(monkeypatch, SoldPage(window=None, genuine_zero=True))
        out = live.comp_report("synthetic item", "synthetic query")
        assert out["genuine_zero"] is True
        assert out["window_as_printed"] is None

    def test_ebay_absorption_refuses_a_non_annual_window(self, monkeypatch):
        from scripts import comps_mcp_server
        _stub_market(monkeypatch, SoldPage(window=THIRTY_DAY_WINDOW,
                                           rows=list(ONE_ROW)))
        with pytest.raises(NonAnnualWindow):
            comps_mcp_server.ebay_absorption("synthetic query")


# --- read_sold pagination, against the real parser -------------------------

def _sold_page_text(n_rows: int, first: int = 0) -> str:
    """innerText-shaped SOLD page with `n_rows` rows, for the real parser."""
    head = (
        "Seller Hub\nrichmondgeneral\nResearch products\nSold​Active\n"
        f"{ANNUAL_WINDOW}\nShow sales trends\n"
        "$24.11\nAvg sold price\n$4.99 - $105.00\nSold price range\n"
        "$8.83\nAvg shipping\n7%\nFree shipping\n-\nSell-through\n"
        "43\nTotal sellers\nListing\n\nActions\n\nAvg sold price\n"
    )
    rows = "".join(
        "\n, preview full size image\n"
        f"Synthetic sold listing number {first + i:04d} title\n\nEdit\n\n"
        "$10.00\nFixed price\n\n$5.00\n0% Free shipping\n\n1\n\n$10.00\n\n"
        "-\n\nJul 15, 2026\n"
        for i in range(n_rows)
    )
    return head + rows + "Page 1\n"


# Zero rows, no zero-results message — the shape of both the limit>50 silent
# render AND the page one past an exact-multiple-of-50 result set.
PHANTOM_EMPTY = (
    "Seller Hub\nrichmondgeneral\nResearch products\nSold​Active\n"
    "Category selected:\nAll Categories\nAbout eBay\n"
)


@pytest.fixture
def paged_market(monkeypatch):
    """read_sold against canned page texts keyed by offset, real parser."""
    pages: dict[int, str] = {}
    calls: list[int] = []

    async def fake_read_text(url, wait=8.0):
        offset = int(re.search(r"offset=(\d+)", url).group(1))
        calls.append(offset)
        return pages[offset]

    monkeypatch.setattr(live, "_read_text", fake_read_text)
    return pages, calls


class TestSoldPagination:
    def test_a_market_of_exactly_50_rows_ends_at_the_phantom_page(
            self, paged_market):
        """An exact multiple of 50 has no short last page — the next page
        renders zero rows with no message. After >=1 full page that is
        termination, not the silent-empty failure."""
        pages, _ = paged_market
        pages[0] = _sold_page_text(50)
        pages[50] = PHANTOM_EMPTY
        sold = live.read_sold("synthetic query")
        assert len(sold.rows) == 50
        assert sold.truncated is False

    def test_a_short_last_page_is_a_complete_read(self, paged_market):
        pages, _ = paged_market
        pages[0] = _sold_page_text(50)
        pages[50] = _sold_page_text(3, first=50)
        sold = live.read_sold("synthetic query")
        assert len(sold.rows) == 53
        assert sold.truncated is False

    def test_the_page_cap_is_an_explicit_truncation_marker(self, paged_market):
        """12 full pages hit _MAX_SOLD_PAGES with the last page still full:
        more rows exist that were never read. The page cap was previously
        silent — 600 rows posed as the whole market."""
        pages, calls = paged_market
        for off in range(0, 600, 50):
            pages[off] = _sold_page_text(50, first=off)
        sold = live.read_sold("synthetic query")
        assert len(sold.rows) == 600
        assert sold.truncated is True
        assert 600 not in calls

    def test_a_silent_empty_FIRST_page_still_raises(self, paged_market):
        """The phantom-page allowance must not weaken GOTCHA 2: zero rows
        with no message on page one is still suspect, never 'sold 0'."""
        pages, _ = paged_market
        pages[0] = PHANTOM_EMPTY
        with pytest.raises(SuspectEmpty):
            live.read_sold("synthetic query")


class TestTruncationMarker:
    def test_comp_report_carries_the_truncation_marker(self, monkeypatch):
        _stub_market(monkeypatch, SoldPage(window=ANNUAL_WINDOW,
                                           rows=list(ONE_ROW), truncated=True))
        out = live.comp_report("synthetic item", "synthetic query")
        assert out["sold_results_truncated"] is True

    def test_ebay_absorption_carries_the_truncation_marker(self, monkeypatch):
        from scripts import comps_mcp_server
        _stub_market(monkeypatch, SoldPage(window=ANNUAL_WINDOW,
                                           rows=list(ONE_ROW), truncated=True))
        out = comps_mcp_server.ebay_absorption("synthetic query")
        assert out["sold_results_truncated"] is True

    def test_an_untruncated_read_says_so(self, two_row_market, monkeypatch):
        monkeypatch.setattr(live, "select_comps", lambda ident, titles: None)
        out = live.comp_report("Boston Champion sharpener", "boston champion")
        assert out["sold_results_truncated"] is False


class TestUnfilteredLabelling:
    """comps_mcp_server labels its page aggregate landed_avg_unfiltered;
    comp_report emitted the same unscreened aggregates with bare names. One
    convention: page aggregates carry the _unfiltered suffix everywhere."""

    def test_page_aggregates_are_labelled_unfiltered(
            self, two_row_market, monkeypatch):
        monkeypatch.setattr(live, "select_comps", lambda ident, titles: None)
        out = live.comp_report("Boston Champion sharpener", "boston champion")
        assert out["avg_sold_price_unfiltered"] == 24.11
        assert out["avg_shipping_unfiltered"] == 8.83
        assert out["landed_avg_unfiltered"] == pytest.approx(32.94)
        for bare in ("avg_sold_price", "avg_shipping", "landed_avg"):
            assert bare not in out
