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
from fastapi import FastAPI, HTTPException, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse

from dataclasses import replace
from src.intake.embed import load_reshoot_edges
from src.intake.manifest import parse_drop, group_into_lots, LotGroup, TriagedPhoto
from src.intake.spatial import merge_reshoots, seats_from_groups
from src.assemble import AppraisedPhoto, assemble_lots, NO_COMP, compile_absentee_email
from src.bidmath import (
    Lot, CompEstimate, Confidence as BidConfidence, Priority, Decision,
    price_lot, allocate, summarize, ABSENTEE_FEE, mechanic_from_ruling
)
from src.appraisal import (
    Question, QuestionKind, build_queue, learn, StandingRule,
    Appraisal, Confidence as AppConfidence
)
from src.memory import (
    MemoryConflict, StandingRuleRecord, make_question_id, open_rule_store,
    seed_rules,
)
from src.memory.store import InMemoryRuleStore
from src.appraiser import AppraisalEngine
from src.appraiser.containers import visible_contents
from src.appraiser.routing import GEMMA_MODEL
from src.gate import CycleView, render_console
from src.gate.pitch import build_pitch, curator_voice, _CURATOR_SYSTEM
from src.gate.voice import write_pitch_voice
from scripts.run_vertex_pipeline import (
    REFERENCE_COMPS, OPERATOR_APPROVED, apply_operator_cap, apply_operator_fit,
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

SHOP_ID = os.environ.get("BTF_SHOP_ID", "richmond-general")
RULES = open_rule_store()

# Cycle-scoped runtime. Standing rules live in RULES, not here.
STATE = {
    "cycle_id": "2026-08-22",
    "listing_id": "4160518",
    "budget_cap": 600.00,
    "auto_send_threshold": 35.00,
    "user_constraints": {"payment_method": "credit_card", "budget_envelope": 600.00},
}


def current_rules() -> list[StandingRule]:
    return RULES.active_rules(SHOP_ID)


def reset_rule_store(seed=None):
    """Tests only. Replaces the process store with a fresh in-memory seed."""
    global RULES
    RULES = InMemoryRuleStore(
        seed=seed_rules() if seed is None else seed, shop_id=SHOP_ID,
    )

engine = AppraisalEngine()


def photo_from_raw(raw_app: dict | None = None, **base) -> AppraisedPhoto:
    """Map a cached appraisal dict onto AppraisedPhoto, including container fields."""
    raw = raw_app or {}
    if "is_container" not in base:
        base["is_container"] = bool(raw.get("is_container", False))
    if "contents" not in base:
        base["contents"] = tuple(raw.get("contents") or ())
    elif not isinstance(base["contents"], tuple):
        base["contents"] = tuple(base["contents"] or ())
    return AppraisedPhoto(**base)


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
    facts = build_pitch(decisions, captions, current_rules())

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
            # Appraiser readings only here. Owner fit is applied after merge
            # on the surviving lot_id — stamping BT-181's decline onto the
            # close-up would let a high-confidence 181 SKIP BT-002.
            fit = float(raw_app.get("fit_score", 0.50))
            penalty = float(raw_app.get("condition_penalty", 0.0))
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

        appraised_photos.append(photo_from_raw(
            app_pair[1] if app_pair else None,
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

    embed_cache_path = Path("data/aug22_gallery_4160518/embeddings.json")
    if not embed_cache_path.exists():
        embed_cache_path = Path("/app/data/aug22_gallery_4160518/embeddings.json")

    # One grouping space: AppraisedPhoto.photo_id, sequences, and edges are BT-00N.
    # load_vectors accepts seq keys and gallery photo_ids into that space.
    photo_by_seq = {p["sequence"]: f"BT-{p['sequence']:03d}" for p in photos}
    gallery_ids = {str(p["photo_id"]): f"BT-{p['sequence']:03d}" for p in photos}
    sequences = {f"BT-{p['sequence']:03d}": p["sequence"] for p in photos}
    try:
        edges = load_reshoot_edges(
            embed_cache_path, photo_by_seq, sequences, gallery_ids=gallery_ids,
        )
    except Exception as e:
        print(f"[!] Warning: Could not parse embedding cache: {e}")
        edges = set()

    assembled_raw = assemble_lots(appraised_photos, comps=comps, reshoot_edges=edges)
    lots = [apply_operator_fit(l) for l in assembled_raw]

    groups = group_into_lots([
        TriagedPhoto(
            photo_id=p.photo_id,
            caption=p.caption,
            is_lot=p.is_lot,
            same_lot_as_previous=p.same_lot_as_previous,
        )
        for p in appraised_photos
    ])
    if edges:
        groups = merge_reshoots(groups, edges)
    seats = seats_from_groups(
        [LotGroup(lot_key=g.lot_key.removeprefix("seq:"), photo_ids=g.photo_ids)
         for g in groups],
        sequences,
    )

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
        Question(
            kind=QuestionKind.APPETITE,
            category="advertising / bottles",
            prompt="Century Progress bottle (BT-235) and similar advertising glass: keep buying for the storefront?",
            lot_ids=("BT-235",),
            value_at_stake=48.0,
            confidence_gap=0.3,
            wants_photo=False,
        ),
    ]
    all_questions = domain_questions + emitted_questions
    queue_res = build_queue(all_questions, current_rules(), cap=12)

    return photos, seats, lots, allocated_decisions, summary, queue_res, captions_map


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
        "gemma_model": GEMMA_MODEL,
        "gemma_ok": bool(engine.client) and "gemma" in GEMMA_MODEL.lower(),
        "memory_backend": getattr(RULES, "backend_name", "unknown"),
        "memory_durable": bool(getattr(RULES, "durable", False)),
    }


@app.get("/", response_class=HTMLResponse)
def get_console():
    photos, seats, lots, decisions, summary, queue_res, captions_map = get_aug22_state()
    pitch = build_pitch(decisions, captions_map, current_rules())
    # Unit tests must stay credential-free and fast. Cloud Run has no
    # PYTEST_CURRENT_TEST, so Gemma runs there (then caches).
    live_client = None if os.environ.get("PYTEST_CURRENT_TEST") else engine.client
    cache = Path("/tmp/btf_gemma_voice.json")
    voice = write_pitch_voice(
        pitch, client=live_client, cache_path=cache,
    )
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
        voice=voice,
        seats=seats,
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
                "question_id": make_question_id(STATE["cycle_id"], q),
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
            {
                "question_id": make_question_id(STATE["cycle_id"], q),
                "question": q.prompt,
                "rule": r.answer,
                "learned_cycle": r.learned_cycle,
            }
            for q, r in queue_res.auto_answered
        ],
    }


def _require_operator(x_operator_token: str | None) -> None:
    expected = os.environ.get("OPERATOR_TOKEN")
    if not expected:
        return
    if (x_operator_token or "") != expected:
        raise HTTPException(status_code=401, detail="operator token required")


@app.post("/api/answer")
def answer_question(
    payload: dict = Body(...),
    x_operator_token: str | None = Header(default=None),
):
    _require_operator(x_operator_token)
    qid = payload.get("question_id")
    ans = (payload.get("answer") or "").strip()
    if not qid or not ans:
        raise HTTPException(
            status_code=400, detail="Missing question_id or answer",
        )

    photos, seats, lots, decisions, summary, queue_res, captions = get_aug22_state()
    by_id = {make_question_id(STATE["cycle_id"], q): q for q in queue_res.asked}
    question = by_id.get(qid)
    if question is None:
        raise HTTPException(
            status_code=404, detail="question is not on the current desk queue",
        )

    before = {
        "asked": len(queue_res.asked),
        "auto_answered": len(queue_res.auto_answered),
        "allocated": [d.lot_id for d in decisions if d.allocated],
    }

    promoted = learn([(question, ans)], cycle=STATE["cycle_id"])
    stored = None
    if not promoted:
        return {
            "status": "recorded",
            "promoted": False,
            "reason": "object-specific answers do not become standing memory",
            "question_id": qid,
            "affected_lots": list(question.lot_ids),
            "before": before,
            "after": before,
            "appraisal_source": "cached_sheet",
            "pending_reappraisal": False,
        }

    new_rule = promoted[0]
    try:
        stored = RULES.put(StandingRuleRecord(
            shop_id=SHOP_ID,
            kind=new_rule.kind,
            category=new_rule.category,
            answer=new_rule.answer,
            learned_cycle=new_rule.learned_cycle,
            source_question_id=qid,
        ), expected_revision=payload.get("expected_revision"))
    except MemoryConflict as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    _, _, _, after_decisions, _, after_queue, _ = get_aug22_state()
    after = {
        "asked": len(after_queue.asked),
        "auto_answered": len(after_queue.auto_answered),
        "allocated": [d.lot_id for d in after_decisions if d.allocated],
    }
    return {
        "status": "applied",
        "promoted": True,
        "question_id": qid,
        "rule": {
            "rule_id": stored.rule_id,
            "revision": stored.revision,
            "kind": stored.kind.value,
            "category": stored.category,
            "answer": stored.answer,
            "learned_cycle": stored.learned_cycle,
            "source_question_id": stored.source_question_id,
        },
        "affected_lots": list(question.lot_ids),
        "before": before,
        "after": after,
        "appraisal_source": "cached_sheet",
        "pending_reappraisal": True,
        "standing_rules_count": len(current_rules()),
    }


@app.get("/api/memory")
def list_memory():
    rules = current_rules()
    return {
        "backend": getattr(RULES, "backend_name", "unknown"),
        "durable": bool(getattr(RULES, "durable", False)),
        "shop_id": SHOP_ID,
        "rules": [
            {
                "kind": r.kind.value,
                "category": r.category,
                "answer": r.answer,
                "learned_cycle": r.learned_cycle,
            }
            for r in rules
        ],
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
            standing_rules=current_rules(),
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
    _, _, lots, decisions, _, _, _ = get_aug22_state()
    return compile_absentee_email(
        to="info@bluetoadauctions.com",
        subject="Absentee Bids - August 22 Antique & Estate Auction (Bidder: Richmond General)",
        auction_date="Saturday, August 22, 2026",
        venue="200 Elizabeth Lane, Genoa City, WI",
        lots=lots,
        decisions=decisions,
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
