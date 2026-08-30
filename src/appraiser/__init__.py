"""
Two-stage model routing: cheap triage over every photo, then structured appraisal.

Stage 1 — TRIAGE, Gemini 3.5 Flash Lite.
    Is this a lot or a duplicate angle? Roughly what is it? A routing/cost score.
    Does not drop a photo from grouping.

Stage 2 — APPRAISAL, Gemini 3.6 Flash.
    Identification and attribution: maker, period, form, marks, condition.
    Emits clarifying questions wherever a determining attribute isn't visible.

Grouping is a puzzle loop: every photo is assigned once. The split is a
throughput choice, not a coverage gate. Using one model for both wastes money
on the first pass or accuracy on the second.

The prompts forbid inventing a price. An appraiser states what a thing *is*;
what it's worth is a separate, weaker claim made downstream with comps and a
confidence band. Where a determining attribute is not visible, the correct
output is a question, not a guess.
"""

from src.appraiser.routing import (
    ModelTier, model_for, TRIAGE_MODEL, APPRAISAL_MODEL, CURATOR_MODEL, GEMMA_MODEL,
)
from src.appraiser.schema import (
    TRIAGE_SCHEMA, APPRAISAL_SCHEMA, CONTAINER_LOCATION_SCHEMA,
    CONTAINER_DECOMPOSITION_SCHEMA, to_vertex,
)
from src.appraiser.prompts import (
    build_triage_prompt, build_appraisal_prompt,
    build_container_location_prompt, build_container_decomposition_prompt,
)
from src.appraiser.containers import (
    NormalizedBox, crop_to_container, visible_contents, append_visible_contents,
)
from src.appraiser.engine import AppraisalEngine
from src.appraiser.grounded_batch import (
    GroundedPricingPipeline, grounded_reference_comps,
    grounded_status_reason, price_one_grounded, run_grounded_pricing_batch,
)

__all__ = [
    "ModelTier", "model_for", "TRIAGE_MODEL", "APPRAISAL_MODEL",
    "CURATOR_MODEL", "GEMMA_MODEL",
    "TRIAGE_SCHEMA", "APPRAISAL_SCHEMA", "CONTAINER_LOCATION_SCHEMA",
    "CONTAINER_DECOMPOSITION_SCHEMA", "to_vertex",
    "build_triage_prompt", "build_appraisal_prompt",
    "build_container_location_prompt", "build_container_decomposition_prompt",
    "NormalizedBox", "crop_to_container", "visible_contents", "append_visible_contents",
    "AppraisalEngine",
    "GroundedPricingPipeline",
    "grounded_reference_comps", "grounded_status_reason", "price_one_grounded",
    "run_grounded_pricing_batch",
]
