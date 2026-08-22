"""Model routing. One decision, stated once, so it can be defended in the README."""

from enum import Enum

# Hackathon requires Gemini 3.5 or newer. Both of these qualify.
TRIAGE_MODEL = "gemini-3.5-flash-lite"    # $0.30 / $2.50 per 1M tokens, ~350 tok/s
APPRAISAL_MODEL = "gemini-3.6-flash"      # $1.50 / $7.50 per 1M tokens

# The curator's voice. An open model, and the only tier here that writes prose
# rather than deciding anything — it is handed a finished sheet and asked to
# phrase it. Serves from the `global` endpoint only; us-central1 answers
# FAILED_PRECONDITION for this one, same quirk as the Gemini tiers.
CURATOR_MODEL = "gemma-4-26b-a4b-it-maas"

# Rough token accounting per photo, used for cost estimates and budget guards.
EST_INPUT_TOKENS_PER_PHOTO = 1_500
EST_OUTPUT_TOKENS_TRIAGE = 120
EST_OUTPUT_TOKENS_APPRAISAL = 400
EST_OUTPUT_TOKENS_CONTAINER_LOCATION = 120
EST_OUTPUT_TOKENS_CONTAINER_ITEMIZATION = 600

_PRICING = {  # USD per 1M tokens (input, output)
    TRIAGE_MODEL: (0.30, 2.50),
    APPRAISAL_MODEL: (1.50, 7.50),
}


class ModelTier(str, Enum):
    TRIAGE = "triage"
    APPRAISAL = "appraisal"


def model_for(tier: ModelTier) -> str:
    return TRIAGE_MODEL if tier is ModelTier.TRIAGE else APPRAISAL_MODEL


def estimate_cost_usd(
    photo_count: int,
    candidate_count: int,
    container_count: int = 0,
) -> dict[str, float]:
    """
    What one cycle costs. Printed in the run log so the operator always knows,
    and so 'is this affordable' is never a question anyone has to guess at.
    """
    t_in, t_out = _PRICING[TRIAGE_MODEL]
    a_in, a_out = _PRICING[APPRAISAL_MODEL]

    triage = (
        photo_count * EST_INPUT_TOKENS_PER_PHOTO / 1e6 * t_in
        + photo_count * EST_OUTPUT_TOKENS_TRIAGE / 1e6 * t_out
    )
    appraisal = (
        candidate_count * EST_INPUT_TOKENS_PER_PHOTO / 1e6 * a_in
        + candidate_count * EST_OUTPUT_TOKENS_APPRAISAL / 1e6 * a_out
    )
    # One full-photo boundary call plus one cropped itemization call per
    # selected container. Both use the appraisal model.
    decomposition = (
        container_count * 2 * EST_INPUT_TOKENS_PER_PHOTO / 1e6 * a_in
        + container_count * (
            EST_OUTPUT_TOKENS_CONTAINER_LOCATION
            + EST_OUTPUT_TOKENS_CONTAINER_ITEMIZATION
        ) / 1e6 * a_out
    )
    return {
        "triage_usd": round(triage, 4),
        "appraisal_usd": round(appraisal, 4),
        "decomposition_usd": round(decomposition, 4),
        "total_usd": round(triage + appraisal + decomposition, 4),
    }
