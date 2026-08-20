#!/usr/bin/env python3
"""
src/server.py — Cloud Run Web Server & API for Blue Toad Fleet.

Serves the interactive Gate Console UI, real-time collaboration endpoints,
and the automated absentee email generator on Google Cloud.
"""

import json
import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse

from src.intake.manifest import parse_drop, group_into_lots, TriagedPhoto
from src.bidmath import (
    Lot, CompEstimate, Confidence, Priority,
    price_lot, allocate, summarize, ABSENTEE_FEE
)
from src.appraisal import Question, QuestionKind, build_queue, learn, StandingRule
from src.gate import CycleView, render_console
from scripts.run_aug22_cycle import AUG22_CATALOG_TAXONOMY, evaluate_catalog_comp

app = FastAPI(title="Blue Toad Fleet", version="2.0.0")

# In-memory runtime state for the active cycle
STATE = {
    "cycle_id": "2026-08-22",
    "listing_id": "4160518",
    "budget_cap": 600.00,
    "auto_send_threshold": 35.00,
    "standing_rules": [
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
    ],
    "user_constraints": {"payment_method": "credit_card", "budget_envelope": 600.00},
}

def get_aug22_state():
    manifest_path = Path("data/aug22_gallery_4160518/manifest.json")
    if not manifest_path.exists():
        manifest_path = Path("/app/data/aug22_gallery_4160518/manifest.json")
    
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        photos = manifest["photos"]
    else:
        photos = []

    # 1. Spatial Intake & Grouping
    entries = [{"name": p["filename"], "uri": p["thumb_url"], "caption": p["caption"]} for p in photos]
    drop = parse_drop(cycle_id="2026-08-22", listing_id="4160518", entries=entries)

    triaged = []
    for i, p in enumerate(photos):
        cap = p["caption"].lower()
        has_cap = bool(cap.strip())

        if "poppy trail" in cap or (i > 0 and "poppy trail" in photos[i-1]["caption"].lower() and not has_cap):
            is_first_poppy = ("poppy trail" in cap and (i == 0 or "poppy trail" not in photos[i-1]["caption"].lower()))
            triaged.append(TriagedPhoto(
                photo_id=p["photo_id"],
                caption=p["caption"] or "Poppy Trail dishes (Under-table multi-box set)",
                is_lot=is_first_poppy,
                same_lot_as_previous=not is_first_poppy,
            ))
            continue

        is_extra_angle = (not has_cap and i > 0 and photos[i-1]["has_caption"])
        triaged.append(TriagedPhoto(
            photo_id=p["photo_id"],
            caption=p["caption"],
            is_lot=not is_extra_angle,
            same_lot_as_previous=is_extra_angle,
        ))

    lot_groups = group_into_lots(triaged)

    # 2. Valuation & BidMath
    lots = []
    captions_map = {}
    for g in lot_groups:
        primary_photo = next(p for p in photos if p["photo_id"] == g.primary_photo_id)
        caption = primary_photo["caption"]
        lot_id = f"BT-{primary_photo['sequence']:03d}"
        captions_map[lot_id] = caption

        comp, cat, fit = evaluate_catalog_comp(caption)
        lots.append(Lot(
            lot_id=lot_id,
            caption=caption or f"Uncaptioned lot (Photo #{primary_photo['sequence']})",
            category=cat,
            fit_score=fit,
            condition_penalty=0.10,
            comp=comp or CompEstimate(low=0.0, high=0.0, source_count=0, confidence=Confidence.NONE),
        ))

    decisions = [price_lot(l) for l in lots]
    decisions = allocate(decisions, budget_cap=STATE["budget_cap"], auto_send_threshold=STATE["auto_send_threshold"])
    summary = summarize(decisions)

    # 3. Questions Queue (Policy, House Conventions, and Appetite)
    questions = [
        Question(
            kind=QuestionKind.POLICY,
            category="sports memorabilia",
            prompt="Uncertified Autographs (Jordan Hat BT-006, DiMaggio Hat BT-010): No visible PSA/JSA certificate in photos. Bid speculative raw floor ($35 max bid) or skip uncertified sports ink entirely?",
            lot_ids=("BT-006", "BT-010"),
            value_at_stake=800.0,
            confidence_gap=0.5,
            wants_photo=False
        ),
        Question(
            kind=QuestionKind.LOT_GROUPING,
            category="dinnerware / pottery",
            prompt="Under-Table Box Runs (Poppy Trail BT-073): Blue Toad convention check — assume all 10 under-table boxes sell together as ONE bulk estate lot ($45 max for all), or bid as choice per box?",
            lot_ids=("BT-073", "BT-075", "BT-078", "BT-080"),
            value_at_stake=200.0,
            confidence_gap=0.3,
            wants_photo=False
        ),
        Question(
            kind=QuestionKind.APPETITE,
            category="sports memorabilia",
            prompt="Store Inventory Balance: Sourcing engine selected $650 across sports memorabilia. Is the sports showcase low, or should we cap sports at $300 and bias budget toward tools and breweriana?",
            lot_ids=("BT-004", "BT-006", "BT-007", "BT-008", "BT-010", "BT-012", "BT-023"),
            value_at_stake=650.0,
            confidence_gap=0.4,
            wants_photo=False
        ),
    ]
    queue_res = build_queue(questions, STATE["standing_rules"], cap=12)

    return photos, lot_groups, lots, decisions, summary, queue_res, captions_map

@app.get("/healthz")
def healthz():
    return {
        "status": "healthy",
        "service": "blue-toad-fleet",
        "project": os.environ.get("GOOGLE_CLOUD_PROJECT", "threebatdrone-prod-420"),
        "version": "2.0.0",
    }

@app.get("/", response_class=HTMLResponse)
def get_console():
    photos, lot_groups, lots, decisions, summary, queue_res, captions_map = get_aug22_state()
    view = CycleView(
        cycle_id=STATE["cycle_id"],
        auction_date="Saturday, August 22, 2026",
        photos_ingested=len(photos),
        queue=queue_res,
        decisions=decisions,
        summary=summary,
        budget_cap=STATE["budget_cap"],
        auto_send_threshold=STATE["auto_send_threshold"],
        captions=captions_map,
        deadline="Friday August 21, 8:00 PM CDT",
        illustrative=False,
        lots_total=len(lot_groups),
    )
    return render_console(view)

@app.get("/api/lots")
def list_lots():
    _, _, lots, decisions, summary, _, _ = get_aug22_state()
    by_id = {d.lot_id: d for d in decisions}
    out = []
    for l in lots:
        d = by_id.get(l.lot_id)
        out.append({
            "lot_id": l.lot_id,
            "caption": l.caption,
            "category": l.category,
            "fit_score": l.fit_score,
            "comp_low": l.comp.low if l.comp.source_count > 0 else None,
            "comp_high": l.comp.high if l.comp.source_count > 0 else None,
            "priority": d.priority.value if d else None,
            "max_bid": d.max_bid if d else None,
            "all_in": d.all_in if d else None,
            "auto_send": d.auto_send if d else False,
            "allocated": d.allocated if d else False,
            "decision": "AUTO-SEND" if d and d.auto_send and d.allocated else ("NEEDS APPROVAL" if d and d.allocated else "SKIPPED"),
        })
    return {"total": len(out), "summary": summary.__dict__, "lots": out}

@app.get("/api/questions")
def list_questions():
    _, _, _, _, _, queue_res, _ = get_aug22_state()
    return {
        "asked": [
            {
                "kind": q.kind.value,
                "category": q.category,
                "prompt": q.prompt,
                "lot_ids": list(q.lot_ids),
                "value_at_stake": q.value_at_stake,
                "confidence_gap": q.confidence_gap,
                "impact": q.impact,
            }
            for q in queue_res.asked
        ],
        "auto_answered_from_memory": [
            {"question": q.prompt, "rule": r.answer, "learned_cycle": r.learned_cycle}
            for q, r in queue_res.auto_answered
        ],
    }

@app.post("/api/answer")
def answer_question(payload: dict = Body(...)):
    """
    Accepts an answer to a clarification question, promoting it to a persistent StandingRule.
    Payload: {"kind": "lot_grouping", "category": "dinnerware / pottery", "answer": "all under-table boxes sell as one"}
    """
    kind_str = payload.get("kind")
    cat = payload.get("category")
    ans = payload.get("answer")

    if not kind_str or not cat or not ans:
        raise HTTPException(status_code=400, detail="Missing kind, category, or answer")

    new_rule = StandingRule(
        rule_key=(QuestionKind(kind_str), cat),
        answer=ans,
        learned_cycle=STATE["cycle_id"],
    )
    # Deduplicate and append
    STATE["standing_rules"] = [r for r in STATE["standing_rules"] if r.rule_key != new_rule.rule_key] + [new_rule]
    return {
        "status": "learned",
        "standing_rules_count": len(STATE["standing_rules"]),
        "rule": {"rule_key": f"{kind_str}:{cat}", "answer": ans, "cycle": STATE["cycle_id"]},
    }

@app.get("/api/email", response_class=PlainTextResponse)
def get_absentee_email():
    email_path = Path("data/aug22_absentee_bid_email.txt")
    if not email_path.exists():
        email_path = Path("/app/data/aug22_absentee_bid_email.txt")
    if email_path.exists():
        return email_path.read_text()
    return "Absentee email draft not generated yet."

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
