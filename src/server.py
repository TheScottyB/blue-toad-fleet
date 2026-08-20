#!/usr/bin/env python3
"""
src/server.py — Cloud Run Web Server & API for Blue Toad Fleet.

Serves the interactive Gate Console UI, real-time collaboration endpoints,
automated absentee email generator, and live Vertex AI appraisal execution on Google Cloud.
"""

import json
import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse

from src.intake.manifest import parse_drop, group_into_lots, TriagedPhoto
from src.bidmath import (
    Lot, CompEstimate, Confidence as BidConfidence, Priority, Decision,
    price_lot, allocate, summarize, ABSENTEE_FEE
)
from src.appraisal import (
    Question, QuestionKind, build_queue, learn, StandingRule,
    Appraisal, Confidence as AppConfidence
)
from src.appraiser import AppraisalEngine
from src.gate import CycleView, render_console
from scripts.run_vertex_pipeline import REFERENCE_COMPS

app = FastAPI(title="Blue Toad Fleet", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

engine = AppraisalEngine()


def get_aug22_state():
    manifest_path = Path("data/aug22_gallery_4160518/manifest.json")
    if not manifest_path.exists():
        manifest_path = Path("/app/data/aug22_gallery_4160518/manifest.json")

    appraisal_cache_path = Path("data/aug22_gallery_4160518/appraisal_results.json")
    if not appraisal_cache_path.exists():
        appraisal_cache_path = Path("/app/data/aug22_gallery_4160518/appraisal_results.json")

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        photos = manifest["photos"]
    else:
        photos = []

    # 1. Spatial Intake & Grouping
    entries = [{"name": p["filename"], "uri": p["thumb_url"], "caption": p["caption"]} for p in photos]
    drop = parse_drop(cycle_id=STATE["cycle_id"], listing_id=STATE["listing_id"], entries=entries)

    triaged = []
    for i, p in enumerate(photos):
        cap = p["caption"].lower()
        has_cap = bool(cap.strip())
        is_extra_angle = (not has_cap and i > 0 and photos[i-1]["has_caption"])
        triaged.append(TriagedPhoto(
            photo_id=p["photo_id"],
            caption=p["caption"],
            is_lot=not is_extra_angle,
            same_lot_as_previous=is_extra_angle,
        ))

    lot_groups = group_into_lots(triaged)

    # 2. Load Vertex AI Appraisals (from cache or live engine)
    appraisals_by_lot = {}
    emitted_questions = []
    if appraisal_cache_path.exists():
        try:
            cached_data = json.loads(appraisal_cache_path.read_text())
            for raw in cached_data:
                app_obj, qs = engine.parse_appraisal_to_domain(raw)
                appraisals_by_lot[app_obj.lot_id] = (app_obj, raw)
                emitted_questions.extend(qs)
        except Exception as e:
            print(f"[!] Warning: Could not parse appraisal cache: {e}")

    # 3. Candidate Lot Evaluation & Bid Decisions
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
            app_pair = appraisals_by_lot.get(lot_id)
            if app_pair:
                app_obj, raw_app = app_pair
                fit = 0.85
                penalty = 0.0
                cat = comp_info["cat"]
                ident = raw_app.get("identification", comp_info["desc"])
            else:
                fit = 0.85
                penalty = 0.0
                cat = comp_info["cat"]
                ident = comp_info["desc"]

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
            decisions.append(price_lot(lot_obj))
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

    allocated_decisions = allocate(
        decisions,
        budget_cap=STATE["budget_cap"],
        auto_send_threshold=STATE["auto_send_threshold"],
    )
    summary = summarize(allocated_decisions)

    # 4. Questions Queue (Domain policies + Model Emitted)
    domain_questions = [
        Question(
            kind=QuestionKind.POLICY,
            category="sports memorabilia",
            prompt="Uncertified Autographs (Jordan Hat BT-006, DiMaggio Hat BT-010): No visible PSA/JSA certificate in photos. Bid speculative raw floor or skip?",
            lot_ids=("BT-006", "BT-010"),
            value_at_stake=800.0,
            confidence_gap=0.5,
            wants_photo=False
        ),
        Question(
            kind=QuestionKind.APPETITE,
            category="dinnerware / pottery",
            prompt="Under-Table Box Runs (Poppy Trail BT-073): Blue Toad convention check — assume all 10 under-table boxes sell together as ONE bulk estate lot, or skip?",
            lot_ids=("BT-073", "BT-075", "BT-078", "BT-080"),
            value_at_stake=200.0,
            confidence_gap=0.3,
            wants_photo=False
        ),
        Question(
            kind=QuestionKind.APPETITE,
            category="vintage tools",
            prompt="Vintage Tool Sourcing (Toolbox BT-083, Wrenches BT-086): Store inventory status?",
            lot_ids=("BT-083", "BT-086"),
            value_at_stake=150.0,
            confidence_gap=0.3,
            wants_photo=False
        ),
    ]
    all_questions = domain_questions + emitted_questions
    queue_res = build_queue(all_questions, STATE["standing_rules"], cap=12)

    return photos, lot_groups, lots, allocated_decisions, summary, queue_res, captions_map


@app.get("/health")
@app.get("/healthz")
@app.get("/healthz/")
def healthz():
    return {
        "status": "healthy",
        "service": "blue-toad-fleet",
        "project": os.environ.get("GOOGLE_CLOUD_PROJECT", "threebatdrone-prod-420"),
        "version": "2.0.0",
        "vertex_client": bool(engine.client),
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
    kind_str = payload.get("kind")
    cat = payload.get("category")
    ans = payload.get("answer")

    if not kind_str or not cat or not ans:
        raise HTTPException(status_code=400, detail="Missing kind, category, or answer")

    try:
        kind = QuestionKind(kind_str.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid question kind: {kind_str}")

    new_rule = StandingRule(
        kind=kind,
        category=cat,
        answer=ans,
        learned_cycle=STATE["cycle_id"],
    )
    STATE["standing_rules"] = [r for r in STATE["standing_rules"] if (r.kind, r.category) != (new_rule.kind, new_rule.category)] + [new_rule]
    return {
        "status": "learned",
        "standing_rules_count": len(STATE["standing_rules"]),
        "rule": {"kind": kind_str, "category": cat, "answer": ans, "cycle": STATE["cycle_id"]},
    }


@app.post("/api/appraise")
def appraise_live(payload: dict = Body(...)):
    """Run an on-demand live Vertex AI appraisal on a lot."""
    lot_id = payload.get("lot_id")
    caption = payload.get("caption", "")
    category_hint = payload.get("category_hint")

    if not lot_id:
        raise HTTPException(status_code=400, detail="Missing lot_id")

    try:
        raw_result = engine.appraise_lot(
            lot_id=lot_id,
            caption=caption,
            category_hint=category_hint,
            standing_rules=STATE["standing_rules"],
        )
        appraisal, questions = engine.parse_appraisal_to_domain(raw_result)
        return {
            "status": "success",
            "model_used": raw_result.get("model_used"),
            "appraisal": {
                "lot_id": appraisal.lot_id,
                "category": appraisal.category,
                "identification": appraisal.identification,
                "confidence": appraisal.confidence.value,
                "est_value_hint": appraisal.est_value_hint,
            },
            "questions": [
                {
                    "kind": q.kind.value,
                    "prompt": q.prompt,
                    "wants_photo": q.wants_photo,
                    "confidence_gap": q.confidence_gap,
                }
                for q in questions
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vertex AI appraisal failed: {e}")


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
