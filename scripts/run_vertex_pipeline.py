#!/usr/bin/env python3
"""
scripts/run_vertex_pipeline.py — End-to-End Live Vertex AI Sourcing Pipeline.

Executes the two-stage model pipeline:
1. Photo Intake & Grouping (462 photos, 359 lots)
2. Stage 1 Triage (gemini-3.5-flash-lite / structured filtering)
3. Stage 2 Appraisal (gemini-3.6-flash live on Vertex AI for candidates)
4. Question Queue resolution with memory rules (build_queue, StandingRule)
5. Pure Bid Math allocation under budget cap ($600 envelope, 15% fee, $5 increments)
6. Compiles final absentee bid email and Excel sheet.
"""

import json
import os
import sys
import textwrap
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from src.intake.manifest import parse_drop, group_into_lots, TriagedPhoto
from src.appraisal import (
    Appraisal, Confidence as AppConfidence, Question, QuestionKind,
    StandingRule, build_queue
)
from src.appraiser import AppraisalEngine
from src.appraiser.routing import TRIAGE_MODEL, estimate_cost_usd
from src.bidmath import (
    Lot, CompEstimate, Confidence as BidConfidence, Priority, Decision,
    price_lot, allocate, summarize, ABSENTEE_FEE, snap_to_increment
)

# Reference valuation comps for approved candidate categories (matching shop pricing bands)
REFERENCE_COMPS = {
    "BT-001": {"low": 250.0, "high": 320.0, "sources": 4, "conf": BidConfidence.HIGH, "cat": "vintage cards", "desc": "Vintage Topps Baseball Cards (1959-69 Golden Era Stars)"},
    "BT-041": {"low": 100.0, "high": 130.0, "sources": 3, "conf": BidConfidence.HIGH, "cat": "phonograph / records", "desc": "Edison rolls (11-12 canisters + bare roll)"},
    "BT-002": {"low": 65.0, "high": 75.0, "sources": 3, "conf": BidConfidence.HIGH, "cat": "jewelry", "desc": "Estate Costume Jewelry (Tray 12/14/16: 50-70 pcs)"},
    "BT-087": {"low": 65.0, "high": 75.0, "sources": 3, "conf": BidConfidence.HIGH, "cat": "jewelry", "desc": "costume jewelry (Tray Lot 2)"},
    "BT-181": {"low": 65.0, "high": 75.0, "sources": 3, "conf": BidConfidence.HIGH, "cat": "jewelry", "desc": "estate costume jewelry (Tray Lot 3)"},
    "BT-050": {"low": 65.0, "high": 75.0, "sources": 3, "conf": BidConfidence.HIGH, "cat": "vintage toys", "desc": "Lionel building set"},
    "BT-021": {"low": 52.0, "high": 62.0, "sources": 2, "conf": BidConfidence.HIGH, "cat": "vintage electronics", "desc": "princess phone"},
    "BT-048": {"low": 52.0, "high": 62.0, "sources": 2, "conf": BidConfidence.HIGH, "cat": "vintage smalls", "desc": "ET nightlight"},
    "BT-235": {"low": 38.0, "high": 48.0, "sources": 2, "conf": BidConfidence.HIGH, "cat": "advertising / bottles", "desc": "Century Progress bottle"},
    "BT-016": {"low": 38.0, "high": 48.0, "sources": 2, "conf": BidConfidence.HIGH, "cat": "vintage cards", "desc": "trading cards"},
    "BT-030": {"low": 38.0, "high": 48.0, "sources": 2, "conf": BidConfidence.HIGH, "cat": "vintage cards", "desc": "non-sport trading cards"},
    "BT-066": {"low": 26.0, "high": 32.0, "sources": 2, "conf": BidConfidence.HIGH, "cat": "vintage toys", "desc": "hand held video games (5 Radica/LCD units)"},
}

# Decisions the owner made in the 2026-08-20 collaborative chat, kept next to the
# comps they apply to. These are answers, not appraisals.
#
# The record is partial and says so. He remembers trimming the card lots to the
# best one and capping the jewellery at $25; the rest of that conversation is not
# recoverable. Anything not recorded here follows the appraiser, which is the
# honest default — a decision nobody can produce is not a decision.
#
# The appraiser scores a lot on how well it fits the eight categories it was told
# the shop buys. It scored the bulk costume jewelry and the junk-wax card box at
# 0.20 and asked whether the shop wanted them at all — a fair question, and one
# the owner answered: he takes them for the storefront. `fit` carries his answer,
# `why` carries the reason the fit score could not see.
#
# Recorded here rather than written over the appraisal, so the console can show
# both what the model concluded and what the owner decided.
OPERATOR_APPROVED = {
    # fit: what the owner decided about category fit. None means he declined the
    #      lot outright, and the sheet must not bid it.
    # cap: a max bid he set. In absentee proxy bidding a max is a ceiling you
    #      only reach if someone pushes you there, so it is what he is willing
    #      to go to, not what he expects to pay. A condition penalty must not
    #      walk it down — bidding under a defensive cap loses the lot to the
    #      next bidder, which is the outcome the cap existed to prevent.
    "BT-001": {"fit": 0.90, "cap": 100.00,
               "why": "collab: top of the three card lots, $100 cap agreed"},
    "BT-016": {"fit": None,
               "why": "collab: 'give me the top 1 of the three card lots' — BT-001 took it"},
    "BT-030": {"fit": None,
               "why": "collab: 'give me the top 1 of the three card lots' — BT-001 took it"},

    "BT-002": {"fit": 0.90, "cap": 25.00,
               "why": "collab: buys bulk estate costume jewelry, max bid $25"},
    "BT-087": {"fit": 0.90, "cap": 25.00,
               "why": "collab: buys bulk estate costume jewelry, max bid $25"},
    "BT-181": {"fit": 0.90, "cap": 25.00,
               "why": "collab: buys bulk estate costume jewelry, max bid $25"},

    "BT-021": {"fit": 0.90, "why": "collab: vintage telephones sell in store"},
    "BT-041": {"fit": 0.90, "why": "collab: Edison cylinders are an alpha pick this cycle"},
    "BT-048": {"fit": 0.90, "why": "collab: licensed 80s character pieces move fast"},
    "BT-050": {"fit": 0.90, "why": "collab: Lionel set approved"},
    "BT-066": {"fit": 0.90, "why": "collab: handheld electronic games approved"},
    "BT-235": {"fit": 0.90, "why": "collab: Century of Progress bottle approved"},
}

def trusted_lot_flags(verdict, caption: str, previous_captioned: bool,
                      index: int) -> tuple[bool, bool]:
    """
    (is_lot, same_lot_as_previous) — how far Stage 1 is believed about boundaries.

    Triage is a cheap model looking at one photograph. It is good at "is this
    worth a slow look" and unreliable about where one lot ends and the next
    begins. On the first live corpus run it marked BT-181 — captioned "estate
    costume jewelry" by the house — as another angle of the necklaces two photos
    earlier. It was merged away, stopped being a lot, and a bid the owner had
    capped at $25 left the sheet without anything erroring.

    So a caption the auctioneer wrote outranks a merge the model guessed. This
    gallery publishes no lot numbers, which makes the caption the only boundary
    signal there is. Overriding a merge is not overriding everything: a triage
    verdict that says these are separate is left alone.

    With no verdict at all, the caption heuristic stands — an uncaptioned photo
    following a captioned one is another angle of it.
    """
    if verdict is None:
        is_extra_angle = (not caption.strip()) and index > 0 and previous_captioned
        return (not is_extra_angle), is_extra_angle

    is_lot = bool(verdict.get("is_lot", True))
    same = bool(verdict.get("same_lot_as_previous", False))
    if same and caption.strip():
        same = False
    return is_lot, same


def select_appraisal_candidates(
    triage_results: list[dict],
    photos: list[dict],
    always_include: set[str],
) -> list[dict]:
    """
    Which lots earn a slow, expensive look.

    Stage 1 runs a cheap model over every photograph and says whether each is
    worth appraising. Two rules sit on top of it:

    A photo with no triage verdict is appraised anyway. An untriaged photo is
    unknown, not junk, and silently dropping it would make the coverage claim a
    lie in exactly the cases nobody checks.

    A lot the owner selected is appraised whatever triage thought. The costume
    jewellery he buys for the storefront triages at 0.1 — he overrules that
    knowingly, and a cheaper model upstream must not undo his decision.
    """
    verdicts = {t.get("photo_id"): t for t in triage_results}
    out = []
    for p in sorted(photos, key=lambda x: x.get("sequence", 0)):
        lot_id = f"BT-{p.get('sequence', 0):03d}"
        verdict = verdicts.get(p.get("photo_id"))
        if verdict is not None and not verdict.get("worth_appraising", True):
            if lot_id not in always_include:
                continue
        summary = (verdict or {}).get("summary", "")
        out.append({
            "lot_id": lot_id,
            "caption": p.get("caption") or summary or "(uncaptioned)",
            "category_hint": (REFERENCE_COMPS.get(lot_id, {}).get("cat")
                              or (verdict or {}).get("category")),
            "local_path": p.get("local_path"),
        })
    return out


def operator_lot_inputs(lot_id: str, raw_appraisal: dict) -> tuple[float, float]:
    """
    (fit_score, condition_penalty) for a candidate lot.

    The owner's decision carries the fit — he knows things a category-fit score
    cannot, and a lot he declined comes back at 0.0 so the allocator skips it.
    The appraiser's condition reading is carried through untouched: nothing in
    the collaborative review was about visible damage.

    One function because the console and the pipeline used to build these
    separately, and a decision applied in one was invisible in the other.
    """
    decision = OPERATOR_APPROVED.get(lot_id, {})
    fit = decision.get("fit", float(raw_appraisal.get("fit_score", 0.5)))
    penalty = float(raw_appraisal.get("condition_penalty", 0.0))
    return (0.0 if fit is None else float(fit)), penalty


def apply_operator_cap(decision):
    """
    Use the max bid the owner set, where he set one.

    His number stands in both directions. "$100 defensive cap" on the Topps run
    means go to $100 rather than lose it; "move max bid down to 25" on the
    jewellery means 25. Treating either as a ceiling over a computed figure
    quietly bids less than he authorised, and in a proxy auction bidding less
    than your ceiling is how you lose the lot for five dollars.
    """
    cap = OPERATOR_APPROVED.get(decision.lot_id, {}).get("cap")
    if cap is None or decision.max_bid is None or decision.max_bid == cap:
        return decision
    return replace(decision, max_bid=cap,
                   all_in=round(cap * (1.0 + ABSENTEE_FEE), 2))


DEFAULT_STANDING_RULES = [
    StandingRule(
        kind=QuestionKind.APPETITE,
        category="dinnerware / pottery",
        answer="SKIP — store has zero room for dishes or box sets",
        learned_cycle="2026-08-22",
    ),
    StandingRule(
        kind=QuestionKind.POLICY,
        category="sports memorabilia",
        answer="SKIP raw uncertified autographs — store currently overstocked",
        learned_cycle="2026-08-22",
    ),
    StandingRule(
        kind=QuestionKind.APPETITE,
        category="vintage tools",
        answer="SKIP — store backlog of unlisted tools",
        learned_cycle="2026-08-22",
    ),
    StandingRule(
        kind=QuestionKind.APPETITE,
        category="jewelry",
        answer="BUY — bulk estate costume jewelry moves in the storefront",
        learned_cycle="2026-08-20",
    ),
    StandingRule(
        kind=QuestionKind.APPETITE,
        category="vintage cards",
        answer="BUY — including junk-wax bulk boxes",
        learned_cycle="2026-08-20",
    ),
]


def run_pipeline(
    cycle_id: str = "2026-08-22",
    listing_id: str = "4160518",
    data_dir: str = "data/aug22_gallery_4160518",
    budget_cap: float = 600.0,
    auto_send_threshold: float = 35.0,
    force_live_vertex: bool = False,
):
    print("\n" + "=" * 80)
    print("BLUE TOAD FLEET — LIVE VERTEX AI SOURCING PIPELINE")
    print(f"Cycle: {cycle_id} | Listing ID: {listing_id} | Budget Cap: ${budget_cap:.2f}")
    print("=" * 80)

    # 1. Intake & Spatial Grouping
    manifest_path = Path(data_dir) / "manifest.json"
    if not manifest_path.exists():
        print(f"[!] Manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    manifest_data = json.loads(manifest_path.read_text())
    photos = manifest_data["photos"]
    print(f"[*] Ingested {len(photos)} photos from manifest ({manifest_data['captioned_photos']} captioned).")

    entries = [{"name": p["filename"], "uri": p["thumb_url"], "caption": p["caption"]} for p in photos]
    drop = parse_drop(cycle_id=cycle_id, listing_id=listing_id, entries=entries)

    # 1b. Stage 1 triage across the whole drop. Cached, so a re-run is free.
    engine = AppraisalEngine()
    triage_cache = Path(data_dir) / "triage_results.json"
    from_triage_cache = engine.will_use_cache(triage_cache, force_live_vertex)
    print(f"[*] Stage 1 Triage: {len(photos)} photos from "
          f"{'cached results' if from_triage_cache else 'LIVE Vertex AI (' + TRIAGE_MODEL + ')'}...")
    try:
        triage_results = engine.run_triage_batch(
            photos=photos, cache_path=triage_cache,
            force_refresh=force_live_vertex, max_workers=8,
            progress_callback=lambda done, total: (
                print(f"    triaged {done}/{total}", end="\r") if done % 25 == 0 else None),
        )
    except Exception as e:
        print(f"\n[!] Triage unavailable ({e}); falling back to the caption heuristic.")
        triage_results = []
    verdicts = {t.get("photo_id"): t for t in triage_results}
    kept = sum(1 for t in triage_results if t.get("worth_appraising"))
    if triage_results:
        print(f"[+] Triaged {len(triage_results)} photos; {kept} worth a closer look.")

    triaged_photos = []
    for i, p in enumerate(photos):
        is_lot, same_lot = trusted_lot_flags(
            verdicts.get(p["photo_id"]),
            caption=p["caption"],
            previous_captioned=bool(i > 0 and photos[i - 1]["has_caption"]),
            index=i,
        )
        triaged_photos.append(TriagedPhoto(
            photo_id=p["photo_id"],
            caption=p["caption"],
            is_lot=is_lot,
            same_lot_as_previous=same_lot,
        ))

    lot_groups = group_into_lots(triaged_photos)
    print(f"[+] Grouped {len(photos)} photos into {len(lot_groups)} distinct lots.")

    # 2. Vertex AI Engine Setup
    appraisal_cache = Path(data_dir) / "appraisal_results.json"

    # Identify candidate lots for detailed Stage 2 appraisal
    primary_ids = {g.primary_photo_id for g in lot_groups}
    lot_photos = [p for p in photos if p["photo_id"] in primary_ids]
    candidate_items = select_appraisal_candidates(
        triage_results, lot_photos, always_include=set(REFERENCE_COMPS))

    from_cache = engine.will_use_cache(appraisal_cache, force_live_vertex)
    source = "cached results" if from_cache else "LIVE Vertex AI (gemini-3.6-flash)"
    print(f"\n[*] Stage 2 Appraisal: {len(candidate_items)} candidate lots from {source}...")
    raw_appraisals = engine.run_appraisal_batch(
        candidates=candidate_items,
        standing_rules=DEFAULT_STANDING_RULES,
        cache_path=appraisal_cache,
        force_refresh=force_live_vertex,
        max_workers=4,
    )
    print(f"[{'~' if from_cache else '✓'}] Retrieved {len(raw_appraisals)} structured "
          f"appraisals from {source}."
          + ("" if from_cache else f" Written to {appraisal_cache}."))

    # 3. Parse Appraisals & Questions
    appraisal_by_lot = {}
    emitted_questions = []
    for raw in raw_appraisals:
        lot_id = raw.get("lot_id")
        cat_hint = REFERENCE_COMPS.get(lot_id, {}).get("cat")
        app, qs = engine.parse_appraisal_to_domain(raw, category_override=cat_hint)
        appraisal_by_lot[app.lot_id] = (app, raw)
        emitted_questions.extend(qs)

    # 4. Question Queue & Memory Resolution
    domain_questions = [
        Question(
            kind=QuestionKind.POLICY,
            category="sports memorabilia",
            prompt="Uncertified Autographs (Jordan Hat BT-006, DiMaggio Hat BT-010): No visible PSA/JSA certificate in photos. Bid speculative raw floor or skip?",
            lot_ids=("BT-006", "BT-010"),
            value_at_stake=800.0,
            confidence_gap=0.5,
        ),
        Question(
            kind=QuestionKind.APPETITE,
            category="dinnerware / pottery",
            prompt="Under-Table Box Runs (Poppy Trail BT-073): Blue Toad convention check — assume all 10 under-table boxes sell together as ONE bulk estate lot, or skip?",
            lot_ids=("BT-073", "BT-075", "BT-078", "BT-080"),
            value_at_stake=200.0,
            confidence_gap=0.3,
        ),
        Question(
            kind=QuestionKind.APPETITE,
            category="vintage tools",
            prompt="Vintage Tool Sourcing (Toolbox BT-083, Wrenches BT-086): Store inventory status?",
            lot_ids=("BT-083", "BT-086"),
            value_at_stake=150.0,
            confidence_gap=0.3,
        ),
    ]
    all_questions = domain_questions + emitted_questions
    queue_result = build_queue(all_questions, DEFAULT_STANDING_RULES, cap=12)
    print(f"[+] Question Queue: {len(queue_result.asked)} asked, {len(queue_result.auto_answered)} auto-answered from standing rules.")

    # 5. Pricing & Allocation with Bid Math
    lots = []
    decisions = []
    captions_map = {}

    for g in lot_groups:
        primary_photo = next(p for p in photos if p["photo_id"] == g.primary_photo_id)
        caption = primary_photo["caption"]
        lot_id = f"BT-{primary_photo['sequence']:03d}"
        captions_map[lot_id] = caption

        if lot_id in REFERENCE_COMPS:
            comp_info = REFERENCE_COMPS[lot_id]
            app_pair = appraisal_by_lot.get(lot_id)
            if app_pair:
                _, raw_app = app_pair
            else:
                raw_app = {}
            fit, penalty = operator_lot_inputs(lot_id, raw_app)
            cat = comp_info["cat"]
            ident = raw_app.get("identification", comp_info["desc"])

            comp_est = CompEstimate(
                low=comp_info["low"],
                high=comp_info["high"],
                source_count=comp_info["sources"],
                confidence=comp_info["conf"],
            )

            lot_obj = Lot(
                lot_id=lot_id,
                caption=ident,
                category=cat,
                fit_score=fit,
                condition_penalty=penalty,
                comp=comp_est,
            )
            lots.append(lot_obj)
            decisions.append(apply_operator_cap(price_lot(lot_obj)))
        else:
            lot_obj = Lot(
                lot_id=lot_id,
                caption=caption or f"Uncaptioned lot (Photo #{primary_photo['sequence']})",
                category="general estate",
                fit_score=0.20,
                condition_penalty=0.10,
                comp=CompEstimate(low=None, high=None, source_count=0, confidence=BidConfidence.NONE),
            )
            lots.append(lot_obj)
            decisions.append(price_lot(lot_obj))

    allocated_decisions = allocate(decisions, budget_cap=budget_cap, auto_send_threshold=auto_send_threshold)
    sheet_summary = summarize(allocated_decisions)

    print("\n" + "=" * 80)
    print("ALLOCATION & SOURCING SUMMARY:")
    print(f"  Total Lots:             {sheet_summary.total_lots}")
    print(f"  Allocated Lots:         {sheet_summary.allocated}")
    print(f"  Auto-Send (<=${auto_send_threshold:.2f}):   {sheet_summary.auto_send}")
    print(f"  Needs Owner Approval:   {sheet_summary.needs_approval}")
    print(f"  Committed Max Bids:     ${sheet_summary.committed_max:,.2f}")
    print(f"  Committed All-In Cost:  ${sheet_summary.committed_all_in:,.2f} (w/ 15% absentee fee)")
    print("=" * 80)

    # 6. Generate Absentee Email Draft
    approved_bids = [d for d in allocated_decisions if d.allocated and d.max_bid]
    email_draft_path = Path(data_dir).parent / "aug22_absentee_bid_email.txt"
    email_lines = [
        "TO: info@bluetoadauctions.com",
        "SUBJECT: Absentee Bids - August 22 Antique & Estate Auction (Bidder: Richmond General)",
        "DATE: Friday, August 21, 2026 (Before 8:00 PM CDT Cutoff)",
        "",
        "Blue Toad Auctions,",
        "",
        "Please register the following absentee proxy bids for the Saturday, August 22, 2026 auction",
        "at 200 Elizabeth Lane, Genoa City, WI.",
        "",
        "Bidder Info:",
        "  Name: Richmond General (Scott)",
        "  Resale Certificate: On file (Wisconsin Tax-Exempt)",
        "  Terms: 15% Absentee Buyer Fee acknowledged (Credit Card on File)",
        "",
        "-" * 89,
    ]

    # One block per bid rather than a fixed-width table. A clerk has to match
    # each line to a physical lot on Saturday morning, and the table truncated
    # descriptions mid-word at 48 characters -- "storage box containing bulk"
    # is a bid on an unidentified object.
    for i, d in enumerate(approved_bids, 1):
        lot_obj = next(l for l in lots if l.lot_id == d.lot_id)
        start_bid = snap_to_increment(max(5.0, d.max_bid * 0.35))
        description = " ".join((lot_obj.caption or d.category).split())
        wrapped = textwrap.wrap(description, width=78) or [description]
        email_lines.append(f"{i:>2}) [{d.lot_id}]  {wrapped[0]}")
        email_lines.extend(f"      {line}" for line in wrapped[1:])
        email_lines.append(f"      START ${start_bid:,.2f}   MAX ${d.max_bid:,.2f}")
        email_lines.append("")

    email_lines.extend([
        "-" * 89,
        f"TOTAL COMMITTED PROXY BIDS: ${sheet_summary.committed_max:,.2f} (${sheet_summary.committed_all_in:,.2f} all-in w/ 15% fee)",
        "",
        "Special Instructions:",
        "  - For 'Buyer's Choice / Times the Money' shelf lots, max quantity is 1 unit only.",
        "  - Standard $5.00 bidding increments applied.",
        "  - Please confirm receipt of these absentee bids by reply email.",
        "",
        "Thank you,",
        "Richmond General",
    ])
    email_draft_path.write_text("\n".join(email_lines))
    print(f"\n[✓] Compiled Final Sealed Absentee Bid Email Draft: {email_draft_path}")

    # 7. Generate Excel Sourcing Sheet
    out_excel = Path(data_dir).parent / "BlueToad_2026-08-22_BidSheet.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Aug 22 Bid Sheet"

    hdr_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    hdr_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")

    headers = ["Lot ID", "Category", "Description", "Est Resale ($)", "Start Bid ($)", "Max Bid ($)", "All-In ($)", "Status"]
    ws.append(headers)
    for c in range(1, 9):
        ws.cell(1, c).fill = hdr_fill
        ws.cell(1, c).font = hdr_font

    for idx, d in enumerate(approved_bids, 2):
        lot_obj = next(l for l in lots if l.lot_id == d.lot_id)
        start_bid = snap_to_increment(max(5.0, d.max_bid * 0.35))
        est_str = f"${lot_obj.comp.low:.0f}-${lot_obj.comp.high:.0f}" if lot_obj.comp.low else "N/A"
        ws.append([
            d.lot_id,
            d.category,
            lot_obj.caption,
            est_str,
            start_bid,
            d.max_bid,
            d.all_in,
            "AUTO-SEND" if d.auto_send else "APPROVED",
        ])
        ws.cell(idx, 8).fill = green_fill

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    wb.save(out_excel)
    print(f"[✓] Saved updated Excel Bid Sheet: {out_excel}")

    # 8. Save Pipeline Snapshot JSON
    pipeline_state_file = Path(data_dir) / "pipeline_state.json"
    pipeline_state_file.write_text(json.dumps({
        "cycle_id": cycle_id,
        "listing_id": listing_id,
        "budget_cap": budget_cap,
        "auto_send_threshold": auto_send_threshold,
        "summary": sheet_summary.__dict__,
        "approved_lots_count": len(approved_bids),
        "total_lots_count": len(lot_groups),
        "photos_count": len(photos),
    }, indent=2))
    print(f"[✓] Saved pipeline state snapshot: {pipeline_state_file}")

    return photos, lot_groups, lots, allocated_decisions, sheet_summary, queue_result, captions_map


if __name__ == "__main__":
    force_live = "--live" in sys.argv
    run_pipeline(force_live_vertex=force_live)
