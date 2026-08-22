"""Container lots bid on confirmed evidence, never attractive speculation."""

from src.appraiser.containers import price_container_evidence
from scripts.run_vertex_pipeline import comp_from_reference


BULK = {
    "low": 20,
    "high": 35,
    "source_count": 3,
    "citations": ["https://example.test/sold/bulk"],
}
ALPHA = {
    "low": 100,
    "high": 140,
    "source_count": 2,
    "citations": ["https://example.test/sold/alpha"],
}


def decomposition(*, marks=(), questions=()):
    return {
        "contents": [{
            "item_name": "possible signed sterling bracelet",
            "market_role": "alpha",
            "marks_observed": list(marks),
        }],
        "questions": list(questions),
    }


def test_confirmed_alpha_adds_its_comp_to_the_bulk_floor():
    result = price_container_evidence(
        decomposition=decomposition(marks=("STERLING maker stamp",)),
        alpha_comp=ALPHA,
        bulk_floor=BULK,
    )
    assert result.alpha_confirmed
    assert (result.low, result.high) == (120, 175)
    assert len(result.citations) == 2


def test_unreadable_hallmark_prices_bulk_and_names_alpha_only_as_upside():
    result = price_container_evidence(
        decomposition=decomposition(
            marks=(), questions=("Is there a maker hallmark on the clasp?",)),
        alpha_comp=ALPHA,
        bulk_floor=BULK,
    )
    assert not result.alpha_confirmed
    assert (result.low, result.high) == (20, 35)
    assert "Unconfirmed alpha upside" in result.upside_note
    assert "alpha" not in " ".join(result.citations)


def test_bulk_floor_itself_must_be_cited():
    try:
        price_container_evidence(
            decomposition=decomposition(), alpha_comp=ALPHA,
            bulk_floor={"low": 20, "high": 35, "source_count": 3},
        )
    except ValueError as exc:
        assert "cited sold evidence" in str(exc)
    else:
        raise AssertionError("uncited bulk floor must be refused")


def test_pipeline_reference_seam_uses_bulk_only_for_unconfirmed_alpha():
    comp, record, note = comp_from_reference(
        {
            "cat": "jewelry",
            "desc": "tray",
            "container_evidence": {"bulk_floor": BULK, "alpha_comp": ALPHA},
        },
        {"container_decomposition": decomposition(
            questions=("Is there a maker hallmark on the clasp?",),
        )},
    )
    assert (comp.low, comp.high, comp.source_count) == (20, 35, 3)
    assert record["provenance"] == "container_bulk_floor"
    assert "Unconfirmed alpha upside" in note


def test_pipeline_reference_seam_adds_only_a_confirmed_alpha():
    comp, record, note = comp_from_reference(
        {
            "cat": "jewelry",
            "desc": "tray",
            "container_evidence": {"bulk_floor": BULK, "alpha_comp": ALPHA},
        },
        {"container_decomposition": decomposition(marks=("STERLING",))},
    )
    assert (comp.low, comp.high, comp.source_count) == (120, 175, 5)
    assert record["provenance"] == "container_alpha_plus_bulk"
    assert note is None
