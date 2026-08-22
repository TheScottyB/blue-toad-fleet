"""Container lots are spatially isolated, itemized, and still bid once."""

import json
from io import BytesIO

from PIL import Image

from scripts.run_vertex_pipeline import select_decomposition_candidates
from src.appraiser import AppraisalEngine
from src.appraiser.containers import (
    NormalizedBox, append_visible_contents, crop_to_container, visible_contents,
)
from src.appraiser.prompts import build_appraisal_prompt
from src.appraiser.schema import (
    CONTAINER_DECOMPOSITION_SCHEMA, CONTAINER_LOCATION_SCHEMA, TRIAGE_SCHEMA,
)
from src.assemble import AppraisedPhoto, assemble_lots
from tests.test_images import jpeg_of


def decomposition(**overrides):
    payload = {
        "lot_id": "BT-041",
        "is_container_lot": True,
        "container_type": "tub",
        "boundary": {"x_min": 100, "y_min": 100, "x_max": 900, "y_max": 900},
        "contents": [
            {
                "item_name": "Edison Blue Amberol cylinders",
                "quantity": 11,
                "maker_or_series": "Edison Blue Amberol",
                "period": "early 20th century",
                "marks_observed": ["EDISON BLUE AMBEROL RECORD"],
                "market_role": "alpha",
                "confidence": "high",
                "condition_notes": [],
            },
            {
                "item_name": "unidentified plastic pieces",
                "quantity": 5,
                "maker_or_series": None,
                "period": None,
                "marks_observed": [],
                "market_role": "filler",
                "confidence": "low",
                "condition_notes": [],
            },
        ],
        "background_exclusions": [
            {"item_name": "clock", "reason": "outside the tub rim"},
        ],
        "hidden_extent": "minor",
        "questions": [],
    }
    payload.update(overrides)
    return payload


class TestBoundariesAndCropping:
    def test_normalized_boundary_becomes_the_expected_pixel_crop(self):
        box = NormalizedBox(250, 250, 750, 750)
        assert box.pixel_box(400, 200, padding=0) == (100, 50, 300, 150)

    def test_crop_really_removes_pixels_outside_the_boundary(self):
        source = Image.new("RGB", (400, 400), "red")
        source.paste(Image.new("RGB", (200, 200), "blue"), (100, 100))
        raw = BytesIO()
        source.save(raw, format="JPEG", quality=100)

        cropped = crop_to_container(
            raw.getvalue(), NormalizedBox(250, 250, 750, 750), padding=0)
        with Image.open(BytesIO(cropped)) as image:
            assert image.size == (200, 200)
            r, g, b = image.getpixel((100, 100))
            assert b > 240 and r < 15 and g < 15

    def test_invalid_or_inverted_model_boundaries_are_rejected(self):
        assert NormalizedBox.from_mapping(
            {"x_min": 900, "y_min": 10, "x_max": 100, "y_max": 800}) is None
        assert NormalizedBox.from_mapping(
            {"x_min": -1, "y_min": 10, "x_max": 100, "y_max": 800}) is None


class TestSchemaContract:
    def test_triage_explicitly_routes_bounded_lots(self):
        assert "needs_decomposition" in TRIAGE_SCHEMA["properties"]
        assert "needs_decomposition" in TRIAGE_SCHEMA["required"]

    def test_every_container_schema_property_is_required(self):
        for schema in (CONTAINER_LOCATION_SCHEMA, CONTAINER_DECOMPOSITION_SCHEMA):
            assert set(schema["properties"]) == set(schema["required"])

    def test_contents_separate_alpha_supporting_and_filler(self):
        role = (CONTAINER_DECOMPOSITION_SCHEMA["properties"]["contents"]
                ["items"]["properties"]["market_role"])
        assert set(role["enum"]) == {"alpha", "supporting", "filler"}

    def test_decomposition_has_no_price_field(self):
        banned = {"price", "value", "estimate", "worth", "margin", "comp"}

        def property_names(node):
            if not isinstance(node, dict):
                return set()
            names = set(node.get("properties", {}))
            for value in node.values():
                if isinstance(value, dict):
                    names |= property_names(value)
                elif isinstance(value, list):
                    for child in value:
                        names |= property_names(child)
            return names

        assert not (banned & property_names(CONTAINER_DECOMPOSITION_SCHEMA))


class TestDescriptionBoundary:
    def test_only_alpha_and_supporting_items_reach_the_clerk_line(self):
        assert visible_contents(decomposition()) == ("11× Edison Blue Amberol cylinders",)
        line = append_visible_contents("Edison record tub", decomposition())
        assert "11× Edison" in line
        assert "plastic pieces" not in line
        assert "clock" not in line

    def test_appraisal_prompt_names_contents_and_explicit_exclusions(self):
        prompt = build_appraisal_prompt(
            "Edison rolls", container_decomposition=decomposition())
        assert "11× Edison Blue Amberol cylinders" in prompt
        assert "Explicitly excluded background: clock" in prompt

    def test_contents_enrich_one_lot_instead_of_creating_sub_lots(self):
        lots = assemble_lots([
            AppraisedPhoto(
                photo_id="p1", caption="Lot 41 Edison tub",
                identification="Edison cylinder record lot",
                contents=visible_contents(decomposition()),
            )
        ])
        assert len(lots) == 1
        assert "11× Edison" in lots[0].caption

    def test_contents_do_not_leak_across_physical_lots(self):
        lots = assemble_lots([
            AppraisedPhoto(photo_id="p1", caption="first tub", contents=("rare cards",)),
            AppraisedPhoto(photo_id="p2", caption="second tub", contents=("toy cars",)),
        ])
        assert len(lots) == 2
        assert "rare cards" in lots[0].caption and "toy cars" not in lots[0].caption
        assert "toy cars" in lots[1].caption and "rare cards" not in lots[1].caption


class _Response:
    def __init__(self, payload):
        self.text = json.dumps(payload)


class _Models:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return _Response(next(self.payloads))


class _Client:
    def __init__(self, payloads):
        self.models = _Models(payloads)


class TestTwoPassEngine:
    def test_locator_then_itemizer_are_two_distinct_model_calls(self):
        location = {
            "is_container_lot": True,
            "container_type": "tray",
            "boundary": {"x_min": 200, "y_min": 100, "x_max": 800, "y_max": 900},
            "confidence": "high",
            "reason": "visible tray rim",
        }
        items = {k: v for k, v in decomposition(container_type="tray").items()
                 if k in CONTAINER_DECOMPOSITION_SCHEMA["properties"]}
        engine = AppraisalEngine()
        engine._client = _Client([location, items])

        result = engine.decompose_container(
            "BT-002", "jewelry trays", jpeg_of(560, 420))

        assert len(engine.client.models.calls) == 2
        assert result["boundary"] == location["boundary"]
        assert result["contents"][0]["market_role"] == "alpha"
        assert result["boundary_model_used"] == engine.appraisal_model

    def test_a_non_container_stops_before_the_itemizer(self):
        location = {
            "is_container_lot": False,
            "container_type": "none",
            "boundary": None,
            "confidence": "high",
            "reason": "one freestanding object",
        }
        engine = AppraisalEngine()
        engine._client = _Client([location])

        result = engine.decompose_container("BT-009", "crock", jpeg_of(560, 420))

        assert len(engine.client.models.calls) == 1
        assert result["is_container_lot"] is False
        assert result["contents"] == []

    def test_a_spatial_graph_boundary_skips_the_locator_call(self):
        items = {k: v for k, v in decomposition().items()
                 if k in CONTAINER_DECOMPOSITION_SCHEMA["properties"]}
        engine = AppraisalEngine()
        engine._client = _Client([items])

        result = engine.decompose_container(
            "BT-041", "Edison rolls", jpeg_of(560, 420),
            spatial_boundary={"x_min": 50, "y_min": 100, "x_max": 950, "y_max": 900},
            spatial_context="center-island tub 7", container_type="tub",
        )

        assert len(engine.client.models.calls) == 1
        assert result["boundary_model_used"] == "spatial-room-graph"


class TestPipelineSelection:
    def test_only_explicitly_flagged_appraisal_candidates_are_selected(self):
        photos = [
            {"photo_id": "p1", "sequence": 1, "caption": "box", "local_path": "one.jpg"},
            {"photo_id": "p2", "sequence": 2, "caption": "crock", "local_path": "two.jpg"},
            {"photo_id": "p3", "sequence": 3, "caption": "tray", "local_path": "three.jpg"},
        ]
        triage = [
            {"photo_id": "p1", "needs_decomposition": True},
            {"photo_id": "p2", "needs_decomposition": False},
            {"photo_id": "p3", "needs_decomposition": True},
        ]
        selected = select_decomposition_candidates(
            triage, photos, appraised_lot_ids={"BT-001", "BT-002"})
        assert [row["lot_id"] for row in selected] == ["BT-001"]

