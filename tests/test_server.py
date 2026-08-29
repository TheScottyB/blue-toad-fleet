"""
Unit tests for Blue Toad Fleet FastAPI server & endpoints.
"""

import pytest
from starlette.testclient import TestClient
from src.server import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health_endpoints(client):
    r1 = client.get("/health")
    assert r1.status_code == 200
    assert r1.json()["status"] == "healthy"
    assert r1.json()["service"] == "blue-toad-fleet"
    assert r1.json()["memory_backend"] in {"memory", "file", "firestore"}
    assert r1.json()["python"].startswith("3.14")

    r2 = client.get("/healthz")
    assert r2.status_code == 200
    assert r2.json()["status"] == "healthy"


def test_health_names_the_gemma_bonus_model(client):
    data = client.get("/health").json()
    assert "gemma" in data["gemma_model"].lower()
    assert not data["gemma_model"].startswith("gemini-")
    assert "gemma_ok" in data


def test_health_reports_the_stamped_git_commit(client, monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "abc123def456")
    assert client.get("/health").json()["git_commit"] == "abc123def456"


def test_health_git_commit_is_unknown_when_unstamped(client, monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    assert client.get("/health").json()["git_commit"] == "unknown"

def test_root_console_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Blue Toad Fleet" in r.text
    assert "Walk-order grouping" in r.text
    assert "spatial observations unavailable" in r.text
    assert "Curator" in r.text and "template fallback" in r.text

def test_console_voice_cache_path_is_env_controlled(client, tmp_path, monkeypatch):
    """A live run caches its Gemma voice, and a matching-key cache entry wins
    over the credential-free fallback by design. When that cache lived at a
    hard-coded /tmp path shared with pytest, a live uvicorn run made the next
    test run render the live voice instead of the template fallback (2026-08-29).
    BTF_VOICE_CACHE must decide where the console looks, so tests own the path.
    """
    import json

    from src.gate.voice import _payload
    from src.server import build_pitch, current_rules, get_aug22_state

    _, _, _, decisions, _, _, captions_map = get_aug22_state()
    pitch = build_pitch(decisions, captions_map, current_rules())
    cache = tmp_path / "voice.json"
    cache.write_text(json.dumps({
        "key": json.dumps(_payload(pitch), sort_keys=True),
        "voice": {
            "alpha": "SENTINEL-CACHED-VOICE for the alpha tier.",
            "fast_smalls": "SENTINEL-CACHED-VOICE for the fast smalls.",
            "wildcard": "SENTINEL-CACHED-VOICE for the wildcard.",
            "pushback": None,
        },
    }))
    monkeypatch.setenv("BTF_VOICE_CACHE", str(cache))

    html = client.get("/").text
    assert "SENTINEL-CACHED-VOICE" in html
    assert "template fallback" not in html


def test_api_lots_summary_and_bids(client):
    r = client.get("/api/lots")
    assert r.status_code == 200
    data = r.json()
    summary = data["summary"]
    # Pin the invariants, not the figure. The total moves whenever an appraisal
    # is re-run or the owner changes his mind, and a magic constant here just
    # turns a legitimate change into a red test that gets edited to match.
    assert summary["allocated"] > 0
    assert summary["committed_max"] > 0
    assert abs(summary["committed_all_in"] - summary["committed_max"] * 1.15) < 0.01
    assert summary["committed_all_in"] <= 600.0, "sheet exceeds the budget envelope"
    assert summary["committed_max"] % 5 == 0, "total is not a sum of $5 increments"
    assert len(data["lots"]) > 0
    assert "contingent_remainder_opportunities" in data
    assert all(lot["labor"] in {"shelf", "list", "research"} for lot in data["lots"])
    assert all("coverage_gap" in lot for lot in data["lots"])
    allowed = {"", "not_searched", "spread", "no_sold_comps", "asking_only"}
    assert all(lot["coverage_gap"] in allowed for lot in data["lots"])
    by_id = {lot["lot_id"]: lot for lot in data["lots"]}
    assert by_id["BT-006"]["max_bid"] is None
    assert by_id["BT-006"]["coverage_gap"] == "spread"
    assert any(lot["coverage_gap"] == "not_searched" for lot in data["lots"])


def test_scoped_choice_ruling_uses_election_and_exposes_remainder():
    from src.appraisal import LotRuling, QuestionKind
    from src.bidmath import (
        BidMechanic, CompEstimate, Confidence, Lot, price_lot,
        remainder_opportunity,
    )
    from src.server import apply_lot_rulings

    lot = Lot(
        lot_id="BT-500", caption="five shelves", category="advertising",
        fit_score=0.9, condition_penalty=0.0,
        comp=CompEstimate(250, 300, 3, Confidence.HIGH),
    )
    ruling = LotRuling(
        kind=QuestionKind.LOT_GROUPING,
        answer="buyer's choice of 5, take 2",
        learned_cycle="c1",
        lot_ids=("BT-500",),
    )
    applied = apply_lot_rulings(
        [lot], rulings=[ruling], operator_approved={})[0]
    assert (applied.mechanic, applied.unit_count, applied.units_wanted) == (
        BidMechanic.CHOICE, 5, 2)
    assert remainder_opportunity(price_lot(applied)) is not None


def test_coverage_gap_for_classifies_empty_dollar_reasons():
    from src.bidmath import CoverageGap
    from src.server import coverage_gap_for

    assert coverage_gap_for("BT-missing", {}) is CoverageGap.NOT_SEARCHED
    spread = {"usable": False, "samples": [
        {"low": 10.0, "high": 20.0, "comps": 5},
        {"low": 10.0, "high": 40.0, "comps": 5},
        {"low": 12.0, "high": 50.0, "comps": 5},
    ]}
    assert coverage_gap_for("BT-x", {"BT-x": spread}) is CoverageGap.SPREAD
    thin = {"usable": False, "sold_comp_count": 0, "samples": [
        {"low": 0.0, "high": 0.0, "comps": 0},
        {"low": 0.0, "high": 0.0, "comps": 0},
        {"low": 0.0, "high": 0.0, "comps": 0},
    ]}
    assert coverage_gap_for("BT-y", {"BT-y": thin}) is CoverageGap.NO_SOLD_COMPS


def test_api_questions(client):
    r = client.get("/api/questions")
    assert r.status_code == 200
    data = r.json()
    assert "asked" in data
    assert "auto_answered_from_memory" in data
    assert len(data["auto_answered_from_memory"]) >= 3

def test_api_answer_promotion(client):
    from src.server import reset_rule_store
    reset_rule_store()


def test_lot_grouping_answer_is_scoped_and_changes_money(client):
    from src.server import reset_rule_store

    reset_rule_store()
    asked = client.get("/api/questions").json()["asked"]
    target = next(
        question for question in asked
        if question["kind"] == "lot_grouping" and "BT-002" in question["lot_ids"]
    )
    response = client.post("/api/answer", json={
        "question_id": target["question_id"],
        "answer": "sell all trays together as one single lot",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["authority_type"] == "lot_ruling"
    assert data["rule"]["lot_ids"] == ["BT-002"]
    assert data["before"]["decisions"]["BT-002"]["mechanic"] == "times_the_money"
    assert data["after"]["decisions"]["BT-002"]["mechanic"] == "straight"
    assert data["after"]["decisions"]["BT-002"]["committed_max"] < (
        data["before"]["decisions"]["BT-002"]["committed_max"])
    assert data["money_changed"] is True
    assert data["pending_reappraisal"] is False

    memory = client.get("/api/memory").json()
    assert len(memory["lot_rulings"]) == 1
    assert memory["lot_rulings"][0]["lot_ids"] == ["BT-002"]
    email = client.get("/api/email").text
    bt002_block = email.split("[BT-002]", 1)[1].split("\n\n", 1)[0]
    assert "one lot, one bid" in bt002_block
    assert "PER UNIT" not in bt002_block
    reset_rule_store()
    asked = client.get("/api/questions").json()["asked"]
    assert asked, "desk queue empty; nothing to answer"
    target = asked[0]
    r = client.post("/api/answer", json={
        "question_id": target["question_id"],
        "answer": "BUY — advertising glass moves in the storefront",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "applied"
    assert data["promoted"] is True
    assert data["rule"]["category"] == target["category"]
    mem = client.get("/api/memory").json()
    assert mem["backend"] == "memory"
    assert any(x["category"] == target["category"] for x in mem["rules"])
    later = client.get("/api/questions").json()
    assert all(q["question_id"] != target["question_id"] for q in later["asked"])
    assert any(
        a["question_id"] == target["question_id"]
        for a in later["auto_answered_from_memory"]
    )
    reset_rule_store()


def test_api_answer_rejects_unasked_question(client):
    from src.server import reset_rule_store
    reset_rule_store()
    r = client.post("/api/answer", json={
        "question_id": "q_does_not_exist",
        "answer": "BUY",
    })
    assert r.status_code == 404


def test_stale_answer_revision_conflicts_without_mutating_state(client):
    from src.server import reset_rule_store

    reset_rule_store()
    target = next(
        question for question in client.get("/api/questions").json()["asked"]
        if question["kind"] in {"policy", "appetite", "lot_grouping", "scope"}
    )
    payload = {
        "question_id": target["question_id"],
        "answer": "BUY",
        "expected_revision": target["expected_revision"],
    }
    first = client.post("/api/answer", json=payload)
    assert first.status_code == 200
    before = client.get("/api/memory").json()
    second = client.post("/api/answer", json=payload)
    assert second.status_code == 409
    assert client.get("/api/memory").json() == before
    reset_rule_store()


def test_api_answer_does_not_promote_via_raw_kind(client):
    r = client.post("/api/answer", json={
        "kind": "mark",
        "category": "stoneware",
        "answer": "Only bid if wing mark is clearly visible",
    })
    assert r.status_code == 400


def test_api_answer_invalid(client):
    r = client.post("/api/answer", json={"kind": "invalid_kind"})
    assert r.status_code in (400, 422)


def test_cloud_operator_actions_fail_closed_and_require_the_token(client, monkeypatch):
    from src.server import reset_rule_store

    reset_rule_store()
    target = client.get("/api/questions").json()["asked"][0]
    payload = {"question_id": target["question_id"], "answer": "BUY"}
    monkeypatch.setenv("K_SERVICE", "blue-toad-fleet")
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    assert client.post("/api/answer", json=payload).status_code == 503

    monkeypatch.setenv("OPERATOR_TOKEN", "test-operator-token")
    assert client.post("/api/answer", json=payload).status_code == 401
    response = client.post(
        "/api/answer", json=payload,
        headers={"X-Operator-Token": "test-operator-token"},
    )
    assert response.status_code == 200
    reset_rule_store()

def test_api_email_draft(client):
    r = client.get("/api/email")
    assert r.status_code == 200
    text = r.text
    assert "info@bluetoadauctions.com" in text
    assert "$335.00" in text or "Richmond General" in text
    assert "ITEM DESCRIPTION" not in text


def test_corrupt_embed_cache_does_not_500_console(client, monkeypatch):
    def boom(*_a, **_k):
        raise ValueError("mixed-length vectors")
    monkeypatch.setattr("src.server.load_reshoot_edges", boom)
    r = client.get("/")
    assert r.status_code == 200
    assert "Blue Toad Fleet" in r.text


def test_merged_declined_181_does_not_skip_bt002():
    """High-confidence BT-181 with operator fit=None must not SKIP BT-002."""
    from src.assemble import AppraisedPhoto, assemble_lots
    from src.bidmath import CompEstimate, Confidence, Priority, price_lot
    from scripts.run_vertex_pipeline import apply_operator_fit

    jewelry = CompEstimate(65, 75, 3, Confidence.HIGH)
    lots = assemble_lots(
        [
            AppraisedPhoto(
                photo_id="BT-002", caption="Estate Costume Jewelry",
                identification="trays", category="jewelry",
                fit_score=0.85, confidence=Confidence.MEDIUM,
            ),
            AppraisedPhoto(
                photo_id="BT-181", caption="estate costume jewelry",
                identification="close-up", category="jewelry",
                fit_score=0.0, confidence=Confidence.HIGH,
            ),
        ],
        comps={"seq:BT-002": jewelry, "BT-002": jewelry},
        reshoot_edges={frozenset({"BT-002", "BT-181"})},
    )
    lot = apply_operator_fit(lots[0])
    assert lot.lot_id == "BT-002"
    assert lot.fit_score != 0.0
    assert price_lot(lot).priority is not Priority.SKIP


def test_photo_from_raw_maps_container_fields_into_assemble():
    from src.assemble import assemble_lots
    from src.bidmath import Confidence
    from src.server import photo_from_raw

    photo = photo_from_raw(
        {
            "identification": "Edison crate",
            "is_container": True,
            "contents": ["Blue Amberol"],
        },
        photo_id="p1",
        caption="Lot 41 box",
        identification="Edison crate",
        category="phonograph / records",
        fit_score=0.9,
        confidence=Confidence.HIGH,
    )
    lots = assemble_lots([photo])
    assert "Blue Amberol" in lots[0].caption


def test_photo_from_raw_defaults_when_cache_omits_container_keys():
    from src.server import photo_from_raw

    photo = photo_from_raw(
        {"identification": "Red Wing crock"},
        photo_id="p1",
        caption="Lot 5",
        identification="Red Wing crock",
    )
    assert photo.is_container is False
    assert photo.contents == ()


class TestTheModelReachesTheQueue:
    """
    Nothing caught it when the Vertex questions were unhooked from build_queue —
    the console rendered three hand-written prompts, all of them absorbed by
    standing rules, and reported an empty queue as if the cycle were clean.
    A console that cannot show what the model asked is a console showing a demo.
    """

    def test_model_emitted_questions_reach_the_console_queue(self):
        from src.server import get_aug22_state

        _, _, _, _, _, queue, _ = get_aug22_state()
        surfaced = queue.asked + [q for q, _ in queue.auto_answered] + queue.dropped

        hand_written = {
            "sports memorabilia", "dinnerware / pottery", "vintage tools",
        }
        from_model = [q for q in surfaced if q.category not in hand_written]

        assert from_model, (
            "the queue contains only the hard-coded domain questions; "
            "nothing the appraiser emitted reached it"
        )

    def test_the_queue_is_not_empty_while_lots_carry_questions(self):
        import json
        from pathlib import Path
        from src.server import get_aug22_state

        cache = Path("data/aug22_gallery_4160518/appraisal_results.json")
        emitted = sum(len(lot.get("questions", []))
                      for lot in json.loads(cache.read_text()))
        assert emitted, "fixture has no questions; this test proves nothing"

        _, _, _, _, _, queue, _ = get_aug22_state()
        assert queue.asked, (
            f"the appraiser emitted {emitted} question(s) and the console asks none"
        )


class TestOperatorOverridesAreRecordedNotHidden:
    """
    The 12 sourcing lots carry decisions the owner made in the collaborative
    review — he buys bulk costume jewelry for the storefront whatever the
    category-fit score says, and he agreed a $100 cap on the Topps run.

    Those are answers, not appraisals. Writing them in as `fit = 0.90,
    penalty = 0.0, conf = HIGH` overwrites what the appraiser concluded, so the
    console reports HIGH confidence on lots the model called low and shows no
    trace of a human having decided anything.
    """

    def test_no_lot_departs_from_the_appraisal_without_a_recorded_reason(self):
        """
        Overriding the appraiser is fine — the owner knows things a category-fit
        score cannot. Doing it anonymously is not: every departure has to name
        who decided and why, or the sheet cannot be audited after the sale.
        """
        import json
        from pathlib import Path
        from src.server import get_aug22_state
        from scripts.run_vertex_pipeline import OPERATOR_APPROVED

        raw = {l["lot_id"]: l for l in json.loads(
            Path("data/aug22_gallery_4160518/appraisal_results.json").read_text())}
        _, _, lots, _, _, _, _ = get_aug22_state()

        silent = []
        for lot in lots:
            r = raw.get(lot.lot_id)
            if not r:
                continue
            if abs(lot.fit_score - float(r.get("fit_score", lot.fit_score))) < 1e-9:
                continue                        # matches the appraisal
            reason = OPERATOR_APPROVED.get(lot.lot_id, {}).get("why", "")
            if not reason:
                silent.append(lot.lot_id)
        assert not silent, f"fit overridden with no recorded reason: {silent}"

    def test_every_recorded_override_says_why(self):
        from scripts.run_vertex_pipeline import OPERATOR_APPROVED
        blank = [k for k, v in OPERATOR_APPROVED.items() if not v.get("why", "").strip()]
        assert not blank, f"override with an empty reason: {blank}"

    def test_an_answered_appetite_question_is_not_asked_again(self):
        """
        The owner answered these in the collab session. A queue that asks them
        anyway, while the sheet already bids on the category, is asking a
        question whose answer it has already spent money on.
        """
        from src.server import get_aug22_state

        _, _, _, _, _, queue, _ = get_aug22_state()
        bid_categories = {"jewelry", "vintage cards"}
        still_asked = [
            q.prompt for q in queue.asked
            if q.kind.value == "appetite" and q.category in bid_categories
        ]
        assert not still_asked, (
            "appetite already settled by an allocated bid, yet still queued: "
            + "; ".join(p[:70] for p in still_asked)
        )


class TestTheCollabDecisionsHold:
    """
    Decisions the owner gave in the collaborative chat, as assertions. He does
    not remember all of them, so what is recorded here is what is recoverable —
    anything else follows the appraiser, which is the honest default.
    """

    CARD_LOTS = {"BT-001", "BT-016", "BT-030"}
    JEWELLERY_LOTS = {"BT-002", "BT-087", "BT-181"}

    def allocated(self):
        from src.server import get_aug22_state
        _, _, _, decisions, _, _, _ = get_aug22_state()
        return {d.lot_id: d for d in decisions if d.allocated}

    def test_only_the_top_card_lot_is_bid(self):
        """"Give me the top 1 of the three card lots." Not all three."""
        bid = self.CARD_LOTS & self.allocated().keys()
        assert bid == {"BT-001"}, (
            f"bidding on {len(bid)} of 3 card lots ({sorted(bid)}); "
            "the owner asked for the top one only"
        )

    def test_no_jewellery_lot_exceeds_the_twenty_five_dollar_cap(self):
        """"Move max bid down to 25 on the vintage jewellery lots." A ceiling."""
        over = {lid: d.max_bid for lid, d in self.allocated().items()
                if lid in self.JEWELLERY_LOTS and (d.max_bid or 0) > 25.0}
        assert not over, f"over the agreed $25 cap: {over}"

    def test_the_owners_max_bid_is_the_one_that_ships(self):
        """
        Where he set a number it stands, in both directions. A defensive cap
        exists so the lot is not lost for five dollars; a condition penalty
        that walks it down produces exactly the loss it was meant to prevent.
        """
        from scripts.run_vertex_pipeline import OPERATOR_APPROVED
        allocated = self.allocated()
        for lot_id, rec in OPERATOR_APPROVED.items():
            cap, d = rec.get("cap"), allocated.get(lot_id)
            if cap is None or d is None:
                continue
            assert d.max_bid == cap, (
                f"{lot_id} bids ${d.max_bid}; the owner set ${cap}")

    def test_the_topps_run_ships_at_its_defensive_cap(self):
        d = self.allocated().get("BT-001")
        assert d is not None and d.max_bid == 100.0, (
            f"BT-001 at ${d.max_bid if d else None}; the agreed defensive cap was $100")

    def test_the_top_card_lot_is_still_on_the_sheet(self):
        assert "BT-001" in self.allocated(), "the lot the owner kept is missing"

    def test_every_declined_lot_records_the_instruction_that_declined_it(self):
        from scripts.run_vertex_pipeline import OPERATOR_APPROVED
        declined = {k: v for k, v in OPERATOR_APPROVED.items() if v.get("fit") is None}
        assert declined, "no lot is recorded as declined; the card-lot trim is missing"
        for lot_id, rec in declined.items():
            assert rec.get("why", "").strip(), f"{lot_id} declined with no reason"


class TestTheSheetAndTheEmailAgree:
    """
    The console and the pipeline built candidate lots independently, so an owner
    decision applied in one was invisible in the other — the console showed a
    trimmed 10-lot sheet while the email still carried 12. Whatever a judge or a
    clerk reads, it has to be the same sheet.
    """

    def test_both_paths_derive_lot_inputs_from_one_place(self):
        from scripts.run_vertex_pipeline import operator_lot_inputs
        # Declined lots come back with zero fit, whatever the appraiser scored.
        fit, _ = operator_lot_inputs("BT-016", {"fit_score": 0.9, "condition_penalty": 0.0})
        assert fit == 0.0

    def test_the_appraisers_condition_reading_is_carried_not_discarded(self):
        from scripts.run_vertex_pipeline import operator_lot_inputs
        _, penalty = operator_lot_inputs("BT-001", {"fit_score": 0.75, "condition_penalty": 0.35})
        assert penalty == 0.35

    def test_an_unknown_lot_falls_back_to_the_appraisal(self):
        from scripts.run_vertex_pipeline import operator_lot_inputs
        fit, penalty = operator_lot_inputs("BT-999", {"fit_score": 0.42, "condition_penalty": 0.2})
        assert (fit, penalty) == (0.42, 0.2)

    def test_the_compiled_email_matches_the_console_sheet(self):
        """The artifact a human receives must reconcile to what the console shows."""
        import re
        from pathlib import Path
        from src.server import get_aug22_state

        email_path = Path("data/aug22_absentee_bid_email.txt")
        if not email_path.exists():
            import pytest
            pytest.skip("no compiled email")

        _, _, _, decisions, summary, _, _ = get_aug22_state()
        console_lots = {d.lot_id for d in decisions if d.allocated}
        email_lots = set(re.findall(r"\bBT-\d{3}\b", email_path.read_text()))

        assert email_lots == console_lots, (
            f"email-only: {sorted(email_lots - console_lots)}; "
            f"console-only: {sorted(console_lots - email_lots)}"
        )
