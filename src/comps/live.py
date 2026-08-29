"""
eBay comp analysis — the live layer.

Everything here touches the outside world: the dedicated CDP Chrome for page
text and screenshot evidence, and Vertex for intelligent comp selection. The
pure parsing and arithmetic live in src/comps/__init__.py and are what the
unit tests cover; this layer is deliberately thin plumbing around them.

Data path: the SAME dedicated Chrome profile scripts/cdp_capture.py uses
(remote debugging on 127.0.0.1:9222, profile ~/.btf-chrome-profile, signed in
to Seller Hub once by the operator). Real Chrome is the only browser eBay does
not bot-block, and CDP is the only route that puts pixels on disk — see
cdp_capture's docstring for the four mechanisms that failed first.

Intelligent comp selection: the base search is keywords, and keywords lie. A
"Boston Champion pencil sharpener" query returns replacement cutters, parts
lots and a "Boston Champion Style" that says in its own title it is not one; a
Sega Nomad query returns shells, screens and repair services. The seller could
read every row and throw the junk out — he will not, at an hour per lot, which
makes it the same bottleneck this project exists to remove. So a model reads
the lot's identification against each row title and answers the only question
that matters: is this THAT item? Verdicts are yes / no / unsure, and unsure is
an honest answer — it is excluded from the priced band and kept in absorption,
matching the playbook's finding that absorption survives a dirty comp set
(2.14 raw vs 2.15 comp-only on the sharpener) while the price band does not.

The absorption figure is CHANNEL-SPECIFIC: it is the velocity of the item on
eBay, not in the store or any other channel. Present it as such, always.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
from pathlib import Path

import websockets

from scripts.cdp_capture import capture, close_tab, open_tab
from src.comps import (ActivePage, SoldPage, absorption, months_of_supply,
                       parse_active_page, parse_sold_page)

_BASE = ("https://www.ebay.com/sh/research?marketplace=EBAY-US"
         "&categoryId=0&offset={offset}&limit={limit}&tabName={tab}"
         "&keywords={q}")
_SOLD_PAGE_LIMIT = 50   # >50 silently renders zero rows on SOLD (playbook G2)
_ACTIVE_LIMIT = 200     # works on ACTIVE, returns the whole set in one read
_MAX_SOLD_PAGES = 12    # 600 listings; past that the query is too broad to comp


def _year_window_ms(now: _dt.datetime | None = None) -> tuple[int, int]:
    now = now or _dt.datetime.now()
    start = now - _dt.timedelta(days=365)
    return int(start.timestamp() * 1000), int(now.timestamp() * 1000)


def _sold_url(q: str, offset: int) -> str:
    s, e = _year_window_ms()
    return (_BASE.format(offset=offset, limit=_SOLD_PAGE_LIMIT, tab="SOLD",
                         q=q.replace(" ", "+"))
            + f"&dayRange=365&startDate={s}&endDate={e}")


def _active_url(q: str) -> str:
    return _BASE.format(offset=0, limit=_ACTIVE_LIMIT, tab="ACTIVE",
                        q=q.replace(" ", "+"))


async def _read_text(url: str, wait: float = 8.0) -> str:
    """``document.body.innerText`` of the loaded page, via the CDP Chrome."""
    tab = open_tab(url)
    try:
        await asyncio.sleep(wait)
        async with websockets.connect(tab["webSocketDebuggerUrl"],
                                      max_size=64 * 1024 * 1024) as ws:
            await ws.send(json.dumps({
                "id": 1, "method": "Runtime.evaluate",
                "params": {"expression": "document.body?.innerText || ''",
                           "returnByValue": True}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == 1:
                    return msg["result"]["result"].get("value", "")
    finally:
        close_tab(tab["id"])


def read_sold(query: str) -> SoldPage:
    """Walk every SOLD page for the 365-day window and merge the rows.

    Pages until a short page (the site has no next-marker and no row total),
    keeps the window and aggregates from page one, and lets page one's
    SuspectEmpty/ChallengePage guards propagate — a silent empty must never
    become 'sold 0'.
    """
    async def walk() -> SoldPage:
        first = parse_sold_page(await _read_text(_sold_url(query, 0)))
        if first.genuine_zero:
            return first
        merged = first
        offset = _SOLD_PAGE_LIMIT
        while (len(merged.rows) % _SOLD_PAGE_LIMIT == 0
               and offset < _MAX_SOLD_PAGES * _SOLD_PAGE_LIMIT):
            page = parse_sold_page(await _read_text(_sold_url(query, offset)))
            merged.rows.extend(page.rows)
            if len(page.rows) < _SOLD_PAGE_LIMIT:
                break
            offset += _SOLD_PAGE_LIMIT
        return merged

    return asyncio.run(walk())


async def _read_active(query: str) -> ActivePage:
    return parse_active_page(await _read_text(_active_url(query)))


def read_active(query: str) -> ActivePage:
    return asyncio.run(_read_active(query))


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


def comp_report(identification: str, query: str,
                evidence_dir: Path | None = None) -> dict:
    """The whole read for one lot: absorption, priced band, verdicts, proof.

    Absorption is computed RAW (units over the page's own active total) and,
    when selection succeeded, comp-only as a cross-check. The priced band uses
    only rows judged 'comp'. Screenshots land in evidence_dir when given, via
    the same capture path as the manual comp reports, and the returned dict
    says explicitly when selection was unavailable and when evidence capture
    failed — an absent screenshot is reported, never papered over.
    """
    stamp = _dt.datetime.now().isoformat(timespec="seconds")
    sold = read_sold(query)
    active = asyncio.run(_read_active(query))

    out: dict = {
        "identification": identification,
        "query": query,
        "captured_at": stamp,
        "channel_note": ("eBay velocity only — the rate this item sells ON "
                        "EBAY, not in the store or other channels"),
        "window_as_printed": sold.window,
        # What the filter bar claimed. Measured 2026-08-29: a sticky chip
        # can be display-only (page data matched the unfiltered API), so
        # non-empty = the page CLAIMED scope — verify before trusting the
        # figures as scoped. None = no bar printed, [] = bar printed clean.
        "filters_as_printed": {"sold": sold.filters, "active": active.filters},
        "sold_units_365d": sold.sold_units,
        "sold_listings_365d": len(sold.rows),
        "active_now": active.total_active,
        "absorption": absorption(sold.sold_units, active.total_active or 0),
        "months_of_supply": months_of_supply(
            absorption(sold.sold_units, active.total_active or 0)),
        "avg_sold_price": sold.avg_price,
        "avg_shipping": sold.avg_shipping,
        "landed_avg": sold.landed_avg,
        "genuine_zero": sold.genuine_zero,
    }

    verdicts = select_comps(identification, [r.title for r in sold.rows]) \
        if sold.rows else None
    if verdicts is None or any(v is None for v in verdicts):
        # A hole means the model never judged that row. A partially screened
        # set posing as screened drops rows from the band AND the exclusion
        # accounting with no trace — so a hole is a failure, whole-set.
        out["comp_selection"] = "UNAVAILABLE — figures above are UNFILTERED"
    else:
        comp_rows = [r for r, v in zip(sold.rows, verdicts)
                     if v and v["verdict"] == "comp"]
        excluded = [
            {"title": r.title[:80], "verdict": v["verdict"], "reason": v["reason"]}
            for r, v in zip(sold.rows, verdicts)
            if v and v["verdict"] != "comp"]
        prices = sorted(r.price for r in comp_rows if r.price is not None)
        out["comp_selection"] = {
            "comp_units": sum(r.qty for r in comp_rows),
            "excluded_count": len(excluded),
            "excluded": excluded[:20],
            "comp_price_band": ([prices[0], prices[-1]] if prices else None),
            "note": ("absorption is reported RAW by design — junk sits in "
                     "both numerator and denominator and cancels (2.14 vs "
                     "2.15 on the sharpener corpus); the price band is "
                     "comp-only because price does NOT survive a dirty set"),
        }

    if evidence_dir is not None:
        try:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            sold_png = evidence_dir / "sold_365d.png"
            active_png = evidence_dir / "active.png"
            asyncio.run(capture(_sold_url(query, 0), sold_png, False, 9.0))
            asyncio.run(capture(_active_url(query), active_png, False, 9.0))
            out["evidence"] = {"sold": str(sold_png), "active": str(active_png)}
        except Exception as e:
            out["evidence"] = f"CAPTURE FAILED: {e} — no screenshot proof exists"
    return out
