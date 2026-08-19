"""
Two-stage appraisal: cheap triage over everything, careful appraisal over survivors.

Stage 1 — TRIAGE, Gemini 3.5 Flash Lite, ~428 photos.
    Is this a lot or a duplicate angle? Roughly what is it? Worth a closer look?
    Cheap and fast. Cuts the gallery to candidates.

Stage 2 — APPRAISAL, Gemini 3.6 Flash, ~60 candidates.
    Identification and attribution: maker, period, form, marks, condition.
    Emits clarifying questions wherever a determining attribute isn't visible.

The split is deliberate and worth defending: a wide fan-out over hundreds of
images is a throughput problem, and judgment on the survivors is a reasoning
problem. Using one model for both wastes money on the first or accuracy on the
second.

The prompts forbid inventing a price. An appraiser states what a thing *is*;
what it's worth is a separate, weaker claim made downstream with comps and a
confidence band. Where a determining attribute is not visible, the correct
output is a question, not a guess.
"""

from src.appraiser.routing import ModelTier, model_for, TRIAGE_MODEL, APPRAISAL_MODEL
from src.appraiser.schema import TRIAGE_SCHEMA, APPRAISAL_SCHEMA, to_vertex
from src.appraiser.prompts import build_triage_prompt, build_appraisal_prompt

__all__ = [
    "ModelTier", "model_for", "TRIAGE_MODEL", "APPRAISAL_MODEL",
    "TRIAGE_SCHEMA", "APPRAISAL_SCHEMA", "to_vertex",
    "build_triage_prompt", "build_appraisal_prompt",
]
