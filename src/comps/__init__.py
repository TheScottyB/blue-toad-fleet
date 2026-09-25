"""
eBay comp analysis — the pure layer.

Parses Seller Hub Product-Research **JSON API** responses
(``/sh/research/api/search?...&modules=aggregates&modules=searchResults``,
NDJSON — one module per line) into typed rows and aggregates, and computes
the one metric the operator defined:

    ebay_velocity = sold_units_last_365_days / active_listings_now

An absorption rate — how much of the standing eBay supply clears in a year.
Channel-specific by design: it is the velocity of the item ON EBAY, not in the
store or any other channel, and days-on-market per listing is explicitly not
computed anywhere in this module.

Why the API and not the rendered page (rewritten 2026-09-25): the page reader
scraped ``document.body.innerText`` with positional regexes, and eBay's
formatting drifted underneath it without an error — row prices became
``$ 45.00`` (space) so every comp price parsed as None and the price band was
empty on every run; the sold range switched to an en dash; the quantity anchor
missed ``eBay shipping`` rows. The API carries the same figures as NAMED
fields, so a format change breaks one money parser loudly instead of a row
layout silently.

Guards kept from docs/PLAYBOOK-ebay-velocity.md, each of which otherwise
produces a WRONG NUMBER rather than an error:

  - An empty result set without eBay's own "No … results found" message is
    SUSPECT (raise), never "sold 0".
  - ``Total sold``/``itemssold`` is UNITS, not a lot size; the numerator sums
    units, never counts rows.
  - The window must be a year. The API echoes no date line, so the request
    sends explicit startDate/endDate (``dayRange`` alone is a label, not the
    data — measured 2026-09-25: 2 rows without the dates vs 5 with) and every
    returned sale date must fall inside the requested window.
  - A signin/challenge page (HTML, not NDJSON) is refused before any number
    is read off it.

A ``PageErrorModule`` with severity ERROR rides along on every SOLD response,
including the exact request eBay's own page makes (measured 2026-09-25); it is
noise unless it carries a message. Seller Hub UI filter chips do NOT scope API
reads — only URL params do (measured 2026-09-25, sharpener query: 305
unfiltered / 274 conditionId=3000 / 24 conditionId=1000 while the UI showed a
sticky Used chip).

No I/O and no model calls in this module — that is src/comps/live.py's job.
"""

from __future__ import annotations

import datetime as _dt
import json as _json
import re
import statistics
from dataclasses import dataclass, field

__all__ = [
    "ChallengePage", "SuspectEmpty", "NonAnnualWindow", "UnknownConditionId",
    "SoldRow", "SoldPage", "ActiveRow", "ActivePage",
    "money", "money_range", "split_modules", "aggregates",
    "parse_sold_response", "parse_active_response", "merge_sold_pages",
    "absorption", "months_of_supply", "window_days", "window_label",
    "require_annual_window", "CONDITION_IDS", "require_known_condition",
    "api_total_sold", "sold_cross_check", "price_stats",
]


class ChallengePage(RuntimeError):
    """The response is a bot-challenge or signin page, not research data."""


class SuspectEmpty(RuntimeError):
    """Zero rows without eBay's own zero-results message, or no results
    module at all. Treating it as a real zero computes absorption 0 for a
    market that may be perfectly healthy."""


class UnknownConditionId(ValueError):
    """A conditionId the research API would silently ignore.

    Measured 2026-08-29: conditionId=0 and =999999 both fell back to the
    default scope while looking obedient. Only ids in CONDITION_IDS are ever
    sent."""


class NonAnnualWindow(RuntimeError):
    """The sold window is not a year, or the data does not honour it.

    The numerator is DEFINED per 365 days; a 30-day window flowing into
    ``sold_units_365d`` understates absorption ~12x (playbook G1)."""


_CHALLENGE = re.compile(
    r"pardon our interruption|security measure|captcha|verify you are human"
    r"|sign in or register|<html", re.I)
_MONEY = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
_ZERO_MSG = re.compile(r"No (?:sold|active) results found", re.I)
_DATE_FMT = "%b %d, %Y"


# --- primitives --------------------------------------------------------------

def money(text: str | None) -> float | None:
    """First dollar amount in ``text``, spaced or not (``$ 45.00``,
    ``$45.00``, ``+$ 12.80 shipping``, ``$ 6,508.70``). None when absent —
    ``-`` and ``- - -`` are eBay's "no value", never zero."""
    if not text:
        return None
    m = _MONEY.search(text)
    return float(m.group(1).replace(",", "")) if m else None


def money_range(text: str | None) -> tuple[float | None, float | None]:
    """``$ 15.00 - $ 45.00`` / ``$15.00 – $45.00`` → (15.0, 45.0). Any
    separator; exactly two amounts or (None, None)."""
    amounts = [float(a.replace(",", "")) for a in _MONEY.findall(text or "")]
    return (amounts[0], amounts[1]) if len(amounts) == 2 else (None, None)


def _shipping(text: str | None) -> float | None:
    """Shipping cell: ``Free shipping`` is 0.0, an amount is itself, and
    anything else (``-``, missing) is unknown."""
    if not text:
        return None
    if "free" in text.lower() and money(text) is None:
        return 0.0
    return money(text)


def _int(text: str | None) -> int | None:
    m = re.search(r"\d[\d,]*", text or "")
    return int(m.group(0).replace(",", "")) if m else None


def _text(node) -> str | None:
    """The visible text of a TextualDisplay-shaped node, or None."""
    if not isinstance(node, dict):
        return None
    spans = node.get("textSpans")
    if isinstance(spans, list):
        parts = [s.get("text", "") for s in spans if isinstance(s, dict)]
        joined = "".join(p for p in parts if p)
        return joined or None
    if "text" in node:
        return _text(node["text"]) if isinstance(node["text"], dict) else node["text"]
    return None


def _get(node, *path):
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


# --- response structure ------------------------------------------------------

def split_modules(body: str) -> list[dict]:
    """The NDJSON body as a list of module dicts.

    A body that is not NDJSON — an HTML signin redirect, a bot wall — is a
    ChallengePage: no number on it is a comp."""
    modules: list[dict] = []
    for line in (body or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = _json.loads(line)
        except ValueError:
            if _CHALLENGE.search(line):
                raise ChallengePage(
                    "the research API answered with a challenge or signin "
                    "page — sign the dedicated Chrome in to Seller Hub")
            raise ChallengePage(
                f"the research API answered with non-JSON ({line[:80]!r}) — "
                "not research data")
        if isinstance(obj, dict):
            modules.append(obj)
    if not modules:
        raise SuspectEmpty("empty response body from the research API")
    return modules


def _module(modules: list[dict], suffix: str) -> dict | None:
    return next((m for m in modules
                 if str(m.get("_type", "")).endswith(suffix)), None)


def _messages(modules: list[dict]) -> list[str]:
    out = []
    for m in modules:
        if m.get("_type") == "PageErrorModule":
            for msg in m.get("messages") or []:
                t = _text(msg)
                if t:
                    out.append(t)
    return out


def aggregates(modules: list[dict]) -> dict[str, str]:
    """The aggregate strip as {header: value text}, exactly as eBay labels
    it ("Avg sold price", "Total sold", "Total active listings", …)."""
    agg = _module(modules, "ResearchAggregateModule")
    out: dict[str, str] = {}
    for section in (agg or {}).get("sections") or []:
        for item in section.get("dataItems") or []:
            label, value = _text(item.get("header")), _text(item.get("value"))
            if label and value is not None:
                out[label] = value
    return out


# --- rows and pages ----------------------------------------------------------

@dataclass(frozen=True)
class SoldRow:
    title: str
    price: float | None
    qty: int
    date: str | None
    item_id: str | None = None
    shipping: float | None = None     # 0.0 = free; None = not shown
    total_sales: float | None = None
    image: str | None = None

    @property
    def url(self) -> str | None:
        return f"https://www.ebay.com/itm/{self.item_id}" if self.item_id else None

    @property
    def landed(self) -> float | None:
        if self.price is None or self.shipping is None:
            return None
        return round(self.price + self.shipping, 2)


@dataclass(frozen=True)
class ActiveRow:
    title: str
    price: float | None = None
    shipping: float | None = None
    item_id: str | None = None
    start_date: str | None = None
    watchers: int | None = None

    @property
    def url(self) -> str | None:
        return f"https://www.ebay.com/itm/{self.item_id}" if self.item_id else None


@dataclass
class SoldPage:
    window: str | None
    rows: list[SoldRow] = field(default_factory=list)
    avg_price: float | None = None
    price_low: float | None = None
    price_high: float | None = None
    avg_shipping: float | None = None
    total_sellers: int | None = None
    # eBay's own "Total sold" aggregate over the whole result set — the
    # independent figure the row walk is cross-checked against.
    total_sold: int | None = None
    genuine_zero: bool = False
    # Set by the pagination walk: True means the page cap stopped the walk
    # with the last page still full, so rows and sold_units are a FLOOR.
    truncated: bool = False

    @property
    def sold_units(self) -> int:
        """The numerator. Units, never rows."""
        return sum(r.qty for r in self.rows)

    @property
    def landed_avg(self) -> float | None:
        """What a buyer actually pays. On the sharpener corpus shipping was
        49% of the item price; a resale estimate off the item price alone
        understates the market by a third."""
        if self.avg_price is None or self.avg_shipping is None:
            return None
        return round(self.avg_price + self.avg_shipping, 2)


@dataclass
class ActivePage:
    total_active: int | None
    rows: list[ActiveRow] = field(default_factory=list)
    avg_price: float | None = None
    price_low: float | None = None
    price_high: float | None = None
    avg_shipping: float | None = None


def _image(listing: dict) -> str | None:
    url = _get(listing, "image", "URL")
    if not url:
        return None
    return "https:" + url if url.startswith("//") else url


def _sold_row(r: dict) -> SoldRow | None:
    listing = r.get("listing") or {}
    title = _text(listing.get("title"))
    if not title:
        return None
    return SoldRow(
        title=title,
        price=money(_text(_get(r, "avgsalesprice", "avgsalesprice"))),
        qty=max(1, _int(_text(r.get("itemssold"))) or 1),
        date=_text(r.get("datelastsold")),
        item_id=_get(listing, "itemId", "value"),
        shipping=_shipping(_text(_get(r, "avgshipping", "avgshipping"))
                           or _text(_get(r, "avgsalesprice", "averageshipping"))),
        total_sales=money(_text(r.get("totalsales"))),
        image=_image(listing),
    )


def _active_row(r: dict) -> ActiveRow | None:
    listing = r.get("listing") or {}
    title = _text(listing.get("title"))
    if not title:
        return None
    return ActiveRow(
        title=title,
        price=money(_text(_get(r, "listingPrice", "listingPrice"))),
        shipping=_shipping(_text(_get(r, "listingPrice", "listingShipping"))),
        item_id=_get(listing, "itemId", "value"),
        start_date=_text(r.get("startDate")),
        watchers=_int(_text(r.get("watchers"))),
    )


def parse_sold_response(body: str, window: str | None = None) -> SoldPage:
    """ONE sold API page. ``window`` is the window the request pinned (the
    API echoes none); it is carried onto the page for the annual guard."""
    modules = split_modules(body)
    results = _module(modules, "SearchResultsModule")
    if results is None:
        raise SuspectEmpty(
            "sold response has no SearchResultsModule — the request was "
            "malformed or the API changed shape, NOT a real zero")
    rows = [row for row in map(_sold_row, results.get("results") or []) if row]
    if not rows:
        if any(_ZERO_MSG.search(m) for m in _messages(modules)):
            return SoldPage(window=window, genuine_zero=True)
        raise SuspectEmpty(
            "zero sold rows and no 'No sold results found' message — "
            "unloaded or malformed response, NOT a real zero")
    agg = aggregates(modules)
    low, high = money_range(agg.get("Sold price range"))
    return SoldPage(
        window=window, rows=rows,
        avg_price=money(agg.get("Avg sold price")),
        price_low=low, price_high=high,
        avg_shipping=money(agg.get("Avg shipping")),
        total_sellers=_int(agg.get("Total sellers")),
        total_sold=_int(agg.get("Total sold")),
    )


def merge_sold_pages(first: SoldPage, later: list[SoldPage]) -> SoldPage:
    """Page one's aggregates and window, every page's rows."""
    for page in later:
        first.rows.extend(page.rows)
    return first


def parse_active_response(body: str) -> ActivePage:
    modules = split_modules(body)
    results = _module(modules, "SearchResultsModule")
    agg = aggregates(modules)
    # The denominator comes from eBay's own aggregate, never the row count:
    # rows are capped by `limit`, the aggregate is the whole market.
    total = _int(agg.get("Total active listings"))
    rows = [row for row in map(_active_row, (results or {}).get("results") or [])
            if row]
    if total is None and not rows:
        if any(_ZERO_MSG.search(m) for m in _messages(modules)):
            return ActivePage(total_active=0)
        raise SuspectEmpty(
            "no 'Total active listings' figure and no rows — malformed "
            "response, not a real zero")
    low, high = money_range(agg.get("Listing price range"))
    return ActivePage(
        total_active=total if total is not None else len(rows),
        rows=rows,
        avg_price=money(agg.get("Avg listing price")),
        price_low=low, price_high=high,
        avg_shipping=money(agg.get("Avg shipping")),
    )


# --- the window --------------------------------------------------------------

_WINDOW_DATES = re.compile(r"(\w{3} \d+, \d{4})\s*[–-]\s*(\w{3} \d+, \d{4})")


def window_label(start: _dt.date, end: _dt.date) -> str:
    return f"{start.strftime('%b %-d, %Y')} – {end.strftime('%b %-d, %Y')}"


def _parse_window(window: str | None):
    m = _WINDOW_DATES.search(window or "")
    if not m:
        return None
    try:
        return (_dt.datetime.strptime(m.group(1), _DATE_FMT).date(),
                _dt.datetime.strptime(m.group(2), _DATE_FMT).date())
    except ValueError:
        return None


def window_days(window: str | None) -> int | None:
    """Days spanned by a ``Mon D, YYYY – Mon D, YYYY`` window, or None."""
    span = _parse_window(window)
    return (span[1] - span[0]).days if span else None


def require_annual_window(page: SoldPage) -> None:
    """Refuse a sold read that is not a year of data.

    Two checks: the window must span 364–366 days (a span containing Feb 29
    is 366 and still a year), and every sale date the API returned must fall
    inside it (±1 day for timezone edges) — the data-level proof that the
    pinned dates were honoured, since the API prints no window of its own.
    A genuine zero carries no rows and passes on the span alone."""
    span = _parse_window(page.window)
    days = (span[1] - span[0]).days if span else None
    if days is None or not 364 <= days <= 366:
        if page.genuine_zero and days is None:
            return
        shown = "unreadable" if days is None else f"{days} days"
        raise NonAnnualWindow(
            f"sold window {page.window!r} is {shown}, not the 365-day "
            "window the metric is defined on (playbook G1)")
    lo = span[0] - _dt.timedelta(days=1)
    hi = span[1] + _dt.timedelta(days=1)
    for row in page.rows:
        if not row.date:
            continue
        try:
            sold_on = _dt.datetime.strptime(row.date, _DATE_FMT).date()
        except ValueError:
            continue
        if not lo <= sold_on <= hi:
            raise NonAnnualWindow(
                f"row {row.item_id or row.title[:40]!r} sold {row.date}, "
                f"outside the requested window {page.window!r} — the API "
                "did not honour the pinned dates")


# --- the metric --------------------------------------------------------------

def absorption(sold_units: int, active_now: int) -> float | None:
    """sold units per year over standing supply. None when there is no
    standing supply — the caller must say "no standing supply on eBay", not
    print infinity on a sheet."""
    if active_now <= 0:
        return None
    return round(sold_units / active_now, 2)


def months_of_supply(sold_units: int, active_now: int) -> float | None:
    """12 * active / sold — months the standing supply would take to clear.

    Computed from the raw counts, never from the rounded absorption rate:
    12 / round(rate, 2) printed 400 months where the true figure was 474
    (RG-0144 windsor read, 2026-08-29). None when either side is zero."""
    if sold_units <= 0 or active_now <= 0:
        return None
    return round(12.0 * active_now / sold_units, 1)


def price_stats(values: list[float]) -> dict | None:
    """n / min / p25 / median / p75 / max over the given prices, or None.

    Quartiles use the inclusive method so a two-comp band reads as its own
    endpoints rather than extrapolating past them."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        q1 = med = q3 = vals[0]
    else:
        q1, med, q3 = statistics.quantiles(vals, n=4, method="inclusive")
    return {"n": len(vals), "min": vals[0], "p25": round(q1, 2),
            "median": round(med, 2), "p75": round(q3, 2), "max": vals[-1]}


# --- scope -------------------------------------------------------------------

CONDITION_IDS = {
    1000: "New",
    1500: "New other",
    1750: "New with defects",
    2000: "Certified refurbished",
    2500: "Seller refurbished",
    3000: "Used",
    4000: "Very Good",
    5000: "Good",
    6000: "Acceptable",
    7000: "For parts or not working",
}


def require_known_condition(condition_id: int | None) -> str | None:
    """The label for a known conditionId; None (no filter) passes through.
    An unknown id is silently ignored server-side, so it is refused here,
    before any I/O."""
    if condition_id is None:
        return None
    label = CONDITION_IDS.get(condition_id)
    if label is None:
        raise UnknownConditionId(
            f"conditionId {condition_id} is not a known eBay condition id "
            "— the server silently ignores unknown ids and serves "
            "default-scope data (measured 2026-08-29), so it is refused")
    return label


# --- cross-check ---------------------------------------------------------------

def api_total_sold(ndjson_text: str) -> int | None:
    """'Total sold' from an api/search NDJSON body, or None — absence,
    never a guessed zero. Walks the aggregate module generically so a
    container rename does not silently break it."""
    def walk(node):
        if isinstance(node, dict):
            yield node
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    for line in (ndjson_text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            module = _json.loads(line)
        except ValueError:
            continue
        if not isinstance(module, dict) \
                or module.get("_type") != "ResearchAggregateModule":
            continue
        for node in walk(module):
            try:
                label = node["header"]["textSpans"][0]["text"]
            except (TypeError, LookupError):
                continue
            if label != "Total sold":
                continue
            try:
                raw = node["value"]["textSpans"][0]["text"]
                return int(raw.replace(",", ""))
            except (TypeError, LookupError, ValueError):
                return None
    return None


def sold_cross_check(page_units: int, truncated: bool,
                     api_total: int | None) -> dict:
    """The row walk's unit total against eBay's own Total sold aggregate.

    Two independent parse paths over the market (row-by-row units vs the
    server's aggregate); disagreement on an untruncated walk means one is
    wrong — or a sale landed between page reads — and the reader must see
    it. A truncated walk is a floor, so anything up to the total is
    consistent. An unreadable total is stated, never hidden."""
    out = {"api_total_sold": api_total, "page_units": page_units}
    if api_total is None:
        out["verdict"] = ("UNAVAILABLE — aggregate Total sold unreadable, "
                          "row figure uncorroborated")
    elif truncated:
        out["verdict"] = ("consistent floor" if page_units <= api_total else
                          f"MISMATCH — walked {page_units} units but the "
                          f"API says the whole market is {api_total}")
    elif page_units == api_total:
        out["verdict"] = "match"
    else:
        out["verdict"] = (f"MISMATCH — row walk {page_units} vs API "
                          f"{api_total}; one is wrong, or a sale landed "
                          "between the page reads")
    return out
