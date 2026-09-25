"""
eBay comp analysis — the live layer.

Everything here touches the outside world: the dedicated CDP Chrome (the only
browser eBay does not bot-block, profile ~/.btf-chrome-profile, signed in to
Seller Hub once by the operator) and Vertex for intelligent comp selection.
Parsing and arithmetic live in src/comps/__init__.py and are what the unit
tests cover.

Data path (rewritten 2026-09-25): ONE tab on the Seller Hub research page per
read, then same-origin ``fetch()`` calls to the research JSON API from inside
it — the exact requests eBay's own page makes. The old path opened a fresh tab
per page and slept a fixed 8 s before scraping ``innerText`` (a run took ~22 s
and the scrape silently lost every row price when eBay changed its money
formatting); an API page answers in under a second and carries named fields.

Intelligent comp selection: the base search is keywords, and keywords lie. A
model reads the lot's identification against each row title and answers the
only question that matters: is this THAT item? Verdicts are comp / not_comp /
unsure; unsure is excluded from the priced stats and kept in absorption,
matching the playbook's finding that absorption survives a dirty comp set
(2.14 raw vs 2.15 comp-only on the sharpener) while price does not.

The absorption figure is CHANNEL-SPECIFIC: it is the velocity of the item on
eBay, not in the store or any other channel. Present it as such, always.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import websockets

from src.comps import (ActivePage, ChallengePage, SoldPage, absorption,
                       merge_sold_pages, months_of_supply,
                       parse_active_response, parse_sold_response,
                       price_stats, require_annual_window,
                       require_known_condition, sold_cross_check,
                       window_label)

CDP = "http://127.0.0.1:9222"
_ORIGIN = "https://www.ebay.com"
_BOOT_URL = _ORIGIN + "/sh/research?marketplace=EBAY-US"
_SOLD_PAGE_LIMIT = 50   # >50 silently renders zero rows on SOLD (playbook G2)
_ACTIVE_LIMIT = 200     # works on ACTIVE, returns the whole set in one read
_MAX_SOLD_PAGES = 12    # 600 listings; past that the query is too broad to comp
_READY_TIMEOUT = 30.0   # seconds for the boot tab to reach a same-origin page
_FETCH_TIMEOUT = 30.0

SCOPE_NOTE = ("API request parameters only — Seller Hub UI filter chips do "
              "not scope these reads (measured 2026-09-25)")


class CDPUnavailable(RuntimeError):
    """The dedicated Chrome is not answering on the CDP port."""


# --- the CDP session ---------------------------------------------------------

def _cdp_json(path: str, method: str = "GET", timeout: float = 10) -> dict | list:
    req = urllib.request.Request(CDP + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except (urllib.error.URLError, OSError) as e:
        raise CDPUnavailable(
            f"the dedicated Chrome is not answering on {CDP} ({e}) — "
            "ops/scripts/ebay-comps starts it; or launch it with "
            "--remote-debugging-port=9222 "
            "--user-data-dir=$HOME/.btf-chrome-profile") from None


class ResearchSession:
    """One Seller Hub tab; research API reads are fetch() calls inside it.

    Same-origin fetch carries the signed-in cookies and hits the endpoint the
    page itself uses, so there is no per-read tab, no fixed sleep, and no
    rendered text to scrape. Readiness is polled (document complete on
    www.ebay.com) rather than assumed after a sleep."""

    def __init__(self) -> None:
        self._tab: dict | None = None
        self._ws = None
        self._n = 0

    async def __aenter__(self) -> "ResearchSession":
        self._tab = _cdp_json(
            "/json/new?" + urllib.parse.quote(_BOOT_URL, safe=""), method="PUT")
        self._ws = await websockets.connect(
            self._tab["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024)
        await self._wait_ready()
        return self

    async def __aexit__(self, *exc) -> None:
        try:
            if self._ws is not None:
                await self._ws.close()
        finally:
            if self._tab is not None:
                # /json/close answers plain text ("Target is closing"), not
                # JSON; closing is best-effort cleanup and never fails a read.
                try:
                    urllib.request.urlopen(
                        f"{CDP}/json/close/{self._tab['id']}", timeout=5).read()
                except (urllib.error.URLError, OSError):
                    pass

    async def _eval(self, expression: str, timeout: float) -> object:
        self._n += 1
        n = self._n
        await self._ws.send(json.dumps({
            "id": n, "method": "Runtime.evaluate",
            "params": {"expression": expression, "awaitPromise": True,
                       "returnByValue": True}}))
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"CDP evaluate did not answer in {timeout}s")
            msg = json.loads(await asyncio.wait_for(self._ws.recv(), left))
            if msg.get("id") != n:
                continue
            result = msg.get("result") or {}
            if "exceptionDetails" in result:
                raise RuntimeError(
                    "page script failed: "
                    + json.dumps(result["exceptionDetails"])[:300])
            return (result.get("result") or {}).get("value")

    async def _wait_ready(self) -> None:
        deadline = time.monotonic() + _READY_TIMEOUT
        last = None
        while time.monotonic() < deadline:
            try:
                last = await self._eval(
                    "({host: location.host, path: location.pathname, "
                    "state: document.readyState})", timeout=5)
            except (RuntimeError, TimeoutError):
                last = None
            if isinstance(last, dict) and last.get("host") == "www.ebay.com":
                if "signin" in (last.get("path") or "").lower():
                    raise ChallengePage(
                        "Seller Hub redirected to signin — sign the dedicated "
                        "Chrome in to eBay (profile ~/.btf-chrome-profile)")
                if last.get("state") in ("interactive", "complete"):
                    return
            elif isinstance(last, dict) and last.get("host") \
                    and "ebay" not in last["host"]:
                raise ChallengePage(
                    f"Seller Hub landed on {last['host']} — signin or "
                    "challenge, not research")
            await asyncio.sleep(0.25)
        raise TimeoutError(
            f"Seller Hub tab not ready after {_READY_TIMEOUT:.0f}s (last "
            f"state {last!r})")

    async def get(self, path: str) -> str:
        """GET a same-origin path; the body on 200, else a refusal."""
        expr = ("(async () => { const r = await fetch(%s, {credentials: "
                "'include', headers: {accept: 'application/json'}}); return "
                "{status: r.status, type: r.headers.get('content-type') || '', "
                "body: await r.text()}; })()" % json.dumps(path))
        res = await self._eval(expr, timeout=_FETCH_TIMEOUT)
        if not isinstance(res, dict):
            raise RuntimeError(f"fetch returned {res!r}")
        if res.get("status") in (401, 403) or "html" in res.get("type", ""):
            raise ChallengePage(
                f"research API answered {res.get('status')} "
                f"{res.get('type')} — signed out or challenged")
        if res.get("status") != 200:
            raise RuntimeError(
                f"research API answered HTTP {res.get('status')}")
        return res.get("body") or ""


# --- requests ------------------------------------------------------------------

def year_window(now: _dt.datetime | None = None) -> tuple[int, int, str]:
    """(start ms, end ms, label) for the trailing 365 days."""
    now = now or _dt.datetime.now()
    start = now - _dt.timedelta(days=365)
    return (int(start.timestamp() * 1000), int(now.timestamp() * 1000),
            window_label(start.date(), now.date()))


def search_path(query: str, tab: str, offset: int = 0, limit: int = 50,
                condition_id: int | None = None,
                window_ms: tuple[int, int] | None = None) -> str:
    """The research API path. Keywords are form-encoded (the old builder
    only swapped spaces, so '&' or '#' in a query corrupted the URL)."""
    params = [("marketplace", "EBAY-US"), ("keywords", query)]
    if window_ms is not None:
        params += [("dayRange", "365"), ("startDate", str(window_ms[0])),
                   ("endDate", str(window_ms[1]))]
    params += [("categoryId", "0"), ("offset", str(offset)),
               ("limit", str(limit)), ("tabName", tab)]
    if condition_id is not None:
        require_known_condition(condition_id)
        params.append(("conditionId", str(condition_id)))
    params += [("modules", "aggregates"), ("modules", "searchResults")]
    return "/sh/research/api/search?" + urllib.parse.urlencode(params)


def research_page_url(query: str, tab: str,
                      condition_id: int | None = None) -> str:
    """The human-facing Seller Hub page for the same read (for screenshots
    and for pasting into a report)."""
    params = [("marketplace", "EBAY-US"), ("keywords", query)]
    if tab == "SOLD":
        s, e, _ = year_window()
        params += [("dayRange", "365"), ("startDate", str(s)),
                   ("endDate", str(e))]
    params += [("categoryId", "0"), ("offset", "0"),
               ("limit", str(_SOLD_PAGE_LIMIT)), ("tabName", tab)]
    if condition_id is not None:
        require_known_condition(condition_id)
        params.append(("conditionId", str(condition_id)))
    return _ORIGIN + "/sh/research?" + urllib.parse.urlencode(params)


@dataclass
class Market:
    sold: SoldPage
    active: ActivePage
    window_ms: tuple[int, int]
    raw: dict[str, str] = field(default_factory=dict)


async def _read_market(query: str, condition_id: int | None) -> Market:
    s, e, label = year_window()
    raw: dict[str, str] = {}
    async with ResearchSession() as sess:
        body = await sess.get(search_path(query, "SOLD", 0, _SOLD_PAGE_LIMIT,
                                          condition_id, (s, e)))
        raw["sold_p0.ndjson"] = body
        first = parse_sold_response(body, window=label)
        later: list[SoldPage] = []
        if not first.genuine_zero:
            got = len(first.rows)
            offset = _SOLD_PAGE_LIMIT
            while got == _SOLD_PAGE_LIMIT:
                if offset >= _MAX_SOLD_PAGES * _SOLD_PAGE_LIMIT:
                    first.truncated = True
                    break
                body = await sess.get(search_path(
                    query, "SOLD", offset, _SOLD_PAGE_LIMIT, condition_id,
                    (s, e)))
                raw[f"sold_p{offset // _SOLD_PAGE_LIMIT}.ndjson"] = body
                page = parse_sold_response(body, window=label)
                if page.genuine_zero:
                    # An exact multiple of 50: the page past the end carries
                    # the zero message — termination, not a dead market.
                    break
                later.append(page)
                got = len(page.rows)
                offset += _SOLD_PAGE_LIMIT
        body = await sess.get(search_path(query, "ACTIVE", 0, _ACTIVE_LIMIT,
                                          condition_id))
        raw["active.ndjson"] = body
        active = parse_active_response(body)
    return Market(sold=merge_sold_pages(first, later), active=active,
                  window_ms=(s, e), raw=raw)


def read_market(query: str, condition_id: int | None = None) -> Market:
    """SOLD (every page, 365-day window pinned) + ACTIVE in one session."""
    require_known_condition(condition_id)
    return asyncio.run(_read_market(query, condition_id))


# ---------------------------------------------------------------------------
# Intelligent comp selection
# ---------------------------------------------------------------------------

COMP_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "verdict": {"type": "string",
                                "enum": ["comp", "not_comp", "unsure"]},
                    "reason": {"type": "string"},
                },
                "required": ["index", "verdict", "reason"],
            },
        },
    },
    "required": ["verdicts"],
}

_SELECT_SYSTEM = """You judge whether eBay listings are comparables for ONE \
specific item. A comparable is the same object: same product, same model, \
complete, not a part, not an accessory, not a reproduction unless the item \
itself is one, not a multi-item lot unless the item itself is one. "unsure" is \
a correct answer and is always better than a guess — an unsure row is simply \
excluded from the priced band. Judge ONLY from the title text given; invent \
nothing."""


def select_comps(identification: str, titles: list[str]):
    """Per-title comp verdicts from the appraisal-tier model, or None.

    None means the selection could not be made (no client, call failed,
    unparseable response) and the caller must report the comp set as
    UNFILTERED rather than silently pretending it was screened. A returned
    list may carry None holes for titles the model skipped; a hole is the
    same failure and the caller must treat it as one, whole-set.
    """
    try:
        from src.appraiser import AppraisalEngine
        from src.appraiser.schema import to_vertex
        from google.genai import types

        engine = AppraisalEngine()
        if engine.client is None:
            return None
        listing_block = "\n".join(f"{i}: {t}" for i, t in enumerate(titles))
        resp = engine.client.models.generate_content(
            model=engine.appraisal_model,
            contents=[f"THE ITEM:\n{identification}\n\nTHE LISTINGS:\n{listing_block}"],
            config=types.GenerateContentConfig(
                system_instruction=_SELECT_SYSTEM,
                response_mime_type="application/json",
                response_schema=to_vertex(COMP_SCHEMA),
                temperature=0.1,
            ),
        )
        verdicts = json.loads(resp.text)["verdicts"]
        by_index = {v["index"]: v for v in verdicts if 0 <= v["index"] < len(titles)}
        return [by_index.get(i) for i in range(len(titles))]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _market_figures(m: Market, condition_id: int | None) -> dict:
    """The shared absorption block of both tools, in one place."""
    sold, active = m.sold, m.active
    label = require_known_condition(condition_id)
    return {
        "window": sold.window,
        "window_source": ("requested startDate/endDate; every sale date "
                          "checked inside it"),
        "condition_scope": {
            "condition_id": condition_id,
            "label": (label if condition_id is not None
                      else "no condition filter sent — unfiltered read")},
        "scope_note": SCOPE_NOTE,
        "sold_units_365d": sold.sold_units,
        "sold_listings_365d": len(sold.rows),
        # True = the page cap stopped the walk with the last page still
        # full, so the sold figures (and absorption) are a FLOOR.
        "sold_results_truncated": sold.truncated,
        # Row-by-row units against eBay's own Total sold aggregate.
        "sold_cross_check": sold_cross_check(
            sold.sold_units, sold.truncated, sold.total_sold),
        "active_now": active.total_active,
        "absorption": absorption(sold.sold_units, active.total_active or 0),
        "months_of_supply": months_of_supply(
            sold.sold_units, active.total_active or 0),
        "genuine_zero": sold.genuine_zero,
        # Aggregates over the WHOLE result set, before comp screening.
        "avg_sold_price_unfiltered": sold.avg_price,
        "sold_price_range_unfiltered": (
            [sold.price_low, sold.price_high]
            if sold.price_low is not None else None),
        "avg_shipping_unfiltered": sold.avg_shipping,
        "landed_avg_unfiltered": sold.landed_avg,
        "active_avg_price": active.avg_price,
        "active_price_range": (
            [active.price_low, active.price_high]
            if active.price_low is not None else None),
    }


def _row_dict(r, verdict: dict | None = None) -> dict:
    d = {"item_id": r.item_id, "url": r.url, "title": r.title,
         "price": r.price, "shipping": r.shipping, "landed": r.landed,
         "qty": r.qty, "date": r.date}
    if verdict is not None:
        d["verdict"] = verdict.get("verdict")
        d["reason"] = verdict.get("reason")
    return d


def write_evidence(m: Market, evidence_dir: Path, query: str,
                   condition_id: int | None, screenshots: bool) -> dict:
    """The raw API bodies are the proof (machine-checkable, re-parseable);
    Seller Hub screenshots are optional, for a human-facing report."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, body in m.raw.items():
        p = evidence_dir / name
        p.write_text(body)
        files[name.rsplit(".", 1)[0]] = str(p)
    out: dict = {"api_responses": files}
    if screenshots:
        try:
            from scripts.cdp_capture import capture
            sold_png = evidence_dir / "sold_365d.png"
            active_png = evidence_dir / "active.png"
            asyncio.run(capture(research_page_url(query, "SOLD", condition_id),
                                sold_png, False, 9.0))
            asyncio.run(capture(research_page_url(query, "ACTIVE", condition_id),
                                active_png, False, 9.0))
            out["screenshots"] = {"sold": str(sold_png), "active": str(active_png)}
        except BaseException as e:  # capture's open_tab raises SystemExit
            if isinstance(e, KeyboardInterrupt):
                raise
            out["screenshots"] = f"CAPTURE FAILED: {e} — no screenshot exists"
    return out


def absorption_report(query: str, condition_id: int | None = None) -> dict:
    """The cheap pass: channel-specific velocity, no model call."""
    m = read_market(query, condition_id)
    require_annual_window(m.sold)
    return {"query": query,
            "channel": "eBay only — not store or other channels",
            **_market_figures(m, condition_id)}


def comp_report(identification: str, query: str,
                evidence_dir: Path | None = None,
                condition_id: int | None = None,
                screenshots: bool = False,
                include_rows: bool = False) -> dict:
    """The whole read for one lot: absorption, screened comps with prices
    and links, comp-only price stats, active competition, proof.

    Absorption is RAW (units over eBay's own active total) by design — it
    survives a dirty comp set. Price stats use only rows judged 'comp'.
    ``include_rows`` adds every sold row with its verdict (the CLI's
    --rows-out). Refuses (NonAnnualWindow) when the window is not a year or
    any sale date falls outside it."""
    stamp = _dt.datetime.now().isoformat(timespec="seconds")
    m = read_market(query, condition_id)
    require_annual_window(m.sold)
    sold, active = m.sold, m.active

    out: dict = {
        "identification": identification,
        "query": query,
        "captured_at": stamp,
        "channel_note": ("eBay velocity only — the rate this item sells ON "
                         "EBAY, not in the store or other channels"),
        **_market_figures(m, condition_id),
    }

    verdicts = select_comps(identification, [r.title for r in sold.rows]) \
        if sold.rows else None
    screened = verdicts is not None and not any(v is None for v in verdicts)
    if not screened:
        # A hole means the model never judged that row. A partially screened
        # set posing as screened drops rows from the stats AND the exclusion
        # accounting with no trace — so a hole is a failure, whole-set.
        out["comp_selection"] = "UNAVAILABLE — figures above are UNFILTERED"
    else:
        pairs = list(zip(sold.rows, verdicts))
        comp_rows = [r for r, v in pairs if v["verdict"] == "comp"]
        excluded = [(r, v) for r, v in pairs if v["verdict"] != "comp"]
        prices = [r.price for r in comp_rows if r.price is not None]
        out["comp_selection"] = {
            "comp_units": sum(r.qty for r in comp_rows),
            "comp_price_band": ([min(prices), max(prices)] if prices else None),
            "comp_price_stats": price_stats(prices),
            "comp_landed_stats": price_stats(
                [r.landed for r in comp_rows if r.landed is not None]),
            "comps": [_row_dict(r) for r in comp_rows[:25]],
            "excluded_count": len(excluded),
            "excluded": [{"title": r.title[:80], "url": r.url,
                          "price": r.price, "verdict": v["verdict"],
                          "reason": v["reason"]} for r, v in excluded[:25]],
            "note": ("absorption is RAW by design — junk sits in both "
                     "numerator and denominator and cancels (2.14 vs 2.15 on "
                     "the sharpener corpus); price stats are comp-only "
                     "because price does NOT survive a dirty set"),
        }

    cheapest = sorted((r for r in active.rows if r.price is not None),
                      key=lambda r: r.price)[:5]
    out["active_lowest_asks"] = [
        {"title": r.title[:80], "url": r.url, "price": r.price,
         "shipping": r.shipping, "listed": r.start_date} for r in cheapest]

    if include_rows:
        out["sold_rows"] = [
            _row_dict(r, v if screened else None)
            for r, v in zip(sold.rows, verdicts if screened
                            else [None] * len(sold.rows))]

    if evidence_dir is not None:
        out["evidence"] = write_evidence(m, evidence_dir, query,
                                         condition_id, screenshots)
    return out
