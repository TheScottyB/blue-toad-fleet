import pytest
from src.appraisal import QuestionKind, StandingRule
from src.appraiser import (
    APPRAISAL_MODEL, APPRAISAL_SCHEMA, ModelTier, TRIAGE_MODEL, TRIAGE_SCHEMA,
    build_appraisal_prompt, build_triage_prompt, model_for,
)
from src.appraiser.routing import estimate_cost_usd
from src.appraiser.schema import CATEGORIES, CONFIDENCE, QUESTION_KINDS, to_vertex


class TestRouting:
    def test_models_meet_the_version_requirement(self):
        # Hackathon requires Gemini 3.5 or newer. Guard against a silent downgrade.
        for m in (TRIAGE_MODEL, APPRAISAL_MODEL):
            assert m.startswith("gemini-3."), m
            minor = float(m.split("-")[1])
            assert minor >= 3.5, f"{m} is below the required Gemini 3.5"

    def test_tiers_route_to_distinct_models(self):
        assert model_for(ModelTier.TRIAGE) != model_for(ModelTier.APPRAISAL)
        assert model_for(ModelTier.TRIAGE) == TRIAGE_MODEL

    def test_triage_is_the_cheaper_tier(self):
        c = estimate_cost_usd(photo_count=428, candidate_count=61)
        per_triage_photo = c["triage_usd"] / 428
        per_appraisal = c["appraisal_usd"] / 61
        assert per_triage_photo < per_appraisal

    def test_full_cycle_stays_under_two_dollars(self):
        c = estimate_cost_usd(photo_count=428, candidate_count=61)
        assert c["total_usd"] < 2.00, c

    def test_cost_scales_with_volume(self):
        small = estimate_cost_usd(50, 10)["total_usd"]
        big = estimate_cost_usd(500, 100)["total_usd"]
        assert big > small


class TestSchemas:
    def test_triage_requires_every_declared_property(self):
        assert set(TRIAGE_SCHEMA["required"]) == set(TRIAGE_SCHEMA["properties"])

    def test_appraisal_requires_every_declared_property(self):
        assert set(APPRAISAL_SCHEMA["required"]) == set(APPRAISAL_SCHEMA["properties"])

    def test_no_price_field_anywhere_in_appraisal(self):
        banned = {"price", "value", "estimate", "worth", "est_value", "value_range"}
        assert not (banned & set(APPRAISAL_SCHEMA["properties"]))

    def test_maker_and_period_are_nullable(self):
        # An unknown maker must be expressible as null, not fabricated.
        for f in ("maker", "period"):
            assert "null" in APPRAISAL_SCHEMA["properties"][f]["type"]

    def test_question_kinds_match_the_queue_model(self):
        assert set(QUESTION_KINDS) == {k.value for k in QuestionKind}

    def test_categories_cover_the_shop_taxonomy(self):
        for c in ("breweriana", "railroad", "stoneware", "cameras"):
            assert c in CATEGORIES

    def test_confidence_matches_the_appraisal_model(self):
        from src.appraisal import Confidence
        assert set(CONFIDENCE) == {c.value for c in Confidence}

    def test_question_items_are_fully_specified(self):
        q = APPRAISAL_SCHEMA["properties"]["questions"]["items"]
        assert set(q["required"]) == set(q["properties"])


class TestToVertex:
    # Vertex responseSchema is an OpenAPI 3.0 subset: it rejects union types
    # like {"type": ["string", "null"]} and wants nullable: true instead.
    # Proven live 2026-08-19 — the unconverted schema 400s.

    def test_union_typed_fields_become_nullable(self):
        v = to_vertex(APPRAISAL_SCHEMA)
        for f in ("maker", "period"):
            assert v["properties"][f]["type"] == "string"
            assert v["properties"][f]["nullable"] is True

    def test_no_union_types_survive_anywhere(self):
        def walk(node):
            if isinstance(node, dict):
                assert not isinstance(node.get("type"), list), node
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)
        walk(to_vertex(APPRAISAL_SCHEMA))

    def test_recurses_into_array_items(self):
        nested = {"type": "array",
                  "items": {"type": "object",
                            "properties": {"note": {"type": ["string", "null"]}}}}
        v = to_vertex(nested)
        assert v["items"]["properties"]["note"] == {"type": "string",
                                                    "nullable": True}

    def test_untouched_fields_pass_through(self):
        v = to_vertex(APPRAISAL_SCHEMA)
        assert v["properties"]["category"]["enum"] == CATEGORIES
        assert v["required"] == APPRAISAL_SCHEMA["required"]
        q = v["properties"]["questions"]["items"]
        assert set(q["required"]) == set(q["properties"])

    def test_schema_without_unions_converts_unchanged(self):
        assert to_vertex(TRIAGE_SCHEMA) == TRIAGE_SCHEMA

    def test_does_not_mutate_its_input(self):
        before = repr(APPRAISAL_SCHEMA)
        to_vertex(APPRAISAL_SCHEMA)
        assert repr(APPRAISAL_SCHEMA) == before


class TestPrompts:
    def test_triage_prompt_includes_caption(self):
        assert "Hamm's sign" in build_triage_prompt("Hamm's sign")

    def test_triage_handles_missing_caption(self):
        assert "(no caption)" in build_triage_prompt("")

    def test_triage_asks_about_duplicate_angles_when_given_context(self):
        p = build_triage_prompt("another view", previous_summary="Red Wing crock")
        assert "Red Wing crock" in p and "same item" in p

    def test_appraisal_prompt_injects_standing_rules(self):
        rules = [StandingRule(kind=QuestionKind.SCOPE, category="advertising",
                              answer="only the marked piece", learned_cycle="c1")]
        p = build_appraisal_prompt("wall of signs", standing_rules=rules)
        assert "only the marked piece" in p
        assert "DO NOT ask about them again" in p

    def test_appraisal_prompt_omits_rules_block_when_none(self):
        p = build_appraisal_prompt("a crock")
        assert "Standing rules" not in p

    def test_appraisal_prompt_carries_category_hint(self):
        assert "stoneware" in build_appraisal_prompt("a crock", category_hint="stoneware")


class TestSystemPrompts:
    def test_appraisal_system_forbids_pricing(self):
        from src.appraiser.prompts import APPRAISAL_SYSTEM
        assert "NEVER state or imply a price" in APPRAISAL_SYSTEM

    def test_appraisal_system_forbids_inferring_unseen_marks(self):
        from src.appraiser.prompts import APPRAISAL_SYSTEM
        assert "ONLY marks you can actually see" in APPRAISAL_SYSTEM

    def test_appraisal_system_prefers_questions_to_guesses(self):
        from src.appraiser.prompts import APPRAISAL_SYSTEM
        assert "EMIT A QUESTION rather than guessing" in APPRAISAL_SYSTEM

    def test_triage_system_biases_toward_false_positives(self):
        from src.appraiser.prompts import TRIAGE_SYSTEM
        assert "false negative loses the lot" in TRIAGE_SYSTEM

    def test_system_prompts_name_the_real_places(self):
        from src.appraiser.prompts import APPRAISAL_SYSTEM
        assert "Richmond, Illinois" in APPRAISAL_SYSTEM
        assert "Genoa City, Wisconsin" in APPRAISAL_SYSTEM
