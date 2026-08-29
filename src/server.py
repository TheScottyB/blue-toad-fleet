#!/usr/bin/env python3
"""
src/server.py — Cloud Run Web Server & API for Blue Toad Fleet.

Serves the interactive Gate Console UI, real-time collaboration endpoints,
automated absentee email generator, and live Vertex AI appraisal execution on Google Cloud.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (HTMLResponse, PlainTextResponse, JSONResponse,
                               RedirectResponse, Response)

from dataclasses import replace
from src.intake.embed import load_reshoot_edges, sha256_file
from src.intake.manifest import parse_drop, group_into_lots, LotGroup, TriagedPhoto
from src.intake.spatial import merge_reshoots, seats_from_groups
from src.assemble import AppraisedPhoto, assemble_lots, NO_COMP, compile_absentee_email
from src.bidmath import (
    ABSENTEE_FEE, BidMechanic, CompEstimate, Confidence as BidConfidence,
    Decision, Lot, Priority, allocate, clerk_directive, elect,
    mechanic_from_ruling, price_lot, remainder_opportunity, summarize,
)
from src.appraisal import (
    Question, QuestionKind, build_queue, learn, learn_rulings, StandingRule,
    Appraisal, Confidence as AppConfidence
)
from src.memory import (
    LotRulingRecord, MemoryConflict, StandingRuleRecord, make_question_id, open_rule_store,
    seed_rules,
)
from src.memory.store import InMemoryRuleStore
from src.cycles import (
    CycleConflict, CycleNotFound, CycleStatus,
    open_cycle_repository, open_job_launcher,
)
from src.appraiser import AppraisalEngine
from src.appraiser.containers import visible_contents
from src.appraiser.grounded_batch import (
    grounded_reference_comps, grounded_status_reason,
)
from src.appraiser.routing import GEMMA_MODEL
from src.gate import CycleView, render_console
from src.gate.walkstrip import render_walk_strip
from src.gate.pitch import build_pitch
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
CYCLES = open_cycle_repository()
CYCLE_JOBS = open_job_launcher()

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


def current_rulings():
    return RULES.active_rulings(SHOP_ID, STATE["cycle_id"])


def apply_lot_rulings(lots, rulings=None, operator_approved=None):
    """Apply exact-object grouping rulings before any money is priced.

    A durable answer wins over the historic Aug-22 fixture. Scope answers are
    retained by memory but do not pretend to be mechanic instructions; only a
    LOT_GROUPING ruling is parsed into unit exposure here.
    """
    approvals = OPERATOR_APPROVED if operator_approved is None else operator_approved
    grouping_answers: dict[str, set[str]] = {}
    for ruling in current_rulings() if rulings is None else rulings:
        if ruling.kind is not QuestionKind.LOT_GROUPING:
            continue
        for lot_id in ruling.lot_ids:
            grouping_answers.setdefault(lot_id, set()).add(ruling.answer)

    ruled = []
    for lot in lots:
        answers = grouping_answers.get(lot.lot_id, set())
        if len(answers) > 1:
            # Conflicting authorities must refuse rather than win by iteration
            # order. mechanic_from_ruling intentionally returns UNKNOWN here.
            answer = "conflicting grouping rulings"
        elif answers:
            answer = next(iter(answers))
        else:
            answer = approvals.get(lot.lot_id, {}).get("ruling")
        if answer:
            mechanic, units, wanted = mechanic_from_ruling(answer)
            lot = replace(
                lot,
                mechanic=mechanic,
                unit_count=units,
                units_wanted=None,
            )
            if wanted is not None and mechanic is not BidMechanic.UNKNOWN:
                lot = elect(lot, wanted)
        ruled.append(lot)
    return ruled


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


def get_aug22_state(*, sheet: str = "full"):
    """Build the historical August fixture view.

    ``sheet="sent"`` is an archival compatibility mode used only to reconcile
    the closed absentee email against the exact hand-comp inputs it received.
    Application endpoints use the full local fixture; fresh cloud cycles are
    built independently by ``src.cycles.worker``.
    """
    if sheet not in {"full", "sent"}:
        raise ValueError(f"unknown August fixture sheet: {sheet}")
    manifest_path = Path("data/aug22_gallery_4160518/manifest.json")
    if not manifest_path.exists():
        manifest_path = Path("/app/data/aug22_gallery_4160518/manifest.json")

    triage_cache_path = Path("data/aug22_gallery_4160518/triage_results.json")
    if not triage_cache_path.exists():
        triage_cache_path = Path("/app/data/aug22_gallery_4160518/triage_results.json")

    appraisal_cache_path = Path("data/aug22_gallery_4160518/appraisal_results.json")
    if not appraisal_cache_path.exists():
        appraisal_cache_path = Path("/app/data/aug22_gallery_4160518/appraisal_results.json")

    grounded_cache_path = Path("data/aug22_gallery_4160518/grounded_prices.json")
    if not grounded_cache_path.exists():
        grounded_cache_path = Path("/app/data/aug22_gallery_4160518/grounded_prices.json")
    grounded_rows = []
    if grounded_cache_path.exists():
        try:
            grounded_rows = json.loads(grounded_cache_path.read_text())
        except Exception as e:
            print(f"[!] Warning: Could not parse grounded pricing cache: {e}")
    grounded_by_lot = {row.get("lot_id"): row for row in grounded_rows}
    cycle_comps = dict(REFERENCE_COMPS)
    if sheet == "full":
        cycle_comps = {
            **grounded_reference_comps(grounded_rows),
            **cycle_comps,
        }

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
                cat_hint = cycle_comps.get(lot_id, {}).get("cat")
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
        if lot_tag in cycle_comps:
            comp_info = cycle_comps[lot_tag]
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
    for k, v in cycle_comps.items():
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
        source_manifest = embed_cache_path.with_name("manifest.json")
        edges = load_reshoot_edges(
            embed_cache_path, photo_by_seq, sequences, gallery_ids=gallery_ids,
            expected_manifest_sha256=(
                sha256_file(source_manifest) if source_manifest.is_file() else "missing"
            ),
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
    lots = (
        apply_lot_rulings(
            lots, rulings=(), operator_approved=OPERATOR_APPROVED,
        )
        if sheet == "sent"
        else apply_lot_rulings(lots)
    )

    # 4. BidMath Pricing & Allocation
    decisions = []
    for lot in lots:
        decision = apply_operator_cap(price_lot(lot))
        if decision.needs_deep_comps:
            decision = replace(
                decision,
                reason=grounded_status_reason(grounded_by_lot.get(lot.lot_id)),
            )
        decisions.append(decision)
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
    queue_res = build_queue(
        all_questions,
        current_rules(),
        cap=12,
        lot_rulings=current_rulings(),
    )

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
        "answer_auth": "required" if os.environ.get("OPERATOR_TOKEN") else "disabled",
        "python": sys.version.split()[0],
        "cycle_storage": CYCLES.backend_name if CYCLES else "disabled",
        "cycle_job_configured": bool(CYCLE_JOBS and CYCLE_JOBS.configured),
    }


@app.get("/", response_class=HTMLResponse)
def get_console():
    photos, seats, lots, decisions, summary, queue_res, captions_map = get_aug22_state()
    pitch = build_pitch(decisions, captions_map, current_rules())
    # Unit tests must stay credential-free and fast. Cloud Run has no
    # PYTEST_CURRENT_TEST, so Gemma runs there (then caches).
    live_client = None if os.environ.get("PYTEST_CURRENT_TEST") else engine.client
    # A matching-key cache entry wins even with no client, so the cache location
    # must be overridable: a local uvicorn run sharing /tmp with pytest would
    # feed its live voice to the next test run.
    cache = Path(os.environ.get("BTF_VOICE_CACHE", "/tmp/btf_gemma_voice.json"))
    voice = write_pitch_voice(
        pitch, client=live_client, cache_path=cache, telemetry=engine.telemetry,
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
        cycle_controls=bool(
            CYCLES and CYCLE_JOBS and CYCLE_JOBS.configured
            and (os.environ.get("OPERATOR_TOKEN") or not os.environ.get("K_SERVICE"))
        ),
    )
    return render_console(view)


def _manifest_by_sequence() -> dict[int, dict]:
    """The gallery manifest indexed by sequence, parsed once per process.

    The walk strip requests up to 462 photos per page load; re-parsing the
    manifest per request (as the per-lot byte helper does) would multiply one
    JSON parse by every tile.
    """
    global _MANIFEST_BY_SEQ
    if _MANIFEST_BY_SEQ is None:
        manifest_path = Path("data/aug22_gallery_4160518/manifest.json")
        if not manifest_path.exists():
            manifest_path = Path("/app/data/aug22_gallery_4160518/manifest.json")
        photos = (json.loads(manifest_path.read_text())["photos"]
                  if manifest_path.exists() else [])
        _MANIFEST_BY_SEQ = {int(p["sequence"]): p for p in photos}
    return _MANIFEST_BY_SEQ


_MANIFEST_BY_SEQ: dict[int, dict] | None = None


@app.get("/walk", response_class=HTMLResponse)
def walk_strip():
    photos, seats, *_ = get_aug22_state()
    # Seats speak in lot ids (BT-<seq>), the manifest in gallery photo ids.
    # Translate each seat member back to the manifest id at its sequence so
    # the strip can join them; a member that is not a BT id passes through.
    pid_by_seq = {int(p["sequence"]): str(p["photo_id"]) for p in photos}

    def manifest_pid(member: str) -> str:
        if member.startswith("BT-") and member[3:].isdigit():
            return pid_by_seq.get(int(member[3:]), member)
        return member

    translated = [
        replace(s, photo_ids=tuple(manifest_pid(m) for m in s.photo_ids))
        for s in seats
    ]
    return render_walk_strip(
        photos, translated,
        cycle_id=STATE["cycle_id"], listing_id=STATE["listing_id"],
    )


@app.get("/walk/photo/{seq}")
def walk_photo(seq: int):
    """One gallery thumbnail: cached bytes when the container has them, else a
    redirect to the CDN thumb the manifest recorded. A deployed --source build
    carries only the force-added evidence images, so the redirect is the normal
    path on Cloud Run; the 404 is reserved for a sequence the manifest never
    listed."""
    entry = _manifest_by_sequence().get(seq)
    if entry is None:
        raise HTTPException(status_code=404, detail="no such photo in the manifest")
    path = Path(entry.get("local_path") or "")
    if path.is_file():
        payload = path.read_bytes()
        mime = "image/webp" if payload[:4] == b"RIFF" else "image/jpeg"
        return Response(content=payload, media_type=mime)
    thumb = str(entry.get("thumb_url") or "")
    if thumb.startswith("//"):
        thumb = "https:" + thumb
    if thumb.startswith("https://"):
        return RedirectResponse(thumb, status_code=302)
    raise HTTPException(status_code=404, detail="no cached bytes and no CDN thumb")


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
            "decision": (
                "AUTO-SEND" if d and d.auto_send and d.allocated
                else "NEEDS APPROVAL" if d and d.allocated
                else "NEEDS DEEPER COMPS" if d and d.needs_deep_comps
                and d.reason.startswith("needs deeper comps")
                else "DEEP COMPS RETRY PENDING" if d and d.needs_deep_comps
                and d.reason.startswith("deep comps retry")
                else "PENDING DEEP COMPS" if d and d.needs_deep_comps
                else "PENDING RULING" if d and d.needs_mechanic_ruling
                else "SKIPPED"
            ),
            "reason": d.reason if d else None,
        })
    remainder = [
        opportunity
        for decision in decisions
        if (opportunity := remainder_opportunity(decision)) is not None
    ]
    return {
        "total": len(out),
        "summary": summary.__dict__,
        "lots": out,
        "contingent_remainder_opportunities": [
            {
                "lot_id": decision.lot_id,
                "source_lot_id": decision.lot_id.removesuffix("-R"),
                "committed_max": decision.committed_max,
                "committed_all_in": decision.committed_all_in,
                "directive": clerk_directive(decision),
            }
            for decision in remainder
        ],
    }


@app.get("/api/questions")
def list_questions():
    _, _, _, _, _, queue_res, _ = get_aug22_state()
    return {
        "accounting": queue_res.accounting(),
        "asked": [
            {
                "question_id": make_question_id(STATE["cycle_id"], q),
                "expected_revision": 0,
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
        "deferred": [
            {"kind": q.kind.value, "lot_ids": list(q.lot_ids), "prompt": q.prompt}
            for q in queue_res.deferred
        ],
        "dropped": [
            {"kind": q.kind.value, "lot_ids": list(q.lot_ids), "prompt": q.prompt}
            for q in queue_res.dropped
        ],
    }


def _require_operator(x_operator_token: str | None) -> None:
    expected = os.environ.get("OPERATOR_TOKEN")
    if os.environ.get("K_SERVICE") and not expected:
        raise HTTPException(
            status_code=503,
            detail="operator actions are disabled until OPERATOR_TOKEN is configured",
        )
    if not expected:
        return
    if (x_operator_token or "") != expected:
        raise HTTPException(status_code=401, detail="operator token required")


def _operator_actor() -> str:
    return (os.environ.get("OPERATOR_ACTOR") or "authenticated_operator").strip()


def _require_cycle_operator(x_operator_token: str | None) -> None:
    """Keep the cycle boundary explicit even though all mutations share auth."""
    _require_operator(x_operator_token)


def _configured_cycles():
    if CYCLES is None:
        raise HTTPException(
            status_code=503,
            detail="cycle storage is disabled; set BTF_CYCLE_BUCKET",
        )
    return CYCLES


def _launch_staged_cycle(request) -> dict:
    repo = _configured_cycles()
    if CYCLE_JOBS is None or not CYCLE_JOBS.configured:
        raise HTTPException(
            status_code=503,
            detail="cycle processor is disabled; set BTF_CYCLE_JOB",
        )
    try:
        claimed = repo.claim_launch(request)
    except CycleNotFound as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not claimed:
        status = repo.read_status(request)
        return {"launched": False, "deduplicated": True, "status": status.as_dict()}
    try:
        operation = CYCLE_JOBS.launch(request)
        status = CycleStatus.make(
            request, "running", "Cloud Run Job accepted the staged cycle",
            operation_name=operation,
        )
        repo.write_status(status)
        return {"launched": True, "deduplicated": False,
                "operation_name": operation, "status": status.as_dict()}
    except Exception as exc:
        # Eventarc retries are useful only if a transient launch failure can
        # release the idempotency claim.
        repo.release_launch(request)
        repo.write_status(CycleStatus.make(request, "failed", str(exc)[:1000]))
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/cycles/start", status_code=202)
def start_cycle(
    payload: dict = Body(...),
    x_operator_token: str | None = Header(default=None),
):
    """Explicitly start a fully staged cycle; never accepts local file paths."""
    _require_cycle_operator(x_operator_token)
    cycle_id = (payload.get("cycle_id") or "").strip()
    shop_id = (payload.get("shop_id") or SHOP_ID).strip()
    if not cycle_id:
        raise HTTPException(status_code=400, detail="cycle_id is required")
    repo = _configured_cycles()
    try:
        request = repo.read_request(shop_id, cycle_id)
    except (CycleNotFound, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not repo.is_ready(request):
        try:
            repo.mark_ready(request)
        except CycleConflict:
            # A simultaneous console click or Eventarc delivery won the race.
            if not repo.is_ready(request):
                raise
    return _launch_staged_cycle(request)


@app.post("/api/events/storage", status_code=202)
def storage_event(payload: dict = Body(...)):
    """Eventarc receiver. Only a durable READY marker can launch work."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    bucket = str(data.get("bucket") or "").removeprefix("gs://").rstrip("/")
    name = str(data.get("name") or "")
    expected_bucket = os.environ.get("BTF_CYCLE_BUCKET", "").removeprefix("gs://").rstrip("/")
    if not expected_bucket or bucket != expected_bucket:
        return {"ignored": True, "reason": "unexpected bucket"}
    parts = name.split("/")
    if (len(parts) != 6 or parts[0] != "shops" or parts[2] != "cycles"
            or parts[4:] != ["control", "READY.json"]):
        return {"ignored": True, "reason": "not a cycle READY marker"}
    shop_id, cycle_id = parts[1], parts[3]
    repo = _configured_cycles()
    try:
        request = repo.read_request(shop_id, cycle_id)
    except (CycleNotFound, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _launch_staged_cycle(request)


@app.get("/api/cycles/current")
def current_cycle():
    repo = _configured_cycles()
    try:
        active = repo.get_json(repo.active_name(SHOP_ID))
        request = repo.read_request(SHOP_ID, active["cycle_id"])
        return {"active": active, "request": request.as_dict(),
                "status": repo.read_status(request).as_dict()}
    except CycleNotFound as exc:
        raise HTTPException(status_code=404, detail="no completed cycle") from exc


@app.get("/api/cycles/{cycle_id}")
def cycle_status(cycle_id: str):
    repo = _configured_cycles()
    try:
        request = repo.read_request(SHOP_ID, cycle_id)
        return {"request": request.as_dict(),
                "status": repo.read_status(request).as_dict(),
                "ready": repo.is_ready(request)}
    except (CycleNotFound, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
        if payload.get("expected_revision") is not None:
            raise HTTPException(
                status_code=409,
                detail="question or authority revision is stale; reload the queue",
            )
        raise HTTPException(
            status_code=404, detail="question is not on the current desk queue",
        )

    before = {
        "asked": len(queue_res.asked),
        "auto_answered": len(queue_res.auto_answered),
        "allocated": [d.lot_id for d in decisions if d.allocated],
        "committed_max": summary.committed_max,
        "committed_all_in": summary.committed_all_in,
        "decisions": {
            decision.lot_id: {
                "allocated": decision.allocated,
                "mechanic": decision.mechanic.value,
                "unit_count": decision.unit_count,
                "units_wanted": decision.units_wanted,
                "max_bid": decision.max_bid,
                "committed_max": decision.committed_max,
            }
            for decision in decisions
            if decision.lot_id in question.lot_ids
        },
    }

    promoted = learn([(question, ans)], cycle=STATE["cycle_id"])
    learned_rulings = learn_rulings([(question, ans)], cycle=STATE["cycle_id"])
    stored = None
    authority_type = None
    if not promoted and not learned_rulings:
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

    try:
        if learned_rulings:
            ruling = learned_rulings[0]
            stored = RULES.put_ruling(LotRulingRecord(
                shop_id=SHOP_ID,
                cycle_id=STATE["cycle_id"],
                kind=ruling.kind,
                lot_ids=ruling.lot_ids,
                cluster_id=ruling.cluster_id,
                answer=ruling.answer,
                source_question_id=qid,
                actor=_operator_actor(),
            ), expected_revision=payload.get("expected_revision"))
            authority_type = "lot_ruling"
        else:
            new_rule = promoted[0]
            stored = RULES.put(StandingRuleRecord(
                shop_id=SHOP_ID,
                kind=new_rule.kind,
                category=new_rule.category,
                answer=new_rule.answer,
                learned_cycle=new_rule.learned_cycle,
                source_question_id=qid,
                actor=_operator_actor(),
            ), expected_revision=payload.get("expected_revision"))
            authority_type = "standing_policy"
    except MemoryConflict as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    _, _, _, after_decisions, after_summary, after_queue, _ = get_aug22_state()
    after = {
        "asked": len(after_queue.asked),
        "auto_answered": len(after_queue.auto_answered),
        "allocated": [d.lot_id for d in after_decisions if d.allocated],
        "committed_max": after_summary.committed_max,
        "committed_all_in": after_summary.committed_all_in,
        "decisions": {
            decision.lot_id: {
                "allocated": decision.allocated,
                "mechanic": decision.mechanic.value,
                "unit_count": decision.unit_count,
                "units_wanted": decision.units_wanted,
                "max_bid": decision.max_bid,
                "committed_max": decision.committed_max,
            }
            for decision in after_decisions
            if decision.lot_id in question.lot_ids
        },
    }
    return {
        "status": "applied",
        "promoted": True,
        "question_id": qid,
        "authority_type": authority_type,
        "rule": {
            "rule_id": (stored.ruling_id if authority_type == "lot_ruling"
                        else stored.rule_id),
            "revision": stored.revision,
            "kind": stored.kind.value,
            "category": getattr(stored, "category", question.category),
            "answer": stored.answer,
            "learned_cycle": (stored.cycle_id if authority_type == "lot_ruling"
                              else stored.learned_cycle),
            "source_question_id": stored.source_question_id,
            "lot_ids": list(getattr(stored, "lot_ids", ())),
            "cluster_id": getattr(stored, "cluster_id", None),
        },
        "affected_lots": list(question.lot_ids),
        "before": before,
        "after": after,
        "appraisal_source": "cached_sheet",
        "pending_reappraisal": False,
        "money_changed": (
            before["committed_max"] != after["committed_max"]
            or before["committed_all_in"] != after["committed_all_in"]
        ),
        "standing_rules_count": len(current_rules()),
        "lot_rulings_count": len(current_rulings()),
    }


@app.get("/api/memory")
def list_memory():
    rules = current_rules()
    rulings = current_rulings()
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
        "lot_rulings": [
            {
                "kind": ruling.kind.value,
                "answer": ruling.answer,
                "learned_cycle": ruling.learned_cycle,
                "lot_ids": list(ruling.lot_ids),
                "cluster_id": ruling.cluster_id,
            }
            for ruling in rulings
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
