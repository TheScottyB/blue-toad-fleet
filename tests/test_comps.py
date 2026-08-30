"""
The comp connector's pure layer, tested against real page shapes.

Every fixture below is built from text the Seller Hub research page actually
rendered during the 2026-08-21/22 sessions (Boston Champion / Century of
Progress / Pink Floyd), and every guard exists because the playbook recorded a
failure that produced a WRONG NUMBER rather than an error:

  - `limit` above 50 renders zero rows on SOLD with no message, so an empty
    parse must be treated as SUSPECT, never as "sold 0" (absorption computes as
    0 from a page that looks fine).
  - a genuine empty market prints "No sold results found for <query>" — that,
    and only that, is a real zero.
  - `Total sold` is UNITS, not lot size: avg_sold_price x total_sold =
    item_sales reconciles on every multi-quantity row, so the numerator sums
    the column; counting rows undercounted by 3.5% on the sharpener corpus.
  - the date window the PAGE prints is the only authority; the request's
    dayRange is a dropdown label.
"""

import pytest

from src.comps import (
    ChallengePage, NonAnnualWindow, SoldPage, SoldRow, SuspectEmpty,
    absorption, months_of_supply, parse_active_page, parse_filters,
    parse_sold_page, require_annual_window, window_days,
)

# --- fixtures shaped exactly like document.body.innerText -------------------

SOLD_PAGE = """Seller Hub
richmondgeneral
Research products
Sold​Active
Aug 21, 2025 – Aug 21, 2026
Show sales trends
$24.11
Avg sold price
$4.99 - $105.00
Sold price range
$8.83
Avg shipping
7%
Free shipping
-
Sell-through
43
Total sellers
Listing

Actions

Avg sold price

, preview full size image
Vintage Boston Champion Pencil Sharpener Hand Crank Pinch Feed NEW NOS

Edit

$33.30
Fixed price

$8.95
0% Free shipping

6

$199.80

-

Jul 15, 2026

, preview full size image
1933 Chicago World's Fair Glass Bottle - A Century of Progress 1833-1933 -No Cap

Edit

$20.00
Fixed price

$6.68
0% Free shipping

1

$20.00

-

Jul 26, 2026

, preview full size image
Boston Champion Pencil Sharpener

Edit

$12.50
Auction

$6.80
0% Free shipping

1

$12.50

3

Aug 12, 2026
Page 1
"""

ACTIVE_PAGE = """Seller Hub
richmondgeneral
Sold​Active
Currently live today
Show current trends
$30.45
Avg listing price
$9.00 - $89.99
Listing price range
$10.02
Avg shipping
15%
Free shipping
46
Total active listings
22%
Promoted listings
Listing

, preview full size image
Vintage Old Bottle Chicago Fair "A Century Of Progress 1833-1933" Well Preserved

Edit

$19.98
Free shipping

-

0

-

Aug 19, 2026

, preview full size image
1933 Chicago Century of Progress Metal Key Fob Bottle Opener

Edit

$21.99
+$9.99 shipping

-

4

-

Jul 23, 2026
"""

GENUINE_ZERO = """Category selected:
All Categories
Sold​Active
No sold results found for "Pink Floyd Palace Theatre Manchester poster"
About eBay
"""

SILENT_EMPTY = """Seller Hub
richmondgeneral
Research products
Sold​Active
Category selected:
All Categories
About eBay
"""

CHALLENGE = """Pardon Our Interruption...
As you were browsing something about your browser made us think you were a bot.
"""

# The filter bar as document.body.innerText actually renders it, captured live
# 2026-08-24 with a sticky "Used" condition filter left over from a manual
# Seller Hub session. The SOLD tab printed all three markers; a fresh ACTIVE
# render printed only the page-level badge with a plain button label.

FILTERED_BAR = """Category selected:
All Categories
Filter Applied
Select a different category
Lock selected filters
Condition filter (1 Selected)
Filter Applied
Format filter
Price filter
Top rated
More filters
Used
Sold​Active
"""

BADGE_ONLY_BAR = """Category selected:
All Categories
Filter Applied
Select a different category
Lock selected filters
Condition filter
Format filter
Price filter
Top rated
More filters
Sold​Active
"""

CLEAN_BAR = """Category selected:
All Categories
Select a different category
Lock selected filters
Condition filter
Format filter
Price filter
Top rated
More filters
Sold​Active
"""


class TestSoldParsing:
    def test_reads_the_window_the_page_printed(self):
        page = parse_sold_page(SOLD_PAGE)
        assert page.window == "Aug 21, 2025 – Aug 21, 2026"

    def test_sums_units_not_rows(self):
        """The x6 NOS listing is six sales. 3 rows, 8 units."""
        page = parse_sold_page(SOLD_PAGE)
        assert len(page.rows) == 3
        assert page.sold_units == 8

    def test_row_fields(self):
        r = parse_sold_page(SOLD_PAGE).rows[0]
        assert r.title.startswith("Vintage Boston Champion")
        assert r.price == 33.30
        assert r.qty == 6

    def test_aggregate_block(self):
        page = parse_sold_page(SOLD_PAGE)
        assert page.avg_price == 24.11
        assert page.avg_shipping == 8.83
        assert (page.price_low, page.price_high) == (4.99, 105.00)

    def test_landed_average_includes_shipping(self):
        page = parse_sold_page(SOLD_PAGE)
        assert page.landed_avg == pytest.approx(24.11 + 8.83)

    def test_a_genuine_zero_is_zero(self):
        page = parse_sold_page(GENUINE_ZERO)
        assert page.rows == [] and page.sold_units == 0
        assert page.genuine_zero is True

    def test_an_empty_page_without_the_zero_message_is_SUSPECT_not_zero(self):
        """GOTCHA 2 as code. limit>50 renders nothing, silently; treating that
        as 'sold 0' computes absorption 0 from a page that looks fine."""
        with pytest.raises(SuspectEmpty):
            parse_sold_page(SILENT_EMPTY)

    def test_a_challenge_page_raises_not_parses(self):
        with pytest.raises(ChallengePage):
            parse_sold_page(CHALLENGE)


class TestActiveParsing:
    def test_denominator_comes_from_the_aggregate_not_row_count(self):
        """The page says 46 active; only 2 rows are rendered in the fixture.
        Counting rows here would understate the denominator 23x."""
        page = parse_active_page(ACTIVE_PAGE)
        assert page.total_active == 46
        assert len(page.rows) == 2

    def test_titles(self):
        page = parse_active_page(ACTIVE_PAGE)
        assert "Key Fob Bottle Opener" in page.rows[1].title

    def test_challenge_raises(self):
        with pytest.raises(ChallengePage):
            parse_active_page(CHALLENGE)


class TestFilterScope:
    """The page's printed filter markers are surfaced as printed — they are
    the page's CLAIM about its own scope (a sticky chip can even be a
    display-only ghost, measured 2026-08-29). An absent bar is UNKNOWN,
    never 'clean'."""

    def test_reports_every_marker_the_sold_page_printed(self):
        page = parse_sold_page(FILTERED_BAR + SOLD_PAGE)
        assert page.filters == [
            "Filter Applied", "Condition filter (1 Selected)", "Used"]

    def test_badge_alone_is_still_a_scoped_read(self):
        page = parse_active_page(BADGE_ONLY_BAR + ACTIVE_PAGE)
        assert page.filters == ["Filter Applied"]

    def test_a_clean_bar_is_an_empty_list(self):
        page = parse_sold_page(CLEAN_BAR + SOLD_PAGE)
        assert page.filters == []

    def test_no_bar_printed_is_unknown_not_clean(self):
        """SOLD_PAGE has no filter bar at all. That is 'the page did not
        print its filter state', which must never read as 'unfiltered'."""
        page = parse_sold_page(SOLD_PAGE)
        assert page.filters is None

    def test_a_genuine_zero_still_carries_the_scope(self):
        """A scoped zero is not the same fact as an unscoped zero."""
        page = parse_sold_page(FILTERED_BAR + GENUINE_ZERO)
        assert page.genuine_zero is True
        assert page.filters == [
            "Filter Applied", "Condition filter (1 Selected)", "Used"]

    def test_parse_filters_directly(self):
        assert parse_filters(FILTERED_BAR) == [
            "Filter Applied", "Condition filter (1 Selected)", "Used"]
        assert parse_filters(CLEAN_BAR) == []
        assert parse_filters("no bar here at all") is None


class TestWindowAuthority:
    """GOTCHA 1 as pure code: the date line the page prints is the only
    authority on the window, and the metric is DEFINED per 365 days. A
    non-annual print must refuse, mirroring evidence/model.py's exactly-365
    check on the capture-import path (±1 day here for leap-year spans)."""

    def test_the_annual_print_spans_365_days(self):
        assert window_days("Aug 21, 2025 – Aug 21, 2026") == 365

    def test_a_30_day_print_is_not_annual(self):
        """The window the verifier probe fed comp_report on 2026-08-29."""
        assert window_days("Jul 23, 2026 – Aug 21, 2026") == 29

    def test_an_absent_or_garbled_window_is_none(self):
        assert window_days(None) is None
        assert window_days("Show sales trends") is None

    def test_refuses_a_short_window(self):
        page = SoldPage(window="Jul 23, 2026 – Aug 21, 2026", rows=[
            SoldRow(title="Synthetic sold listing", price=10.0, qty=1,
                    date="Aug 12, 2026")])
        with pytest.raises(NonAnnualWindow):
            require_annual_window(page)

    def test_refuses_rows_without_any_window(self):
        page = SoldPage(window=None, rows=[
            SoldRow(title="Synthetic sold listing", price=10.0, qty=1,
                    date="Aug 12, 2026")])
        with pytest.raises(NonAnnualWindow):
            require_annual_window(page)

    def test_accepts_a_leap_year_span(self):
        """Feb 29, 2028 sits inside this year: 366 printed days is still a
        year, not a scope error."""
        assert window_days("Jul 1, 2027 – Jul 1, 2028") == 366
        require_annual_window(SoldPage(window="Jul 1, 2027 – Jul 1, 2028",
                                       rows=[SoldRow(title="Synthetic listing",
                                                     price=1.0, qty=1,
                                                     date=None)]))

    def test_a_genuine_zero_prints_no_window_and_is_exempt(self):
        """The zero-results page prints no date line at all (see
        GENUINE_ZERO above); its report states the absence explicitly
        instead of refusing every dead market."""
        require_annual_window(SoldPage(window=None, genuine_zero=True))


class TestAbsorption:
    def test_the_metric(self):
        """sold units per year over standing supply. 295/138 was the sharpener."""
        assert absorption(295, 138) == pytest.approx(2.14, abs=0.01)

    def test_months_of_supply_is_the_reciprocal(self):
        assert months_of_supply(295, 138) == pytest.approx(5.6, abs=0.05)

    def test_months_of_supply_computes_from_raw_counts_not_rounded_rate(self):
        """4 sold over 158 standing: 12 * 158 / 4 = 474.0 months. Feeding
        the 2-dp rounded absorption (0.03) into 12/rate printed 400 — 15%
        off — on the live RG-0144 windsor read, 2026-08-29. A slow market
        is exactly where the sheet reader needs the number to be right."""
        assert months_of_supply(4, 158) == pytest.approx(474.0)

    def test_months_of_supply_edges_are_None_not_numbers(self):
        assert months_of_supply(0, 40) is None
        assert months_of_supply(15, 0) is None

    def test_zero_active_is_not_a_division_crash(self):
        """Nothing standing: supply clears as fast as it appears. Report as
        None rather than a fake number — the caller must say 'no standing
        supply', not print inf on a sheet."""
        assert absorption(15, 0) is None

    def test_zero_sold_zero_active_is_a_dead_market(self):
        assert absorption(0, 0) is None
