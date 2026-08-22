"""
Structured output schemas for Vertex AI.

Constrained decoding is doing real work here: it is what stops the model
returning prose where the pipeline expects a field, and it is why a missing
maker's mark becomes `null` plus a question rather than a confident invention.
"""

from src.appraiser.containers import CONTAINER_TYPES, MARKET_ROLES

CATEGORIES = [
    "breweriana", "railroad", "advertising", "travel posters", "stoneware",
    "native american", "vintage toys", "cameras", "other", "unsorted",
]

CONFIDENCE = ["none", "low", "medium", "high"]

QUESTION_KINDS = ["policy", "lot_grouping", "scope", "mark", "condition", "appetite"]


def to_vertex(node):
    """
    Translate a JSON-Schema node into a Vertex ``responseSchema``.

    Vertex accepts an OpenAPI 3.0 subset: union types such as
    ``{"type": ["string", "null"]}`` are rejected and must be expressed as
    ``{"type": "string", "nullable": True}``. Recurses through ``properties``
    and ``items``, so nested objects and array element schemas are translated
    too. Returns a new structure; the input is never mutated.

    Verified against the live endpoint 2026-08-19: one real photo through
    ``gemini-3.6-flash`` on ``threebatdrone-prod-420`` (global), returned
    schema-valid structured output in 9.87s, 2149 in / 373 out.
    """
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k == "type" and isinstance(v, list):
            non_null = [t for t in v if t != "null"]
            out["type"] = non_null[0] if non_null else "string"
            if "null" in v:
                out["nullable"] = True
        elif k == "properties":
            out["properties"] = {pk: to_vertex(pv) for pk, pv in v.items()}
        elif k == "items":
            out["items"] = to_vertex(v)
        else:
            out[k] = v
    return out


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
        "needs_decomposition": {
            "type": "boolean",
            "description": "True when the sale subject is a box, tub, tray, case, "
                           "basket, or similarly bounded group whose visible contents "
                           "should be spatially isolated and itemized.",
        },
    },
    "required": ["is_lot", "same_lot_as_previous", "category", "summary",
                 "fit_score", "worth_appraising", "needs_decomposition"],
}


_BOUNDARY_SCHEMA = {
    "type": ["object", "null"],
    "description": "Tight physical container boundary in normalized 0..1000 image coordinates.",
    "properties": {
        "x_min": {"type": "number", "minimum": 0, "maximum": 1000},
        "y_min": {"type": "number", "minimum": 0, "maximum": 1000},
        "x_max": {"type": "number", "minimum": 0, "maximum": 1000},
        "y_max": {"type": "number", "minimum": 0, "maximum": 1000},
    },
    "required": ["x_min", "y_min", "x_max", "y_max"],
}


CONTAINER_LOCATION_SCHEMA = {
    "type": "object",
    "properties": {
        "is_container_lot": {
            "type": "boolean",
            "description": "True only when a physical boundary separates the sale subject's "
                           "contents from adjacent room or table clutter.",
        },
        "container_type": {"type": "string", "enum": CONTAINER_TYPES},
        "boundary": _BOUNDARY_SCHEMA,
        "confidence": {"type": "string", "enum": CONFIDENCE},
        "reason": {
            "type": "string",
            "description": "Brief visual evidence for the boundary, or why no boundary exists.",
        },
    },
    "required": ["is_container_lot", "container_type", "boundary", "confidence", "reason"],
}


CONTAINER_DECOMPOSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "contents": {
            "type": "array",
            "description": "Visible objects inside the isolated boundary. Group true duplicates; "
                           "do not invent objects hidden beneath the top layer.",
            "items": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Conservative checkable identification; maker only if visible.",
                    },
                    "quantity": {
                        "type": "integer", "minimum": 1,
                        "description": "Visible count, or conservative lower bound when overlapping.",
                    },
                    "maker_or_series": {"type": ["string", "null"]},
                    "period": {"type": ["string", "null"]},
                    "marks_observed": {"type": "array", "items": {"type": "string"}},
                    "market_role": {
                        "type": "string", "enum": MARKET_ROLES,
                        "description": "alpha for distinctive high-velocity assets; supporting for "
                                       "identifiable secondary goods; filler for generic residue.",
                    },
                    "confidence": {"type": "string", "enum": CONFIDENCE},
                    "condition_notes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["item_name", "quantity", "maker_or_series", "period",
                             "marks_observed", "market_role", "confidence", "condition_notes"],
            },
        },
        "background_exclusions": {
            "type": "array",
            "description": "Objects visible only beyond the rim or at crop margins; never lot contents.",
            "items": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["item_name", "reason"],
            },
        },
        "hidden_extent": {
            "type": "string",
            "enum": ["none", "minor", "substantial", "unknown"],
            "description": "How much of the in-boundary contents are obscured or layered.",
        },
        "questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Only questions that would materially change the contents itemization.",
        },
    },
    "required": ["contents", "background_exclusions", "hidden_extent", "questions"],
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
            "minimum": 0,
            "maximum": 1,
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
        "is_container": {
            "type": "boolean",
            "description": "True if the lot is a box, bin, tray, or tub whose contents "
                           "should be itemized separately from surrounding table clutter.",
        },
        "contents": {
            "type": "array",
            "items": {"type": "string"},
            "description": "High-velocity assets inside the container. Empty when "
                           "is_container is false. Never list neighboring table items.",
        },
    },
    "required": ["identification", "maker", "period", "marks_observed", "category",
                 "condition_notes", "condition_penalty", "fit_score", "confidence",
                 "value_magnitude_hint", "questions", "is_container", "contents"],
}
