"""
The live layer with I/O replaced at the ResearchSession boundary.

  - _read_market's pagination against canned API bodies keyed by request:
    a short page ends the walk, an exact multiple of 50 ends on the page
    past the end (zero rows WITH eBay's message), the cap marks a floor.
  - comp_report's selection accounting, price stats, links, rows and
    evidence, with the model call stubbed.
  - the window guard refusing through both tools.
"""

import json
import urllib.parse
from pathlib import Path

import pytest

from src.comps import NonAnnualWindow, SuspectEmpty, split_modules
from src.comps import live

FIX = Path(__file__).parent / "fixtures" / "comps"
SOLD = (FIX / "sold_heineken_2026-09-25.ndjson").read_text()
ACTIVE = (FIX / "active_heineken_2026-09-25.ndjson").read_text()
SOLD_ZERO = (FIX / "sold_zero_2026-09-25.ndjson").read_text()
PAST_END = (FIX / "sold_past_end_2026-09-25.ndjson").read_text()

HEINEKEN_IDS = ["116782969297", "158271810080", "267646832976",
                "358331808639", "406697668711"]


def synthetic_sold(n_rows: int, start_id: int = 1, total_sold: int = 999,
                   date: str = "Sep 1, 2026") -> str:
    """A sold API body in the real nesting (row shape from the fixture)."""
    mods = split_modules(SOLD)
    results = next(m for m in mods if m["_type"] == "SearchResultsModule")
    template = results["results"][1]
    rows = []
    for i in range(n_rows):
        r = json.loads(json.dumps(template))
        r["listing"]["itemId"]["value"] = str(start_id + i)
        r["listing"]["title"]["textSpans"][0]["text"] = f"Synthetic sold listing {start_id + i}"
        r["datelastsold"]["textSpans"][0]["text"] = date
        rows.append(r)
    results["results"] = rows
    body = "\n".join(json.dumps(m) for m in mods)
    return body.replace('"text": "5"', f'"text": "{total_sold}"', 1)


class FakeSession:
    """Stands in for ResearchSession; answers by (tab, offset)."""
    pages: dict = {}
    requests: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def get(self, path):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        FakeSession.requests.append(q)
        key = (q["tabName"][0], int(q["offset"][0]))
        if key not in FakeSession.pages:
            raise AssertionError(f"unexpected request {key}")
        return FakeSession.pages[key]


@pytest.fixture
def fake_session(monkeypatch):
    FakeSession.pages = {("ACTIVE", 0): ACTIVE}
    FakeSession.requests = []
    monkeypatch.setattr(live, "ResearchSession", FakeSession)
    return FakeSession


def fixed_window(monkeypatch):
    monkeypatch.setattr(live, "year_window", lambda now=None: (
        1758800000000, 1790336000000, "Sep 25, 2025 – Sep 25, 2026"))


@pytest.fixture(autouse=True)
def _pinned_window(monkeypatch):
    fixed_window(monkeypatch)


# --- requests ------------------------------------------------------------------

class TestRequests:
    def test_sold_request_pins_dates_and_both_modules(self):
        path = live.search_path("heineken special dark mirror", "SOLD", 0, 50,
                                None, (1, 2))
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        assert q["startDate"] == ["1"] and q["endDate"] == ["2"]
        assert q["modules"] == ["aggregates", "searchResults"]
        assert q["keywords"] == ["heineken special dark mirror"]

    def test_keywords_are_encoded_not_just_space_swapped(self):
        path = live.search_path('a&b #1 "x"', "SOLD")
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        assert q["keywords"] == ['a&b #1 "x"']

    def test_unknown_condition_is_refused_before_io(self):
        from src.comps import UnknownConditionId
        with pytest.raises(UnknownConditionId):
            live.search_path("q", "SOLD", condition_id=42)


# --- pagination ----------------------------------------------------------------

class TestMarketWalk:
    def test_one_short_page(self, fake_session):
        fake_session.pages[("SOLD", 0)] = SOLD
        m = live.read_market("heineken special dark mirror")
        assert len(m.sold.rows) == 5 and not m.sold.truncated
        assert m.active.total_active == 19
        assert set(m.raw) == {"sold_p0.ndjson", "active.ndjson"}
        assert [r["tabName"][0] for r in fake_session.requests] == [
            "SOLD", "ACTIVE"]

    def test_short_last_page_ends_the_walk(self, fake_session):
        fake_session.pages[("SOLD", 0)] = synthetic_sold(50, 1, 57)
        fake_session.pages[("SOLD", 50)] = synthetic_sold(7, 51, 57)
        m = live.read_market("q")
        assert m.sold.sold_units == 57 and not m.sold.truncated

    def test_exact_multiple_of_50_ends_on_the_page_past_the_end(
            self, fake_session):
        fake_session.pages[("SOLD", 0)] = synthetic_sold(50, 1, 50)
        fake_session.pages[("SOLD", 50)] = PAST_END
        m = live.read_market("q")
        assert m.sold.sold_units == 50 and not m.sold.truncated
        assert not m.sold.genuine_zero

    def test_the_cap_marks_a_floor(self, fake_session):
        for p in range(12):
            fake_session.pages[("SOLD", p * 50)] = synthetic_sold(50, p * 50 + 1)
        m = live.read_market("q")
        assert m.sold.sold_units == 600 and m.sold.truncated

    def test_a_genuine_zero_market_does_not_page(self, fake_session):
        fake_session.pages[("SOLD", 0)] = SOLD_ZERO
        m = live.read_market("q")
        assert m.sold.genuine_zero and m.sold.sold_units == 0

    def test_a_silent_empty_first_page_refuses(self, fake_session):
        body = "\n".join(json.dumps(x) for x in split_modules(SOLD_ZERO)
                         if x["_type"] != "PageErrorModule")
        fake_session.pages[("SOLD", 0)] = body
        with pytest.raises(SuspectEmpty):
            live.read_market("q")


# --- comp_report -----------------------------------------------------------------

def verdicts_all_but_round(ident, titles):
    return [{"index": i,
             "verdict": "not_comp" if "Round" in t else "comp",
             "reason": "round, not rectangular" if "Round" in t else "same mirror"}
            for i, t in enumerate(titles)]


@pytest.fixture
def heineken(fake_session, monkeypatch):
    fake_session.pages[("SOLD", 0)] = SOLD
    monkeypatch.setattr(live, "select_comps", verdicts_all_but_round)
    return fake_session


class TestCompReport:
    def test_screened_comps_carry_prices_and_links(self, heineken):
        out = live.comp_report("Heineken Special Dark mirror 17x14",
                               "heineken special dark mirror")
        sel = out["comp_selection"]
        assert sel["comp_units"] == 4 and sel["excluded_count"] == 1
        assert sel["comp_price_band"] == [15.0, 28.34]
        assert sel["comp_price_stats"]["median"] == pytest.approx(24.98, abs=0.01)
        assert sel["comp_landed_stats"]["n"] == 4
        assert all(c["price"] is not None and c["url"].startswith(
            "https://www.ebay.com/itm/") for c in sel["comps"])
        assert sel["excluded"][0]["reason"] == "round, not rectangular"

    def test_market_figures(self, heineken):
        out = live.comp_report("id", "q")
        assert out["sold_units_365d"] == 5 and out["active_now"] == 19
        assert out["absorption"] == 0.26
        assert out["months_of_supply"] == 45.6
        assert out["sold_cross_check"]["verdict"] == "match"
        assert out["sold_price_range_unfiltered"] == [15.0, 45.0]
        assert out["active_avg_price"] == 45.38
        assert out["window"] == "Sep 25, 2025 – Sep 25, 2026"
        assert "filter chips do not" in out["scope_note"]

    def test_lowest_active_asks_are_sorted_with_links(self, heineken):
        asks = live.comp_report("id", "q")["active_lowest_asks"]
        prices = [a["price"] for a in asks]
        assert prices == sorted(prices) and all(a["url"] for a in asks)

    def test_rows_only_on_request(self, heineken):
        assert "sold_rows" not in live.comp_report("id", "q")
        rows = live.comp_report("id", "q", include_rows=True)["sold_rows"]
        assert [r["item_id"] for r in rows] == HEINEKEN_IDS
        assert {r["verdict"] for r in rows} == {"comp", "not_comp"}

    def test_selection_failure_is_stated_unfiltered(self, heineken,
                                                    monkeypatch):
        monkeypatch.setattr(live, "select_comps", lambda i, t: None)
        out = live.comp_report("id", "q", include_rows=True)
        assert out["comp_selection"].startswith("UNAVAILABLE")
        assert "verdict" not in out["sold_rows"][0]

    def test_a_hole_in_the_verdicts_is_a_whole_set_failure(self, heineken,
                                                          monkeypatch):
        def holey(ident, titles):
            v = verdicts_all_but_round(ident, titles)
            v[2] = None
            return v
        monkeypatch.setattr(live, "select_comps", holey)
        assert live.comp_report("id", "q")["comp_selection"].startswith(
            "UNAVAILABLE")

    def test_evidence_is_the_raw_api_bodies(self, heineken, tmp_path):
        out = live.comp_report("id", "q", evidence_dir=tmp_path)
        files = out["evidence"]["api_responses"]
        assert Path(files["sold_p0"]).read_text() == SOLD
        assert Path(files["active"]).read_text() == ACTIVE
        assert "screenshots" not in out["evidence"]

    def test_condition_scope_is_stated(self, heineken):
        out = live.comp_report("id", "q", condition_id=3000)
        assert out["condition_scope"] == {"condition_id": 3000,
                                          "label": "Used"}
        assert heineken.requests[0]["conditionId"] == ["3000"]


class TestWindowRefusal:
    def test_a_sale_outside_the_window_refuses_both_tools(self, fake_session):
        fake_session.pages[("SOLD", 0)] = synthetic_sold(3, date="Jan 2, 2024")
        with pytest.raises(NonAnnualWindow):
            live.comp_report("id", "q")
        from scripts import comps_mcp_server
        with pytest.raises(NonAnnualWindow):
            comps_mcp_server.ebay_absorption("q")


class TestAbsorptionTool:
    def test_the_cheap_pass_makes_no_model_call(self, fake_session,
                                                monkeypatch):
        fake_session.pages[("SOLD", 0)] = SOLD

        def boom(*a):
            raise AssertionError("absorption must not call the model")
        monkeypatch.setattr(live, "select_comps", boom)
        from scripts import comps_mcp_server
        out = comps_mcp_server.ebay_absorption("heineken special dark mirror")
        assert out["sold_units_365d"] == 5 and out["active_now"] == 19
        assert out["channel"] == "eBay only — not store or other channels"
