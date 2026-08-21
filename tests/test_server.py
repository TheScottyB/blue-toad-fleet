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

    r2 = client.get("/healthz")
    assert r2.status_code == 200
    assert r2.json()["status"] == "healthy"

def test_root_console_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Blue Toad Fleet" in r.text
    assert "Pole Barn Showroom Topology" in r.text
    assert "Curator's Negotiation" in r.text

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

def test_api_questions(client):
    r = client.get("/api/questions")
    assert r.status_code == 200
    data = r.json()
    assert "asked" in data
    assert "auto_answered_from_memory" in data
    assert len(data["auto_answered_from_memory"]) >= 3

def test_api_answer_promotion(client):
    payload = {
        "kind": "mark",
        "category": "stoneware",
        "answer": "Only bid if wing mark is clearly visible"
    }
    r = client.post("/api/answer", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "learned"
    assert data["rule"]["category"] == "stoneware"

def test_api_answer_invalid(client):
    r = client.post("/api/answer", json={"kind": "invalid_kind"})
    assert r.status_code in (400, 422)

def test_api_email_draft(client):
    r = client.get("/api/email")
    assert r.status_code == 200
    text = r.text
    assert "info@bluetoadauctions.com" in text
    assert "$335.00" in text or "Richmond General" in text


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

    def test_a_negotiated_cap_is_a_ceiling_never_a_floor(self):
        """
        A cap limits a bid; it must not raise one. If the appraiser's condition
        reading lands under the agreed number, the lower figure is what goes on
        the sheet — an authorisation to spend $100 is not an instruction to.
        """
        from scripts.run_vertex_pipeline import OPERATOR_APPROVED
        allocated = self.allocated()
        for lot_id, rec in OPERATOR_APPROVED.items():
            cap = rec.get("cap")
            d = allocated.get(lot_id)
            if cap is None or d is None:
                continue
            assert d.max_bid <= cap, f"{lot_id} bids ${d.max_bid} over its ${cap} cap"

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
