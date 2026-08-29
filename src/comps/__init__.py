"""
eBay comp analysis — the pure layer.

Parses Seller Hub Product-Research page text (``document.body.innerText`` as a
CDP fetch returns it) into typed rows and aggregates, and computes the one
metric the operator defined:

    ebay_velocity = sold_units_last_365_days / active_listings_now

An absorption rate — how much of the standing eBay supply clears in a year.
Channel-specific by design: it is the velocity of the item ON EBAY, not in the
store or any other channel, and days-on-market per listing is explicitly not
computed anywhere in this module.

Every guard here is a failure from docs/PLAYBOOK-ebay-velocity.md turned into
code. They all share one property: without the guard, the failure produces a
WRONG NUMBER rather than an error.

  - ``limit`` above 50 renders zero rows on the SOLD tab with no message.  An
    empty parse without the page's own "No … results found" line is therefore
    SUSPECT (raise), never "sold 0" — absorption would compute as 0 from a page
    that looks fine.
  - ``Total sold`` is UNITS, not a lot size (avg_sold_price x total_sold =
    item_sales reconciles on every multi-quantity row).  The numerator sums the
    column; counting rows undercounted by 3.5% on the sharpener corpus, with
    the entire gap on page one.
  - The date window the PAGE prints is the only authority on the window; the
    request's ``dayRange`` sets a dropdown label, not the data.
  - A challenge/signin page parses as prose, so it must be detected and
    refused before any number is read off it.

No I/O and no model calls in this module — that is src/comps/live.py's job,
keeping this layer unit-testable the way src/bidmath is.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field

__all__ = [
    "ChallengePage", "SuspectEmpty", "NonAnnualWindow", "SoldRow", "SoldPage",
    "ActiveRow", "ActivePage", "parse_sold_page", "parse_active_page",
    "parse_filters", "absorption", "months_of_supply", "window_days",
    "require_annual_window",
]


class ChallengePage(RuntimeError):
    """The text is a bot-challenge or signin page, not research data."""


class SuspectEmpty(RuntimeError):
    """Zero rows without the page's own zero-results message.

    Seen live when ``limit`` exceeds 50 on the SOLD tab: the table renders
    empty with no error and no message. Treating it as a real zero computes
    absorption 0 for a market that may be perfectly healthy.
    """


class NonAnnualWindow(RuntimeError):
    """The printed sold window is absent or is not a year (playbook G1).

    ``dayRange=365`` sets the dropdown label, not the data: the page can
    serve a 30-day window under a "Last year" control. The numerator is
    DEFINED per 365 days, so a non-annual window computes absorption up to
    ~12x wrong — the printed date line is the only authority, and a read
    whose line is missing or non-annual must refuse, never normalize.
    """


_ROW_SEP = "preview full size image"
_WINDOW = re.compile(r"(\w{3} \d+, \d{4} – \w{3} \d+, \d{4})")
_MONEY = re.compile(r"\$([\d,]+\.\d{2})")
_ZERO_MSG = re.compile(r"No (?:sold|active) results found", re.I)
_CHALLENGE = re.compile(
    r"pardon our interruption|security measure|captcha|verify you are human"
    r"|sign in or register", re.I)
_QTY_ANCHOR = re.compile(r"% Free shipping$")
_DATE = re.compile(r"^\w{3} \d+, \d{4}$")
_FILTER_COUNTED = re.compile(r"^[A-Z][A-Za-z ]* filter \(\d+ Selected\)$")
_FILTER_APPLIED = "Filter Applied"
_MORE_FILTERS = "More filters"
# The tab strip renders with or without a zero-width space between the words.
_TAB_STRIP = re.compile(r"^Sold​?Active$")
_MAX_CHIPS = 12
_MAX_CHIP_LEN = 40


def _money(text: str, label: str) -> float | None:
    m = re.search(r"\$([\d,]+\.\d{2})\s*\n" + re.escape(label), text)
    return float(m.group(1).replace(",", "")) if m else None


def _int_before(text: str, label: str) -> int | None:
    m = re.search(r"(\d+)\s*\n" + re.escape(label), text)
    return int(m.group(1)) if m else None


def _require_research_page(text: str) -> None:
    if _CHALLENGE.search(text):
        raise ChallengePage(
            "this text is a challenge or signin page, not research data — "
            "no number on it is a comp")


def parse_filters(text: str) -> list[str] | None:
    """The scope markers the page printed, as printed.

    Sticky Seller Hub filter UI survives from manual sessions (measured
    2026-08-24: a leftover Used condition chip on a live read). Measured
    2026-08-29: that chip can be a DISPLAY GHOST — the page's own data
    requests carried only the URL's params (no conditionId), and the page's
    aggregates matched the unfiltered API read, not the Used-scoped one. So
    printed markers mean "the page CLAIMS this scope"; the data may or may
    not be scoped (an explicit conditionId in the URL, by contrast, does
    scope it). Surfaced as printed: the "Filter Applied" badge, any
    "<name> filter (N Selected)" button, and the chip labels rendered
    between "More filters" and the Sold/Active tab strip. Returns [] for a
    bar with none of those, and None when no filter bar was printed at
    all — an absent bar is UNKNOWN, never "clean".
    """
    lines = [ln.strip() for ln in text.split("\n")]
    try:
        more_i = lines.index(_MORE_FILTERS)
    except ValueError:
        return None
    printed: list[str] = []
    if _FILTER_APPLIED in lines:
        printed.append(_FILTER_APPLIED)
    printed.extend(ln for ln in lines[:more_i] if _FILTER_COUNTED.match(ln))
    chips = 0
    for ln in lines[more_i + 1:]:
        if not ln:
            continue
        if _TAB_STRIP.match(ln) or len(ln) > _MAX_CHIP_LEN or chips >= _MAX_CHIPS:
            break
        printed.append(ln)
        chips += 1
    return printed


@dataclass(frozen=True)
class SoldRow:
    title: str
    price: float | None
    qty: int
    date: str | None


@dataclass(frozen=True)
class ActiveRow:
    title: str


@dataclass
class SoldPage:
    window: str | None
    rows: list[SoldRow] = field(default_factory=list)
    avg_price: float | None = None
    price_low: float | None = None
    price_high: float | None = None
    avg_shipping: float | None = None
    total_sellers: int | None = None
    genuine_zero: bool = False
    filters: list[str] | None = None
    # Set by the pagination walk, never by a single-page parse: True means
    # the page cap stopped the walk with the last page still full, so rows
    # and sold_units are a FLOOR, not the market.
    truncated: bool = False

    @property
    def sold_units(self) -> int:
        """The numerator. Units, never rows — see the module docstring."""
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
    avg_shipping: float | None = None
    filters: list[str] | None = None


def _split_rows(text: str) -> list[list[str]]:
    return [
        [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        for chunk in text.split(_ROW_SEP)[1:]
    ]


def parse_sold_page(text: str) -> SoldPage:
    _require_research_page(text)
    filters = parse_filters(text)

    if _ZERO_MSG.search(text):
        return SoldPage(window=None, genuine_zero=True, filters=filters)

    rows: list[SoldRow] = []
    for lines in _split_rows(text):
        if not lines or len(lines[0]) < 10:
            continue
        title = lines[0]
        prices = [float(m.replace(",", ""))
                  for m in _MONEY.findall("\n".join(lines))]
        qty = 1
        for i, ln in enumerate(lines):
            if _QTY_ANCHOR.search(ln) and i + 1 < len(lines):
                try:
                    qty = max(1, int(lines[i + 1]))
                except ValueError:
                    pass
                break
        date = next((ln for ln in reversed(lines) if _DATE.match(ln)), None)
        rows.append(SoldRow(title=title, price=prices[0] if prices else None,
                            qty=qty, date=date))

    if not rows:
        raise SuspectEmpty(
            "zero sold rows but no 'No sold results found' message — this is "
            "the limit>50 silent render or an unloaded page, NOT a real zero")

    win = _WINDOW.search(text)
    range_m = re.search(
        r"\$([\d,]+\.\d{2}) - \$([\d,]+\.\d{2})\s*\nSold price range", text)
    return SoldPage(
        window=win.group(1) if win else None,
        rows=rows,
        avg_price=_money(text, "Avg sold price"),
        price_low=float(range_m.group(1).replace(",", "")) if range_m else None,
        price_high=float(range_m.group(2).replace(",", "")) if range_m else None,
        avg_shipping=_money(text, "Avg shipping"),
        total_sellers=_int_before(text, "Total sellers"),
        filters=filters,
    )


def parse_active_page(text: str) -> ActivePage:
    _require_research_page(text)
    filters = parse_filters(text)

    if _ZERO_MSG.search(text):
        return ActivePage(total_active=0, filters=filters)

    rows = [ActiveRow(title=lines[0])
            for lines in _split_rows(text)
            if lines and len(lines[0]) >= 10]

    # The denominator comes from the aggregate strip the page itself prints.
    # Row count is NOT a substitute: ACTIVE renders at most `limit` rows, so a
    # 138-listing market at the default limit would count as 50.
    total = _int_before(text, "Total active listings")
    if total is None and not rows:
        raise SuspectEmpty(
            "no 'Total active listings' figure and no rows — unloaded page "
            "or challenge variant, not a real zero")
    return ActivePage(
        total_active=total,
        rows=rows,
        avg_price=_money(text, "Avg listing price"),
        avg_shipping=_money(text, "Avg shipping"),
        filters=filters,
    )


_WINDOW_DATES = re.compile(r"(\w{3} \d+, \d{4})\s*[–-]\s*(\w{3} \d+, \d{4})")


def window_days(window: str | None) -> int | None:
    """Days spanned by the window line as the page printed it, or None."""
    m = _WINDOW_DATES.search(window or "")
    if not m:
        return None
    try:
        start = _dt.datetime.strptime(m.group(1), "%b %d, %Y").date()
        end = _dt.datetime.strptime(m.group(2), "%b %d, %Y").date()
    except ValueError:
        return None
    return (end - start).days


def require_annual_window(page: SoldPage) -> None:
    """Refuse a sold read whose printed window is not a year.

    Mirrors evidence/model.py's exactly-365 check on the capture-import
    path; here 364–366 passes because a span containing Feb 29 prints 366
    days and is still a year. The genuine-zero page prints no date line at
    all, so a genuine zero is exempt — its report already states the
    absence (window None, genuine_zero True). Everything else with a
    missing or non-annual line raises rather than flowing into a figure
    labelled 365d.
    """
    if page.genuine_zero:
        return
    days = window_days(page.window)
    if days is None or not 364 <= days <= 366:
        span = "unreadable" if days is None else f"{days} days"
        raise NonAnnualWindow(
            f"printed sold window {page.window!r} is {span}, not the "
            "365-day window the metric is defined on — dayRange sets a "
            "dropdown label, not the data (playbook G1); re-request with "
            "startDate/endDate epoch ms and read the printed line")


def absorption(sold_units: int, active_now: int) -> float | None:
    """sold units per year over standing supply. None when there is no
    standing supply — the caller must say "no standing supply on eBay", not
    print infinity on a sheet."""
    if active_now <= 0:
        return None
    return round(sold_units / active_now, 2)


def months_of_supply(absorption_rate: float | None) -> float | None:
    if not absorption_rate:
        return None
    return round(12.0 / absorption_rate, 1)
