"""
The pure comps layer against real Seller Hub research-API responses.

Fixtures under tests/fixtures/comps/ are live responses captured 2026-09-25
(Heineken Special Dark mirror query + a nonsense query), trimmed of tracking
and tooltip nodes but keeping eBay's exact nesting and text — including the
`$ 45.00` money format and the always-present PageErrorModule that broke the
old innerText scraper silently.
"""

import datetime as dt
import json
from pathlib import Path

import pytest

from src.comps import (
    ChallengePage, NonAnnualWindow, SoldPage, SoldRow, SuspectEmpty,
    UnknownConditionId, absorption, aggregates, api_total_sold, money,
    money_range, months_of_supply, parse_active_response,
    parse_sold_response, price_stats, require_annual_window,
    require_known_condition, sold_cross_check, split_modules, window_days,
    window_label,
)

FIX = Path(__file__).parent / "fixtures" / "comps"
WINDOW = "Sep 25, 2025 – Sep 25, 2026"


def fixture(name: str) -> str:
    return (FIX / name).read_text()


SOLD = fixture("sold_heineken_2026-09-25.ndjson")
ACTIVE = fixture("active_heineken_2026-09-25.ndjson")
SOLD_ZERO = fixture("sold_zero_2026-09-25.ndjson")
ACTIVE_ZERO = fixture("active_zero_2026-09-25.ndjson")
SOLD_PAST_END = fixture("sold_past_end_2026-09-25.ndjson")


class TestMoney:
    """The format drift that emptied every price band: eBay renders
    `$ 45.00` (space) in rows and API values. One tolerant parser."""

    @pytest.mark.parametrize("text,value", [
        ("$ 45.00", 45.0), ("$45.00", 45.0), ("+$ 12.80 shipping", 12.8),
        ("$ 6,508.70", 6508.70), ("$ 5", 5.0),
    ])
    def test_amounts(self, text, value):
        assert money(text) == value

    @pytest.mark.parametrize("text", [None, "", "-", "- - -", "Free shipping"])
    def test_absence_is_none_never_zero(self, text):
        assert money(text) is None

    @pytest.mark.parametrize("text", [
        "$ 15.00 - $ 45.00", "$15.00 – $45.00", "$ 15.00 — $ 45.00"])
    def test_ranges_with_any_dash(self, text):
        assert money_range(text) == (15.0, 45.0)

    def test_no_range_is_a_pair_of_none(self):
        assert money_range("- - -") == (None, None)


class TestSoldResponse:
    def test_rows_carry_named_fields(self):
        page = parse_sold_response(SOLD, window=WINDOW)
        assert len(page.rows) == 5
        r = next(r for r in page.rows if r.item_id == "158271810080")
        assert r.title.startswith("Heineken Imported Special Dark Beer")
        assert r.price == 23.0
        assert r.shipping == 8.07
        assert r.landed == 31.07
        assert r.qty == 1
        assert r.date == "Sep 13, 2026"
        assert r.url == "https://www.ebay.com/itm/158271810080"
        assert r.image.startswith("https://i.ebayimg.com/")

    def test_every_row_has_a_price(self):
        """The old scraper returned price=None for all five of these."""
        page = parse_sold_response(SOLD, window=WINDOW)
        assert sorted(r.price for r in page.rows) == [
            15.0, 23.0, 26.95, 28.34, 45.0]

    def test_free_shipping_row_is_zero_not_unknown(self):
        page = parse_sold_response(SOLD, window=WINDOW)
        r = next(r for r in page.rows if r.item_id == "267646832976")
        assert r.shipping == 0.0
        assert r.landed == 26.95

    def test_aggregates_including_the_range_and_total(self):
        page = parse_sold_response(SOLD, window=WINDOW)
        assert page.avg_price == 27.66
        assert (page.price_low, page.price_high) == (15.0, 45.0)
        assert page.avg_shipping == 11.06
        assert page.total_sold == 5
        assert page.total_sellers == 5
        assert page.landed_avg == 38.72
        assert page.window == WINDOW

    def test_the_page_error_module_is_noise_when_data_is_present(self):
        mods = split_modules(SOLD)
        assert mods[0]["_type"] == "PageErrorModule"
        assert mods[0]["severity"] == "ERROR"
        assert parse_sold_response(SOLD).rows  # parsed anyway

    def test_units_not_rows(self):
        mods = split_modules(SOLD)
        results = next(m for m in mods
                       if m["_type"] == "SearchResultsModule")["results"]
        results[0]["itemssold"]["textSpans"][0]["text"] = "3"
        body = "\n".join(json.dumps(m) for m in mods)
        page = parse_sold_response(body, window=WINDOW)
        assert len(page.rows) == 5
        assert page.sold_units == 7  # one row now sold 3

    def test_a_genuine_zero_needs_ebays_own_message(self):
        page = parse_sold_response(SOLD_ZERO, window=WINDOW)
        assert page.genuine_zero and page.rows == []
        assert page.sold_units == 0

    def test_the_page_past_the_end_reads_as_zero(self):
        """offset past the last row: zero rows WITH the message — the walk
        treats it as termination, never as a dead market."""
        assert parse_sold_response(SOLD_PAST_END).genuine_zero

    def test_zero_rows_without_the_message_is_suspect(self):
        mods = [m for m in split_modules(SOLD_ZERO)
                if m["_type"] != "PageErrorModule"]
        body = "\n".join(json.dumps(m) for m in mods)
        with pytest.raises(SuspectEmpty):
            parse_sold_response(body)

    def test_no_results_module_is_suspect(self):
        body = "\n".join(json.dumps(m) for m in split_modules(SOLD)
                         if m["_type"] != "SearchResultsModule")
        with pytest.raises(SuspectEmpty):
            parse_sold_response(body)

    @pytest.mark.parametrize("body", [
        "<!DOCTYPE html><html><title>Sign in or Register</title>",
        "Pardon Our Interruption...",
        "not json at all",
    ])
    def test_non_json_is_a_challenge(self, body):
        with pytest.raises(ChallengePage):
            parse_sold_response(body)

    def test_empty_body_is_suspect(self):
        with pytest.raises(SuspectEmpty):
            parse_sold_response("")


class TestActiveResponse:
    def test_total_comes_from_the_aggregate_not_the_rows(self):
        page = parse_active_response(ACTIVE)
        assert page.total_active == 19
        assert len(page.rows) == 3  # fixture trimmed to 3 rows

    def test_rows_and_price_strip(self):
        page = parse_active_response(ACTIVE)
        assert page.avg_price == 45.38
        assert (page.price_low, page.price_high) == (17.99, 79.99)
        r = page.rows[0]
        assert r.price is not None and r.item_id and r.url
        assert r.start_date

    def test_a_genuine_zero(self):
        page = parse_active_response(ACTIVE_ZERO)
        assert page.total_active == 0 and page.rows == []

    def test_aggregates_read_as_labelled(self):
        agg = aggregates(split_modules(ACTIVE))
        assert agg["Total active listings"] == "19"


class TestWindowAuthority:
    """The API prints no window, so the guard is two-part: the requested
    window spans a year, and every sale date falls inside it."""

    def row(self, date):
        return SoldRow(title="Synthetic sold listing", price=10.0, qty=1,
                       date=date, item_id="1")

    def test_label_and_span(self):
        label = window_label(dt.date(2025, 9, 25), dt.date(2026, 9, 25))
        assert label == WINDOW
        assert window_days(label) == 365

    def test_the_real_rows_sit_inside_the_window(self):
        require_annual_window(parse_sold_response(SOLD, window=WINDOW))

    def test_refuses_a_short_window(self):
        with pytest.raises(NonAnnualWindow):
            require_annual_window(SoldPage(
                window="Aug 26, 2026 – Sep 25, 2026",
                rows=[self.row("Sep 13, 2026")]))

    def test_refuses_a_sale_outside_the_window(self):
        """The data did not honour the pinned dates (what a dropped
        startDate/endDate does: measured 2 rows vs 5)."""
        with pytest.raises(NonAnnualWindow):
            require_annual_window(SoldPage(
                window=WINDOW, rows=[self.row("Jun 2, 2025")]))

    def test_one_day_of_timezone_slack(self):
        require_annual_window(SoldPage(
            window=WINDOW, rows=[self.row("Sep 24, 2025"),
                                 self.row("Sep 26, 2026")]))

    def test_refuses_rows_without_any_window(self):
        with pytest.raises(NonAnnualWindow):
            require_annual_window(SoldPage(window=None,
                                           rows=[self.row("Sep 13, 2026")]))

    def test_accepts_a_leap_year_span(self):
        require_annual_window(SoldPage(
            window="Jul 1, 2027 – Jul 1, 2028",
            rows=[self.row("Feb 29, 2028")]))

    def test_a_genuine_zero_passes(self):
        require_annual_window(SoldPage(window=WINDOW, genuine_zero=True))
        require_annual_window(SoldPage(window=None, genuine_zero=True))


class TestAbsorption:
    def test_the_metric(self):
        """sold units per year over standing supply. 295/138 was the sharpener."""
        assert absorption(295, 138) == pytest.approx(2.14, abs=0.01)

    def test_months_of_supply_is_the_reciprocal(self):
        assert months_of_supply(295, 138) == pytest.approx(5.6, abs=0.05)

    def test_months_of_supply_computes_from_raw_counts_not_rounded_rate(self):
        """12 * 158 / 4 = 474.0; 12/round(rate) printed 400 on the RG-0144
        windsor read, 2026-08-29."""
        assert months_of_supply(4, 158) == pytest.approx(474.0)

    def test_edges_are_none_not_numbers(self):
        assert months_of_supply(0, 40) is None
        assert months_of_supply(15, 0) is None
        assert absorption(15, 0) is None
        assert absorption(0, 0) is None


class TestPriceStats:
    def test_quartiles_over_the_real_heineken_comps(self):
        s = price_stats([23.0, 26.95, 15.0, 28.34])
        assert s["n"] == 4 and s["min"] == 15.0 and s["max"] == 28.34
        assert s["median"] == pytest.approx(24.98, abs=0.01)
        assert s["p25"] <= s["median"] <= s["p75"]

    def test_one_value(self):
        assert price_stats([20.0]) == {"n": 1, "min": 20.0, "p25": 20.0,
                                       "median": 20.0, "p75": 20.0,
                                       "max": 20.0}

    def test_nothing_is_none(self):
        assert price_stats([]) is None


class TestConditionScope:
    def test_known_ids_pass_and_carry_labels(self):
        assert require_known_condition(3000) == "Used"
        assert require_known_condition(1000) == "New"
        assert require_known_condition(7000) == "For parts or not working"

    def test_unknown_ids_are_refused_not_silently_ignored(self):
        with pytest.raises(UnknownConditionId):
            require_known_condition(999999)
        with pytest.raises(UnknownConditionId):
            require_known_condition(0)

    def test_none_means_no_filter(self):
        assert require_known_condition(None) is None


class TestApiTotalSold:
    def test_reads_total_sold_from_a_real_response_body(self):
        assert api_total_sold(SOLD) == 5

    def test_a_comma_grouped_total_parses(self):
        assert api_total_sold(SOLD.replace(
            '"text":"Total sold"}]},"value":{"_type":"TextualDisplay",'
            '"textSpans":[{"_type":"TextSpan","text":"5"',
            '"text":"Total sold"}]},"value":{"_type":"TextualDisplay",'
            '"textSpans":[{"_type":"TextSpan","text":"1,291"')) == 1291

    def test_no_aggregate_module_is_none_not_zero(self):
        assert api_total_sold('{"_type":"PageErrorModule"}') is None
        assert api_total_sold("Pardon Our Interruption...") is None
        assert api_total_sold("") is None


class TestSoldCrossCheck:
    def test_agreement_is_a_match(self):
        assert sold_cross_check(291, False, 291)["verdict"] == "match"

    def test_disagreement_is_a_named_mismatch(self):
        v = sold_cross_check(290, False, 291)["verdict"]
        assert "MISMATCH" in v and "290" in v and "291" in v

    def test_a_truncated_walk_is_a_floor_not_a_mismatch(self):
        assert sold_cross_check(600, True, 950)["verdict"] == "consistent floor"

    def test_a_truncated_walk_above_the_total_is_still_wrong(self):
        assert "MISMATCH" in sold_cross_check(600, True, 500)["verdict"]

    def test_an_unreadable_total_is_stated_not_hidden(self):
        v = sold_cross_check(291, False, None)
        assert v["api_total_sold"] is None
        assert "UNAVAILABLE" in v["verdict"]
