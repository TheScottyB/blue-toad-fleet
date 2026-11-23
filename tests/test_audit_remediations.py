"""Regression tests pinning all security, financial, pipeline, and comps audit remediations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from scripts.cache_estatesales import (
    _IMAGE_HOSTS,
    cache_estatesales,
    fetch_listing_html,
    parse_listing_html,
    parse_sale_url,
)
from scripts.cache_gallery import download_image
from scripts.collect_submission_facts import _publication_facts, _test_counts
from scripts.import_ebay_absorption import import_capture
from scripts.video_common import VideoBuildError
from src import server as server_mod
from src.appraiser.containers import price_container_evidence
from src.appraiser.engine import AppraisalEngine
from src.appraiser.grounded_batch import price_one_grounded, run_grounded_pricing_batch
from src.appraiser.pricing import GroundedPrice, parse_price_payload, price_is_usable
from src.assemble import AppraisedPhoto, assemble_lots, compile_absentee_email
from src.bidmath import (
    BidMechanic,
    CompEstimate,
    Confidence,
    Lot,
    Priority,
    allocate,
    elect,
    mechanic_from_ruling,
    price_lot,
    remainder_opportunity,
    snap_to_increment,
)
from src.comps import ChallengePage, SuspectEmpty, parse_active_response
from src.comps import live as comps_live
from src.comps.live import ResearchSession as RealResearchSession
from src.cycles.model import CycleRequest
from src.cycles.storage import CycleNotFound, CycleRepository, LocalObjectStore
from src.cycles.worker import _require_publishable_output
from src.evidence.model import AbsorptionEvidence
from src.memory.store import FileRuleStore


ROOT = Path(__file__).resolve().parents[1]


# --- Phase 1: Immediate Production Containment (C-01, H-01, H-03, M-03) ---

def test_c01_live_vertex_endpoints_require_operator_token(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "blue-toad-fleet")
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    client = TestClient(server_mod.app)
    assert client.post("/api/appraise", json={"lot_id": "BT-001"}).status_code == 503
    assert client.post("/api/decompose", json={"lot_id": "BT-001"}).status_code == 503

    monkeypatch.setenv("OPERATOR_TOKEN", "secret-token\n")
    assert client.post("/api/appraise", json={"lot_id": "BT-001"}).status_code == 401
    assert client.post("/api/decompose", json={"lot_id": "BT-001"}).status_code == 401
    assert (
        client.post(
            "/api/appraise",
            json={"lot_id": "BT-001"},
            headers={"X-Operator-Token": "wrong"},
        ).status_code
        == 401
    )


def test_h01_eventarc_endpoint_enforces_oidc_in_cloud(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "blue-toad-fleet")
    monkeypatch.setenv("BTF_EVENTARC_INVOKER_EMAIL", "invoker@proj.iam.gserviceaccount.com")
    client = TestClient(server_mod.app)
    event = {"data": {"bucket": "b", "name": "shops/s/cycles/c/control/READY.json"}}

    # Missing bearer token -> 401
    assert client.post("/api/events/storage", json=event).status_code == 401

    # Wrong service account -> 403
    monkeypatch.setattr(
        server_mod,
        "_verify_oidc_token",
        lambda tok, aud: {"email": "attacker@evil.iam.gserviceaccount.com", "email_verified": True},
    )
    assert (
        client.post(
            "/api/events/storage",
            json=event,
            headers={"Authorization": "Bearer fake-jwt"},
        ).status_code
        == 403
    )

    # Verified Eventarc invoker -> passes auth (ignored bucket 202)
    monkeypatch.setattr(
        server_mod,
        "_verify_oidc_token",
        lambda tok, aud: {"email": "invoker@proj.iam.gserviceaccount.com", "email_verified": True},
    )
    res = client.post(
        "/api/events/storage",
        json=event,
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert res.status_code == 202
    assert res.json()["ignored"] is True


def test_h03_nan_inf_and_untyped_mutation_payloads_rejected_cleanly():
    server_mod.reset_operator_sheet()
    client = TestClient(server_mod.app)

    for bad_bid in ("nan", "inf", "-inf", True, "abc", 10_000_000):
        res = client.post("/api/sheet/price", json={"lot_id": "BT-001", "max_bid": bad_bid})
        assert res.status_code == 400, f"accepted {bad_bid!r}: {res.text}"

    # /api/lots and /api/audit must remain 200 OK (never bricked by NaN)
    assert client.get("/api/lots").status_code == 200
    assert client.get("/api/audit").status_code == 200

    # Non-string fields and non-bool want return 400, never 500 AttributeError
    assert client.post("/api/sheet/elect", json={"lot_id": 123, "want": True}).status_code == 400
    assert client.post("/api/sheet/elect", json={"lot_id": "BT-001", "want": "false"}).status_code == 400
    assert client.post("/api/walk/edge", json={"status": 123, "seq_a": 1, "seq_b": 2}).status_code == 400
    assert client.post("/api/answer", json={"question_id": "q", "answer": 999}).status_code == 400

    # Over-cap human price rolls back cleanly with 409
    res_over = client.post("/api/sheet/price", json={"lot_id": "BT-001", "max_bid": 600})
    assert res_over.status_code == 409
    assert "BT-001" not in server_mod.OPERATOR_SHEET.human_caps

    with pytest.raises(ValueError):
        snap_to_increment(float("nan"))
    with pytest.raises(ValueError):
        snap_to_increment(float("inf"))


def test_h03_operator_desk_edits_persist_across_durable_store_reloads(tmp_path, monkeypatch):
    store_file = tmp_path / "rules.json"
    store_a = FileRuleStore(store_file, shop_id=server_mod.SHOP_ID)
    monkeypatch.setattr(server_mod, "RULES", store_a)
    client = TestClient(server_mod.app)

    res = client.post("/api/sheet/elect", json={"lot_id": "BT-001", "want": False})
    assert res.status_code == 200

    # Simulate Cloud Run container recycle: fresh FileRuleStore reading the durable state
    store_b = FileRuleStore(store_file, shop_id=server_mod.SHOP_ID)
    monkeypatch.setattr(server_mod, "RULES", store_b)
    lots = {row["lot_id"]: row for row in client.get("/api/lots").json()["lots"]}
    assert lots["BT-001"]["allocated"] is False


def test_m03_dockerignore_excludes_local_secrets_and_agent_dirs():
    lines = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    for required in (".env", ".env.*", ".claude", ".playwright-mcp", "data/memory"):
        assert required in lines


# --- Phase 2: Real-Money & Absentee-Email Safety (C-04, C-05, H-06) ---

def test_c04_unruled_ttm_and_choice_captions_refuse_until_ruled():
    photo = AppraisedPhoto(
        photo_id="BT-014",
        caption="3 jewelry trays — times the money",
        identification="Three jewelry trays",
        category="jewelry",
        fit_score=0.9,
        confidence=Confidence.HIGH,
    )
    [lot] = assemble_lots(
        [photo],
        comps={"seq:BT-014": CompEstimate(200.0, 280.0, 3, Confidence.HIGH)},
    )
    assert lot.mechanic is BidMechanic.UNKNOWN
    decision = price_lot(lot)
    assert decision.max_bid is None
    assert decision.needs_mechanic_ruling is True


def test_c05_unelected_or_unruled_decisions_never_enter_absentee_email():
    unelected = Lot(
        "BT-100",
        "Five shelf lantern unit",
        "railroad",
        0.9,
        0.0,
        CompEstimate(200.0, 280.0, 3, Confidence.HIGH),
        mechanic=BidMechanic.CHOICE,
        unit_count=5,
        units_wanted=None,
    )
    d = price_lot(unelected)
    assert d.needs_election is True
    alloc = allocate([d], budget_cap=1000.0)
    assert alloc[0].allocated is False

    # Even if a caller forces allocated=True, compile_absentee_email refuses to emit it
    from dataclasses import replace
    email = compile_absentee_email(
        to="info@bluetoadauctions.com\r\nBCC: attacker@evil.test",
        subject="Absentee\nSubject",
        auction_date="Saturday",
        venue="Genoa City",
        lots=[unelected],
        decisions=[replace(d, allocated=True)],
    )
    assert "BT-100" not in email
    assert "\r" not in email
    assert "BCC: attacker@evil.test" not in email.splitlines()


@pytest.mark.parametrize(
    "ruling",
    [
        "No, they are not combined",
        "Not sold as a unit",
        "They don't go as one lot",
        "It does not go as a single lot",
        "Not 3x the money",
        "That isn't ×3",
        "Not selling as buyer's choice",
        "Is this buyer's choice or times the money for all 5?",
        "Rather than buyer's choice, it is times the money on all 5",
        "Buyer's choice on the x5 shelf",
        "Times the money, all 14 kt gold rings",
    ],
)
def test_c05_mechanic_from_ruling_refuses_negations_and_ambiguities(ruling):
    assert mechanic_from_ruling(ruling)[0] is BidMechanic.UNKNOWN


def test_c05_choice_of_k_of_n_extracts_pool_count_and_election():
    assert mechanic_from_ruling("Buyer's choice of 1 of the 5 shelves") == (
        BidMechanic.CHOICE,
        5,
        1,
    )
    assert mechanic_from_ruling("Buyer's choice of two out of the six chairs") == (
        BidMechanic.CHOICE,
        6,
        2,
    )


def test_h06_contingent_remainders_respect_cumulative_cap_and_skip_declined():
    skip_lot = elect(
        Lot(
            "BT-SKIP",
            "Declined dolls",
            "dolls",
            0.1,
            0.0,
            CompEstimate(100.0, 140.0, 3, Confidence.HIGH),
            mechanic=BidMechanic.CHOICE,
            unit_count=5,
        ),
        1,
    )
    assert remainder_opportunity(price_lot(skip_lot)) is None

    choice = elect(
        Lot(
            "BT-100",
            "Five shelf lantern unit",
            "railroad",
            0.9,
            0.0,
            CompEstimate(200.0, 280.0, 3, Confidence.HIGH),
            mechanic=BidMechanic.CHOICE,
            unit_count=5,
        ),
        2,
    )
    primary = price_lot(choice)  # $15 * 2 = $30 hammer, $34.50 all-in
    rem = remainder_opportunity(primary)  # $5 * 3 = $15 hammer, $17.25 all-in
    assert rem is not None

    # Cap $40 fits primary ($34.50) but cannot fit cumulative primary + remainder ($51.75)
    out = {d.lot_id: d for d in allocate([primary, rem], budget_cap=40.0)}
    assert out["BT-100"].allocated is True
    assert out["BT-100-R"].allocated is False

    # Cap $60 fits both, and email keeps total committed bids reconciled
    out_ok = allocate([primary, rem], budget_cap=60.0)
    email = compile_absentee_email(
        to="info@bluetoadauctions.com",
        subject="Bids",
        auction_date="Sat",
        venue="WI",
        lots=[choice],
        decisions=out_ok,
    )
    assert "Five shelf lantern unit" in email
    assert "TOTAL COMMITTED PROXY BIDS: $30.00 ($34.50 all-in" in email
    assert "BT-100-R is an exception" not in email


# --- Phase 3: Cloud Cycle & Grounding Reliability (C-03, C-06, H-05) ---

def test_c03_explicit_output_pipeline_publishes_all_stage_artifacts_for_worker(tmp_path):
    from scripts.run_vertex_pipeline import PipelineConfig, execute_pipeline

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    images = input_dir / "images"
    images.mkdir(parents=True)
    # 1200x900 valid JPEG header
    jpeg = (
        b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
        b"\xFF\xC0\x00\x11\x08\x03\x84\x04\xB0\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01\xFF\xD9"
    )
    img_path = images / "001_p1.jpg"
    img_path.write_bytes(jpeg)
    (input_dir / "manifest.json").write_text(
        json.dumps({
            "listing_id": "999",
            "captioned_photos": 1,
            "photos": [{
                "sequence": 1,
                "photo_id": "p1",
                "filename": "001_p1.jpg",
                "thumb_url": "https://picturescdn.estatesales.net/999/1/1-t.jpg",
                "caption": "Lot 1 crock",
                "has_caption": True,
                "local_path": str(img_path),
            }],
        })
    )
    (input_dir / "triage_results.json").write_text(
        json.dumps([{
            "photo_id": "p1",
            "is_lot": True,
            "same_lot_as_previous": False,
            "category": "stoneware",
            "summary": "Lot 1 crock",
            "fit_score": 0.85,
            "worth_appraising": True,
            "needs_decomposition": False,
            "model_used": "gemini-3.5-flash-lite",
        }])
    )
    (input_dir / "appraisal_results.json").write_text(
        json.dumps([{
            "lot_id": "BT-001",
            "identification": "Red Wing 5 gallon crock",
            "category": "stoneware",
            "fit_score": 0.85,
            "condition_penalty": 0.0,
            "confidence": "high",
            "questions": [],
            "model_used": "gemini-3.6-flash",
            "container_decomposition": {
                "is_container_lot": True,
                "container_type": "shelf",
                "components": [],
                "open_questions": [],
            },
        }])
    )
    (input_dir / "grounded_prices.json").write_text("[]")
    (input_dir / "grounded_prices_attempts.json").write_text("[]")

    execute_pipeline(
        PipelineConfig(
            cycle_id="2026-09-05",
            listing_id="999",
            data_dir=input_dir,
            output_dir=output_dir,
            budget_cap=600.0,
            auto_send_threshold=0.0,
            auction_title="Test Sale",
            auction_date="2026-09-05",
            auction_timezone="America/Chicago",
            auction_deadline="2026-09-04T20:00:00-05:00",
            venue="Genoa City, WI",
            reference_comps={
                "BT-001": {
                    "cat": "stoneware",
                    "desc": "Red Wing crock",
                    "container_evidence": {
                        "bulk_floor": {
                            "low": 40,
                            "high": 60,
                            "source_count": 2,
                            "citations": ["https://www.ebay.com/itm/111"],
                        },
                    },
                },
            },
            operator_approved={},
            standing_rules=(),
            cycle_questions=(),
            enable_grounded_pricing=True,
            pricing_engine_factory=lambda: MagicMock(
                price_lot_grounded=MagicMock(return_value=None)
            ),
        )
    )
    # Previously crashed with RuntimeError: pipeline produced no readable triage_results.json
    _require_publishable_output(input_dir, output_dir)


def test_c06_grounding_extract_quota_error_propagates_as_incomplete_attempt():
    engine = AppraisalEngine()
    engine._client = object()

    search_resp = MagicMock()
    search_resp.text = "Sold for $50 and $60 on eBay."
    search_resp.candidates = []

    calls = {"n": 0}

    def fake_gen(*, stage, **kwargs):
        calls["n"] += 1
        if stage == "grounding.search":
            return search_resp
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    engine._generate = fake_gen
    row = price_one_grounded(
        {"lot_id": "BT-001", "identification": "sign", "category": "adv", "fit_score": 0.9},
        engine_factory=lambda: engine,
    )
    assert row["attempt_complete"] is False
    assert len(row["errors"]) == 3


def test_h05_grounded_pricing_requires_every_sample_cited_usd_and_tight_low_spread():
    cited = ["https://www.ebay.com/itm/12345"]
    # 2 uncited hallucinations + 1 cited 0-comp sample -> refused
    assert not price_is_usable([
        GroundedPrice(50, 60, 3, []),
        GroundedPrice(50, 60, 3, []),
        GroundedPrice(45, 65, 0, cited),
    ])
    # Wild low-bound spread ($5 vs $480) -> refused
    assert not price_is_usable([
        GroundedPrice(5, 500, 3, cited),
        GroundedPrice(450, 500, 3, cited),
        GroundedPrice(480, 500, 3, cited),
    ])
    # Non-USD currency -> refused
    assert (
        parse_price_payload(
            {"low": 15000, "high": 20000, "sold_comp_count": 4, "asking_prices_only": False, "currency": "JPY"},
            grounded_sources=cited,
        )
        is None
    )
    # Unconfirmed container alpha with placeholder mark -> bulk floor only
    res = price_container_evidence(
        {
            "is_container_lot": True,
            "contents": [{
                "item_name": "Leica M3",
                "market_role": "alpha",
                "marks_observed": ["illegible"],
            }],
            "questions": ["Is it genuine or a Soviet copy?"],
        },
        alpha_comp={"low": 1200, "high": 1600, "source_count": 3, "citations": cited},
        bulk_floor={"low": 25, "high": 40, "source_count": 2, "citations": cited},
    )
    assert res.alpha_confirmed is False
    assert (res.low, res.high) == (25.0, 40.0)


def test_h05_grounded_batch_preserves_previously_cached_rows_outside_min_fit(tmp_path):
    cache = tmp_path / "grounded_prices.json"
    prior = {"lot_id": "BT-010", "usable": True, "attempt_complete": True, "low": 40, "high": 60}
    cache.write_text(json.dumps([prior]))
    run_grounded_pricing_batch(
        [{"lot_id": "BT-010", "identification": "x", "category": "c", "fit_score": 0.72}],
        cache,
        min_fit=0.90,
        engine_factory=lambda: None,
    )
    saved = {r["lot_id"]: r for r in json.loads(cache.read_text())}
    assert "BT-010" in saved


# --- Phase 4: Seller Hub Comps, Scrapers & Release Hygiene (C-02, H-04, H-07, H-08, H-11) ---

def test_c02_estatesales_blocks_ssrf_and_path_traversal(tmp_path):
    with pytest.raises(ValueError, match="expected"):
        parse_sale_url("http://169.254.169.254/WI/Genoa-City/53128/12345")
    with pytest.raises(ValueError, match="expected"):
        parse_sale_url("https://evil.example/WI/Genoa-City/53128/12345")
    with pytest.raises(ValueError, match="disallowed"):
        fetch_listing_html("http://127.0.0.1:8080/sale/12345")

    redirect_resp = MagicMock()
    redirect_resp.geturl.return_value = "https://169.254.169.254/latest/meta-data"
    redirect_resp.read.return_value = b"<html></html>"
    redirect_resp.__enter__.return_value = redirect_resp
    with pytest.raises(ValueError, match="disallowed"):
        fetch_listing_html(
            "https://www.estatesales.net/WI/Genoa-City/53128/5042877",
            opener=lambda *_args, **_kwargs: redirect_resp,
        )

    res = download_image(
        "file:///etc/passwd", tmp_path / "out.jpg", allowed_hosts=_IMAGE_HOSTS,
    )
    assert not res.ok and "disallowed" in res.error

    traversal_res = download_image(
        "https://picturescdn.estatesales.net/1/1/a.jpg",
        tmp_path / ".." / "out.jpg",
        allowed_hosts=_IMAGE_HOSTS,
    )
    assert not traversal_res.ok and "unsafe" in traversal_res.error

    ssrf_cdn_html = """<script>{"NGRX_STATE":{"feature.traditionalSaleViewState":{
        "activeId":"5042877","entitiesById":{"5042877":{"saleId":5042877,"name":"x",
        "pictures":[{"id":"1","pictureOrder":0,"url":"https://169.254.169.254/a.jpg"}]
    }}}}}</script>"""
    with pytest.raises(ValueError, match="disallowed"):
        parse_listing_html(ssrf_cdn_html, "5042877")

    evil_html = """<script>{"NGRX_STATE":{"feature.traditionalSaleViewState":{
        "activeId":"5042877","entitiesById":{"5042877":{"saleId":5042877,"name":"x",
        "pictures":[{"id":"/../../../../tmp/pwn","url":"https://picturescdn.estatesales.net/1/1/a.jpg"}]
    }}}}}</script>"""
    html_resp = MagicMock()
    html_resp.read.return_value = evil_html.encode()
    html_resp.geturl.return_value = "https://www.estatesales.net/WI/Genoa-City/53128/5042877"
    html_resp.__enter__.return_value = html_resp
    with pytest.raises(ValueError, match="unsafe picture id"):
        cache_estatesales(
            "https://www.estatesales.net/WI/Genoa-City/53128/5042877",
            tmp_path / "sale",
            download_images=False,
            opener=lambda *_args, **_kwargs: html_resp,
        )


def test_h04_stage_directory_confines_local_path_and_mark_ready_checks_images(tmp_path):
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret-bytes")
    src = tmp_path / "drop"
    src.mkdir()
    (src / "manifest.json").write_text(
        json.dumps({
            "listing_id": "4160518",
            "photos": [{
                "sequence": 1,
                "photo_id": "p1",
                "filename": "001.jpg",
                "local_path": str(outside),
            }],
        })
    )
    repo = CycleRepository(LocalObjectStore(tmp_path / "store"))
    req = CycleRequest(
        cycle_id="2026-09-05",
        listing_id="4160518",
        auction_title="Sale",
        auction_date="2026-09-05",
        timezone_name="America/Chicago",
        venue="WI",
        deadline="2026-09-04T20:00:00-05:00",
    )
    with pytest.raises(ValueError, match="unsafe image local_path"):
        repo.stage_directory(req, src)

    # Incomplete upload without image blobs cannot be marked ready
    repo.put_json(repo.request_name(req), req.as_dict(), if_absent=True)
    repo.put_json(
        f"{req.prefix}/input/manifest.json",
        {"photos": [{"filename": "001.jpg", "source_object": f"{req.prefix}/input/images/001.jpg"}]},
        if_absent=True,
    )
    with pytest.raises(CycleNotFound, match="incomplete"):
        repo.mark_ready(req)


def test_h07_signin_ebay_com_and_opaque_redirects_fast_fail_as_challenge_page():
    sess = RealResearchSession()

    async def fake_eval_signin(_expr, timeout):
        return {"host": "signin.ebay.com", "path": "/ws/eBayISAPI.dll", "state": "complete"}

    sess._eval = fake_eval_signin
    with pytest.raises(ChallengePage, match="signin.ebay.com"):
        asyncio.run(sess._wait_ready(timeout=1.0))

    async def fake_eval_redirect(_expr, timeout):
        return {"status": 0, "rtype": "opaqueredirect", "type": "", "body": ""}

    sess._eval = fake_eval_redirect
    with pytest.raises(ChallengePage, match="signed out or challenged"):
        asyncio.run(sess.get("/sh/research/api/search?keywords=test"))
    assert sess._poisoned is True


def test_h07_parse_active_response_rejects_unloaded_zero_and_missing_denominator():
    # Unloaded 0-row response with Total active listings = 0 but NO zero-results message
    unloaded = "\n".join([
        json.dumps({
            "_type": "ResearchAggregateModule",
            "sections": [{"dataItems": [{
                "header": {"textSpans": [{"text": "Total active listings"}]},
                "value": {"textSpans": [{"text": "0"}]},
            }]}],
        }),
        json.dumps({"_type": "ActiveSearchResultsModule", "results": []}),
    ])
    with pytest.raises(SuspectEmpty):
        parse_active_response(unloaded)

    # Non-empty rows without Total active listings aggregate -> refuses capped fallback
    no_agg = json.dumps({
        "_type": "ActiveSearchResultsModule",
        "results": [{"listing": {"title": {"textSpans": [{"text": "Item"}]}}}],
    })
    with pytest.raises(SuspectEmpty, match="capped row count"):
        parse_active_response(no_agg)


def test_h08_absorption_evidence_handles_zero_sales_and_rejects_incomplete_substring(tmp_path):
    ev = AbsorptionEvidence(
        schema_version=1,
        lot_id="BT-001",
        query="rare crock",
        marketplace="EBAY-US",
        window_start="2025-08-22",
        window_end="2026-08-22",
        displayed_window="Aug 22, 2025 – Aug 22, 2026",
        sold_units_last_365_days=0,
        sold_rows=0,
        active_listings_now=12,
        sold_pages_complete=True,
        sold_page_count=1,
        captured_at="2026-08-22T00:00:00Z",
        reviewer="owner",
        source_sha256={"capture": "abc"},
    )
    assert ev.absorption == 0.0
    assert ev.months_of_supply is None
    assert ev.as_dict()["months_of_supply"] is None

    # "incomplete" must NOT match "complete"
    base_capture = ROOT / "data/comps/2026-08-22/BT-235/capture.json"
    raw = json.loads(base_capture.read_text())
    raw["sold"]["pages_walked"] = "offset 0 only (incomplete)"
    cap_file = tmp_path / "capture.json"
    cap_file.write_text(json.dumps(raw))
    for name in ("sold_365d.png", "active.png", "sold_365d.tsv"):
        (tmp_path / name).write_bytes((base_capture.parent / name).read_bytes())
    with pytest.raises(ValueError, match="pagination"):
        import_capture(cap_file, reviewer="owner")


def test_h11_publication_facts_verifies_pipeline_state_hash_and_nonzero_passed(tmp_path):
    gallery = tmp_path / "manifest.json"
    gallery.write_text('{"photos": []}')
    state = tmp_path / "pipeline_state.json"
    state.write_text('{"tampered": true}')
    art = tmp_path / "artifact_manifest.json"
    import hashlib
    art.write_text(
        json.dumps({
            "schema_version": 2,
            "source_manifest_sha256": hashlib.sha256(gallery.read_bytes()).hexdigest(),
            "artifacts": {"pipeline_state.json": {"sha256": "0" * 64}},
        })
    )
    with pytest.raises(VideoBuildError, match="pipeline_state.json"):
        _publication_facts(
            {"sources": {"artifact_manifest": str(art)}},
            {"gallery_manifest": gallery, "pipeline_state": state},
        )

    all_skipped = tmp_path / "skipped.xml"
    all_skipped.write_text('<testsuite tests="5" failures="0" errors="0" skipped="5"/>')
    with pytest.raises(VideoBuildError, match="zero-passed"):
        _test_counts(all_skipped)
