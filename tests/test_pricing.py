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
