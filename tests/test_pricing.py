"""
Grounded pricing.

Everything upstream refuses to name a price. That was the right call while there
was nothing to ground one in — a dollar figure from a photograph is a guess
wearing a number. Search grounding changes what is possible, not the standard:
a price still has to come from sold comparables somebody can go and look at.

Two failure modes have money on them and neither is hypothetical. Asked the same
lot twice, the model returned $40-$60 and $40-$147.50. And asked to report its
sources in a schema field, it wrote bare domains — "https://www.bssauction.com"
— which cite nothing. So: three independent calls and take the median, and
citations come from grounding_metadata, which the model does not author.
"""

from threading import Event

import pytest

from src.appraiser.pricing import (
    GroundedPrice, median_price, price_is_usable, MIN_SOLD_COMPS, MAX_SPREAD_RATIO,
)


def gp(low, high, comps=3, sources=("https://www.ebay.com/itm/1234",)):
    return GroundedPrice(low=low, high=high, sold_comp_count=comps, sources=list(sources))


class TestMedianOfThree:
    def test_the_median_is_taken_on_each_bound(self):
        m = median_price([gp(40, 60), gp(40, 147.5), gp(50, 90)])
        assert (m.low, m.high) == (40.0, 90.0)

    def test_one_wild_result_cannot_drag_the_answer(self):
        """The $147.50 outlier I actually got must not set the bid."""
        m = median_price([gp(40, 60), gp(45, 65), gp(40, 147.5)])
        assert m.high == 65.0

    def test_the_comp_count_is_the_median_too(self):
        m = median_price([gp(40, 60, comps=1), gp(40, 60, comps=6), gp(40, 60, comps=3)])
        assert m.sold_comp_count == 3

    def test_sources_from_every_call_are_unioned(self):
        """Each call may find different sales; all of them are evidence."""
        A = "https://www.ebay.com/itm/1"
        B = "https://www.invaluable.com/lot/2"
        C = "https://bssauction.com/past/3"
        m = median_price([gp(40, 60, sources=(A,)), gp(41, 61, sources=(B,)),
                          gp(42, 62, sources=(A, C))])
        assert sorted(m.sources) == sorted([A, B, C])

    def test_uncitable_sources_are_not_carried_forward(self):
        m = median_price([gp(40, 60, sources=("https://www.bssauction.com",))
                          for _ in range(3)])
        assert m.sources == []

    def test_no_results_is_not_a_price(self):
        assert median_price([]) is None


class TestWhenAPriceMayBeBidOn:
    def test_a_tight_agreeing_price_is_usable(self):
        assert price_is_usable([gp(40, 60), gp(45, 65), gp(42, 62)])

    def test_calls_that_disagree_wildly_are_refused(self):
        """$60 and $147.50 on the same lot means nobody knows what it is worth."""
        assert not price_is_usable([gp(40, 60), gp(40, 147.5), gp(40, 61)])

    def test_too_few_sold_comps_is_refused(self):
        thin = [gp(40, 60, comps=MIN_SOLD_COMPS - 1) for _ in range(3)]
        assert not price_is_usable(thin)

    def test_a_price_with_no_citation_is_refused(self):
        """An uncited price is the model's opinion, which is what we do not bid on."""
        assert not price_is_usable([gp(40, 60, sources=()) for _ in range(3)])

    def test_fewer_than_three_calls_is_refused(self):
        assert not price_is_usable([gp(40, 60), gp(41, 61)])

    def test_a_zero_or_negative_price_is_refused(self):
        assert not price_is_usable([gp(0, 0) for _ in range(3)])

    def test_low_above_high_is_refused(self):
        assert not price_is_usable([gp(90, 40) for _ in range(3)])


class TestGroundedBatchBecomesSheetEvidence:
    def test_unpriced_workflow_states_distinguish_waiting_retry_and_inconclusive(self):
        from src.appraiser.grounded_batch import grounded_status_reason

        assert grounded_status_reason(None).startswith("pending deep comps")
        assert grounded_status_reason({"attempt_complete": False}).startswith(
            "deep comps retry pending"
        )
        assert grounded_status_reason({"attempt_complete": True}).startswith(
            "needs deeper comps"
        )

    def test_pricing_starts_before_every_appraisal_finishes(self, tmp_path):
        from src.appraiser import AppraisalEngine
        from src.appraiser.grounded_batch import GroundedPricingPipeline

        pricing_started = Event()
        engine = AppraisalEngine()
        engine._client = object()

        def appraise(lot_id, **kwargs):
            if lot_id == "BT-002":
                assert pricing_started.wait(timeout=2), (
                    "grounded pricing waited for the whole appraisal batch"
                )
            return {
                "lot_id": lot_id,
                "identification": f"identified {lot_id}",
                "category": "advertising",
                "fit_score": 0.85,
            }

        class PricingEngine:
            def price_lot_grounded(self, _identification, _category):
                pricing_started.set()
                return gp(40, 60, comps=4)

        engine.appraise_lot = appraise
        pricing = GroundedPricingPipeline(
            tmp_path / "prices.json", workers=1, engine_factory=PricingEngine,
        )
        try:
            appraisals, _ = engine.run_enrichment_appraisal_pipeline(
                [
                    {"lot_id": "BT-001", "caption": "first"},
                    {"lot_id": "BT-002", "caption": "second"},
                ],
                force_refresh=True,
                appraisal_workers=2,
                appraisal_result_callback=pricing.submit,
            )
            prices = pricing.finish()
        except Exception:
            pricing.shutdown()
            raise

        assert [row["lot_id"] for row in appraisals] == ["BT-001", "BT-002"]
        assert [row["lot_id"] for row in prices] == ["BT-001", "BT-002"]

    def test_only_complete_usable_rows_cross_the_comp_seam(self, tmp_path):
        from src.appraiser.grounded_batch import (
            grounded_reference_comps, run_grounded_pricing_batch,
        )

        class Engine:
            def price_lot_grounded(self, _identification, _category):
                return gp(40, 60, comps=4)

        appraisals = [
            {"lot_id": "BT-001", "identification": "old sign",
             "category": "advertising", "fit_score": 0.85},
            {"lot_id": "BT-002", "identification": "filler",
             "category": "other", "fit_score": 0.30},
        ]
        rows = run_grounded_pricing_batch(
            appraisals, tmp_path / "prices.json", workers=1,
            engine_factory=Engine,
        )
        assert [row["lot_id"] for row in rows] == ["BT-001"]
        assert rows[0]["attempt_complete"] and rows[0]["usable"]
        refs = grounded_reference_comps(rows)
        assert refs["BT-001"]["provenance"] == "grounded_search"
        assert refs["BT-001"]["citations"] == ["https://www.ebay.com/itm/1234"]

    def test_grounded_comp_reaches_bid_allocation_and_clerk_email(self):
        from src.appraiser.grounded_batch import grounded_reference_comps
        from src.assemble.email import compile_absentee_email
        from src.bidmath import CompEstimate, Confidence, Lot, allocate, price_lot

        rows = [{
            "lot_id": "BT-001", "identification": "old advertising sign",
            "category": "advertising", "usable": True,
            "attempt_complete": True, "errors": [],
            "low": 80, "high": 120, "sold_comp_count": 4,
            "sources": ["https://www.ebay.com/itm/1234"],
        }]
        record = grounded_reference_comps(rows)["BT-001"]
        lot = Lot(
            lot_id="BT-001", caption=record["desc"], category=record["cat"],
            fit_score=0.90, condition_penalty=0.0,
            comp=CompEstimate(
                record["low"], record["high"], record["sources"],
                Confidence.MEDIUM,
            ),
        )
        decisions = allocate([price_lot(lot)], budget_cap=600,
                             auto_send_threshold=0)
        assert decisions[0].allocated and decisions[0].max_bid == 30.0
        email = compile_absentee_email(
            to="auction@example.com", subject="test", auction_date="test date",
            venue="test venue", lots=[lot], decisions=decisions,
        )
        assert "[BT-001]" in email and "MAX $30.00" in email

    def test_transient_errors_are_not_reused_as_a_completed_refusal(self, tmp_path):
        import json
        from src.appraiser.grounded_batch import (
            attempt_history_path, run_grounded_pricing_batch,
        )

        class Broken:
            def price_lot_grounded(self, _identification, _category):
                raise RuntimeError("quota")

        calls = {"count": 0}

        class Recovered:
            def price_lot_grounded(self, _identification, _category):
                calls["count"] += 1
                return gp(40, 60)

        lot = {"lot_id": "BT-001", "identification": "old sign",
               "category": "advertising", "fit_score": 0.85}
        cache = tmp_path / "prices.json"
        first = run_grounded_pricing_batch(
            [lot], cache, workers=1, engine_factory=Broken)
        assert not first[0]["attempt_complete"] and not first[0]["usable"]
        second = run_grounded_pricing_batch(
            [lot], cache, workers=1, engine_factory=Recovered)
        assert second[0]["attempt_complete"] and second[0]["usable"]
        assert calls["count"] == 3
        history = json.loads(attempt_history_path(cache).read_text())
        assert len(history) == 2
        assert history[0]["errors"] and history[0]["attempt_complete"] is False
        assert history[1]["errors"] == [] and history[1]["attempt_complete"] is True
        assert history[0]["attempt_id"] != history[1]["attempt_id"]
        assert all(row["method"] == "vertex_google_search_grounding" for row in history)


class TestCitations:
    def test_a_bare_domain_is_not_a_citation(self):
        """This is verbatim what the model wrote when asked to self-report sources."""
        from src.appraiser.pricing import usable_sources
        assert usable_sources(["https://www.bssauction.com", "https://www.ebay.com"]) == []

    def test_a_url_with_a_path_is_a_citation(self):
        from src.appraiser.pricing import usable_sources
        assert usable_sources(["https://www.ebay.com/itm/1234"]) == ["https://www.ebay.com/itm/1234"]

    def test_the_vertex_redirect_form_is_accepted(self):
        from src.appraiser.pricing import usable_sources
        u = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG5b2u3"
        assert usable_sources([u]) == [u]

    def test_junk_is_dropped(self):
        from src.appraiser.pricing import usable_sources
        assert usable_sources(["", None, "not a url"]) == []


class TestReadingAGroundedResponse:
    """
    Citations come from grounding_metadata, not from a field the model fills in.
    Asked to self-report sources it wrote "https://www.bssauction.com" — true,
    uncheckable, and indistinguishable from evidence at a glance.
    """

    def test_sources_are_read_from_the_grounding_metadata(self):
        from src.appraiser.pricing import sources_from_response

        class Web:
            uri = "https://www.ebay.com/itm/99"
        class Chunk:
            web = Web()
        class GM:
            grounding_chunks = [Chunk()]
        class Cand:
            grounding_metadata = GM()
        class Resp:
            candidates = [Cand()]

        assert sources_from_response(Resp()) == ["https://www.ebay.com/itm/99"]

    def test_a_response_with_no_grounding_yields_no_sources(self):
        from src.appraiser.pricing import sources_from_response

        class Cand:
            grounding_metadata = None
        class Resp:
            candidates = [Cand()]

        assert sources_from_response(Resp()) == []

    def test_a_malformed_response_does_not_explode(self):
        from src.appraiser.pricing import sources_from_response
        assert sources_from_response(None) == []
        assert sources_from_response(object()) == []

    def test_the_models_own_source_field_is_ignored_entirely(self):
        """Even if the payload claims sources, only grounding_metadata counts."""
        from src.appraiser.pricing import parse_price_payload
        p = parse_price_payload(
            {"low": 40, "high": 60, "sold_comp_count": 3,
             "sources": ["https://www.bssauction.com"]},
            grounded_sources=["https://www.invaluable.com/lot/7"])
        assert p.sources == ["https://www.invaluable.com/lot/7"]

    def test_a_payload_missing_fields_is_not_a_price(self):
        from src.appraiser.pricing import parse_price_payload
        assert parse_price_payload({}, grounded_sources=[]) is None
        assert parse_price_payload({"low": 40}, grounded_sources=[]) is None
