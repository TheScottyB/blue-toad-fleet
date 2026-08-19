"""
Structured output schemas for Vertex AI.

Constrained decoding is doing real work here: it is what stops the model
returning prose where the pipeline expects a field, and it is why a missing
maker's mark becomes `null` plus a question rather than a confident invention.
"""

CATEGORIES = [
    "breweriana", "railroad", "advertising", "travel posters", "stoneware",
    "native american", "vintage toys", "cameras", "other", "unsorted",
]

CONFIDENCE = ["none", "low", "medium", "high"]

QUESTION_KINDS = ["lot_grouping", "scope", "mark", "condition", "appetite"]


TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_lot": {
            "type": "boolean",
            "description": "True if this photo shows a distinct lot. False for "
                           "duplicate angles, gallery filler, or signage.",
        },
        "same_lot_as_previous": {
            "type": "boolean",
            "description": "True if this appears to be another angle of the "
                           "immediately preceding photo's item.",
        },
        "category": {"type": "string", "enum": CATEGORIES},
        "summary": {
            "type": "string",
            "description": "Six words or fewer. What the object is.",
        },
        "fit_score": {
            "type": "number",
            "description": "0 to 1. How well this fits what the shop resells.",
        },
        "worth_appraising": {
            "type": "boolean",
            "description": "True if a closer appraisal pass is warranted.",
        },
    },
    "required": ["is_lot", "same_lot_as_previous", "category", "summary",
                 "fit_score", "worth_appraising"],
}


APPRAISAL_SCHEMA = {
    "type": "object",
    "properties": {
        "identification": {
            "type": "string",
            "description": "What the object is, stated as an appraiser would: "
                           "form, maker if determinable, approximate period.",
        },
        "maker": {"type": ["string", "null"]},
        "period": {"type": ["string", "null"]},
        "marks_observed": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Only marks actually visible in the image. Never inferred.",
        },
        "category": {"type": "string", "enum": CATEGORIES},
        "condition_notes": {"type": "array", "items": {"type": "string"}},
        "condition_penalty": {
            "type": "number",
            "description": "0 to 1. Fraction of value lost to observed condition.",
        },
        "fit_score": {"type": "number"},
        "confidence": {"type": "string", "enum": CONFIDENCE},
        "value_magnitude_hint": {
            "type": "number",
            "description": "Rough order of magnitude in USD, for RANKING QUESTIONS "
                           "ONLY. Never used as a price. Pricing happens downstream "
                           "from comps.",
        },
        "questions": {
            "type": "array",
            "description": "Emit a question wherever a determining attribute is not "
                           "visible. A question is always preferable to a guess.",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": QUESTION_KINDS},
                    "prompt": {"type": "string"},
                    "wants_photo": {"type": "boolean"},
                    "confidence_gap": {"type": "number"},
                },
                "required": ["kind", "prompt", "wants_photo", "confidence_gap"],
            },
        },
    },
    "required": ["identification", "maker", "period", "marks_observed", "category",
                 "condition_notes", "condition_penalty", "fit_score", "confidence",
                 "value_magnitude_hint", "questions"],
}
