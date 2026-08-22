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

from dataclasses import replace
from src.intake.manifest import parse_drop, group_into_lots, TriagedPhoto
from src.assemble import AppraisedPhoto, assemble_lots, NO_COMP
from src.bidmath import (
    Lot, CompEstimate, Confidence as BidConfidence, Priority, Decision,
    price_lot, allocate, summarize, ABSENTEE_FEE, mechanic_from_ruling
)
from src.appraisal import (
    Question, QuestionKind, build_queue, learn, StandingRule,
    Appraisal, Confidence as AppConfidence
)
from src.appraiser import AppraisalEngine
from src.appraiser.containers import visible_contents
from src.gate import CycleView, render_console
from src.gate.pitch import build_pitch, curator_voice, _CURATOR_SYSTEM
from scripts.run_vertex_pipeline import (
    REFERENCE_COMPS, OPERATOR_APPROVED, operator_lot_inputs, apply_operator_cap,
    trusted_lot_flags,
)

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
    ],
    "user_constraints": {"payment_method": "credit_card", "budget_envelope": 600.00},
}

engine = AppraisalEngine()


def cached_photo_bytes(lot_id: str) -> bytes | None:
    """The lot's cached gallery photo, or None if the drop has no image for it."""
    manifest_path = Path("data/aug22_gallery_4160518/manifest.json")
    if not manifest_path.exists():
        manifest_path = Path("/app/data/aug22_gallery_4160518/manifest.json")
    if not manifest_path.exists():
        return None

    manifest = json.loads(manifest_path.read_text())
    for photo in manifest["photos"]:
        if f"BT-{photo['sequence']:03d}" != lot_id:
            continue
        path = Path(photo.get("local_path") or "")
        return path.read_bytes() if path.is_file() else None
    return None


def curator_pitch(decisions, captions) -> str:
    """
    The curator's read for the console banner.

    Served from disk where a previous run wrote one, so a page load does not
    call a model. With no cache it writes one live and keeps it. If Gemma is
    unreachable, curator_voice returns the deterministic line and the console
    renders normally — the banner is commentary, and commentary must never be
    the reason a bid sheet fails to load.
    """
    cache = Path("data/aug22_gallery_4160518/curator_voice.txt")
    if not cache.exists():
        alt = Path("/app/data/aug22_gallery_4160518/curator_voice.txt")
        cache = alt if alt.exists() else cache
    facts = build_pitch(decisions, captions, STATE["standing_rules"])

    # Key the cache to the sheet it describes. It was previously served whenever
    # the file was non-empty, with no invalidation at all, so the banner kept
    # quoting a committed total from a sheet that no longer existed — staler
    # than any bug it might have been hiding. A stamp mismatch re-writes it.
    stamp = f"# sheet {facts.committed_max:.2f}/{facts.committed_all_in:.2f}\n"
    if cache.exists():
        cached = cache.read_text()
        if cached.startswith(stamp) and cached[len(stamp):].strip():
            return cached[len(stamp):].strip()
    text = curator_voice(
        facts, writer=lambda pr: engine.write_curator_voice(pr, _CURATOR_SYSTEM))
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(stamp + text + "\n")
    except OSError:
        pass          # read-only filesystem is fine; the text is already in hand
    return text


def get_aug22_state():
    manifest_path = Path("data/aug22_gallery_4160518/manifest.json")
    if not manifest_path.exists():
        manifest_path = Path("/app/data/aug22_gallery_4160518/manifest.json")

    triage_cache_path = Path("data/aug22_gallery_4160518/triage_results.json")
    if not triage_cache_path.exists():
        triage_cache_path = Path("/app/data/aug22_gallery_4160518/triage_results.json")

    appraisal_cache_path = Path("data/aug22_gallery_4160518/appraisal_results.json")
    if not appraisal_cache_path.exists():
        appraisal_cache_path = Path("/app/data/aug22_gallery_4160518/appraisal_results.json")

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        photos = manifest["photos"]
    else:
        photos = []

    # 1. Load Vertex AI Appraisals (from cache or live engine)
    appraisals_by_lot = {}
    emitted_questions = []
    if appraisal_cache_path.exists():
        try:
            cached_data = json.loads(appraisal_cache_path.read_text())
            for raw in cached_data:
                lot_id = raw.get("lot_id")
                cat_hint = REFERENCE_COMPS.get(lot_id, {}).get("cat")
                app_obj, qs = engine.parse_appraisal_to_domain(raw, category_override=cat_hint)
                appraisals_by_lot[app_obj.lot_id] = (app_obj, raw)
                emitted_questions.extend(qs)
        except Exception as e:
            print(f"[!] Warning: Could not parse appraisal cache: {e}")

    # Optional Triage Cache
    triage_by_photo = {}
    if triage_cache_path.exists():
        try:
            cached_triage = json.loads(triage_cache_path.read_text())
            for item in cached_triage:
                triage_by_photo[item.get("photo_id")] = item
        except Exception as e:
            print(f"[!] Warning: Could not parse triage cache: {e}")

    # 2. Build AppraisedPhoto instances for each photo (Triage Fanout & Per-Photo Appraisals)
    appraised_photos = []
    for i, p in enumerate(photos):
        seq_num = p.get("sequence", i + 1)
        lot_tag = f"BT-{seq_num:03d}"
        pid = p.get("photo_id", f"fp_{seq_num:03d}")
        cap = p.get("caption", "")
        has_cap = bool(cap.strip())

        # How far Stage 1 is believed about lot boundaries — one implementation,
        # shared with the pipeline. The console had its own copy and merged a
        # captioned $25 lot away that the pipeline kept.
        is_lot, same_lot = trusted_lot_flags(
            triage_by_photo.get(pid),
            caption=cap,
            previous_captioned=bool(i > 0 and photos[i - 1]["has_caption"]),
            index=i,
        )

        # Determine appraisal attributes
        app_pair = appraisals_by_lot.get(lot_tag)
        raw_app = app_pair[1] if app_pair else {}
        if lot_tag in REFERENCE_COMPS:
            comp_info = REFERENCE_COMPS[lot_tag]
            ident = raw_app.get("identification", comp_info["desc"])
            cat = comp_info["cat"]
            # The owner's decision carries the fit; the appraiser's own condition
            # and confidence readings stand, so the console shows both.
            fit, penalty = operator_lot_inputs(lot_tag, raw_app)
            conf_str = str(raw_app.get("confidence", "low")).lower()
            conf = (AppConfidence(conf_str)
                    if conf_str in AppConfidence._value2member_map_ else AppConfidence.LOW)
        elif app_pair:
            app_obj, _ = app_pair
            ident = raw_app.get("identification", cap)
            cat = raw_app.get("category", "general estate")
            fit = float(raw_app.get("fit_score", 0.50))
            penalty = float(raw_app.get("condition_penalty", 0.0))
            conf_str = raw_app.get("confidence", "low").lower()
            conf = AppConfidence(conf_str) if conf_str in AppConfidence._value2member_map_ else AppConfidence.LOW
        else:
            ident = cap
            cat = "general estate"
            fit = 0.20
            penalty = 0.0
            conf = AppConfidence.NONE

        appraised_photos.append(AppraisedPhoto(
            photo_id=lot_tag,
            caption=cap,
            is_lot=is_lot,
            same_lot_as_previous=same_lot,
            identification=ident,
            category=cat,
            condition_penalty=penalty,
            fit_score=fit,
            confidence=conf,
            contents=visible_contents(raw_app.get("container_decomposition")),
        ))

    # 3. Comps Mapping & Seam Assembly (assemble_lots)
    comps = {}
    for k, v in REFERENCE_COMPS.items():
        comp_est = CompEstimate(
            low=v["low"],
            high=v["high"],
            source_count=v["sources"],
            confidence=v["conf"],
        )
        comps[k] = comp_est
        comps[f"seq:{k}"] = comp_est

    assembled_raw = assemble_lots(appraised_photos, comps=comps)
    lots = [
        replace(l, lot_id=l.lot_id.removeprefix("seq:")) if l.lot_id.startswith("seq:") else l
        for l in assembled_raw
    ]

    captions_map = {l.lot_id: l.caption for l in lots}

    # 3b. The auctioneer's ruling on how a lot is SOLD, applied before pricing.
    # The appraiser asks "one lot or all of them?"; a human or the house answers
    # in words; this is where the answer becomes money. Without it the console
    # renders BT-002 at one tray while the absentee email that went out commits
    # three. A lot with no ruling on file was never asked about and is a plain
    # single lot — only a ruling that exists and cannot be read is UNKNOWN.
    ruled = []
    for l in lots:
        ruling = OPERATOR_APPROVED.get(l.lot_id, {}).get("ruling")
        if ruling:
            mech, units, wanted = mechanic_from_ruling(ruling)
            l = replace(l, mechanic=mech, unit_count=units, units_wanted=wanted)
        ruled.append(l)
    lots = ruled

    # 4. BidMath Pricing & Allocation
    decisions = [apply_operator_cap(price_lot(l)) for l in lots]
    allocated_decisions = allocate(
        decisions,
        budget_cap=STATE["budget_cap"],
        auto_send_threshold=STATE["auto_send_threshold"],
    )
    summary = summarize(allocated_decisions)

    # 5. Questions Queue (Domain Policies + Model-Emitted)
    domain_questions = [
        Question(
            kind=QuestionKind.POLICY,
            category="sports memorabilia",
            prompt="Uncertified Autographs (Jordan Hat BT-006, DiMaggio Hat BT-010): No visible PSA/JSA certificate in photos. Bid speculative raw floor or skip?",
            lot_ids=("BT-006", "BT-010"),
            value_at_stake=800.0,
            confidence_gap=0.5,
            wants_photo=False,
        ),
        Question(
            kind=QuestionKind.APPETITE,
            category="dinnerware / pottery",
            prompt="Under-Table Box Runs (Poppy Trail BT-073): Blue Toad convention check — assume all 10 under-table boxes sell together as ONE bulk estate lot, or skip?",
            lot_ids=("BT-073", "BT-075", "BT-078", "BT-080"),
            value_at_stake=200.0,
            confidence_gap=0.3,
            wants_photo=False,
        ),
        Question(
            kind=QuestionKind.APPETITE,
            category="vintage tools",
            prompt="Vintage Tool Sourcing (Toolbox BT-083, Wrenches BT-086): Store inventory status?",
            lot_ids=("BT-083", "BT-086"),
            value_at_stake=150.0,
            confidence_gap=0.3,
            wants_photo=False,
        ),
    ]
    all_questions = domain_questions + emitted_questions
    queue_res = build_queue(all_questions, STATE["standing_rules"], cap=12)

    return photos, lots, lots, allocated_decisions, summary, queue_res, captions_map


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
    photos, _, lots, decisions, summary, queue_res, captions_map = get_aug22_state()
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
        lots_total=len(lots),
    )
    return render_console(view, pitch_text=curator_pitch(decisions, captions_map))


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

    # Promote through domain learn() mechanism
    temp_question = Question(
        kind=kind,
        category=cat,
        prompt=f"Clarification for {cat}",
        lot_ids=(),
    )
    promoted = learn([(temp_question, ans)], cycle=STATE["cycle_id"])
    if promoted:
        new_rule = promoted[0]
    else:
        new_rule = StandingRule(
            kind=kind,
            category=cat,
            answer=ans,
            learned_cycle=STATE["cycle_id"],
        )

    STATE["standing_rules"] = [
        r for r in STATE["standing_rules"] if (r.kind, r.category) != (new_rule.kind, new_rule.category)
    ] + [new_rule]

    return {
        "status": "learned",
        "standing_rules_count": len(STATE["standing_rules"]),
        "rule": {"kind": kind.value, "category": cat, "answer": ans, "cycle": STATE["cycle_id"]},
    }


@app.post("/api/appraise")
def appraise_live(payload: dict = Body(...)):
    """Run an on-demand live Vertex AI appraisal on a lot."""
    lot_id = payload.get("lot_id")
    caption = payload.get("caption", "")
    category_hint = payload.get("category_hint")

    if not lot_id:
        raise HTTPException(status_code=400, detail="Missing lot_id")

    photo_bytes = cached_photo_bytes(lot_id)
    if photo_bytes is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cached photo for {lot_id}; cannot appraise from a caption alone.",
        )

    try:
        raw_result = engine.appraise_lot(
            lot_id=lot_id,
            caption=caption,
            image_bytes=photo_bytes,
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


@app.post("/api/decompose")
def decompose_live(payload: dict = Body(...)):
    """Spatially isolate and itemize one cached gallery photo."""
    lot_id = payload.get("lot_id")
    if not lot_id:
        raise HTTPException(status_code=400, detail="Missing lot_id")
    photo_bytes = cached_photo_bytes(lot_id)
    if photo_bytes is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cached photo for {lot_id}; cannot decompose from a caption alone.",
        )
    try:
        result = engine.decompose_container(
            lot_id=lot_id,
            caption=payload.get("caption", ""),
            image_bytes=photo_bytes,
            spatial_boundary=payload.get("spatial_boundary"),
            spatial_context=payload.get("spatial_context"),
            container_type=payload.get("container_type"),
        )
        return {"status": "success", "decomposition": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vertex AI decomposition failed: {e}")


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
