"""Structured curator voice on top of master's pitch selection.

`build_pitch` (in pitch.py) still decides who is on the sheet. This module
phrases each tier as its own field so the console can badge Gemma vs template.
Invented dollar figures discard the whole model read — the prompt is not a guard.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.appraiser.routing import GEMMA_MODEL
from src.appraiser.schema import to_vertex
from src.gate.pitch import PitchFacts, PitchLot, invented_amounts

VOICE_SYSTEM = (
    "You are the shop's expert peer, not a yes-man. "
    "Return JSON with keys alpha, fast_smalls, wildcard, pushback. "
    "Each of alpha, fast_smalls, wildcard is 1-2 spoken sentences a shop owner "
    "would hear Friday afternoon — prose, not a JSON echo of the facts. "
    "Use only lot ids, captions, and dollar figures supplied in the user JSON. "
    "Never invent a price, comp, or lot. "
    "Pushback only if a SKIP rule and a matching allocated lot are in the payload; "
    "otherwise set pushback to null."
)

VOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "alpha": {"type": "string"},
        "fast_smalls": {"type": "string"},
        "wildcard": {"type": "string"},
        "pushback": {"type": ["string", "null"]},
    },
    "required": ["alpha", "fast_smalls", "wildcard", "pushback"],
}


@dataclass(frozen=True)
class PitchVoice:
    alpha: str
    fast_smalls: str
    wildcard: str
    pushback: str | None = None
    model: str = GEMMA_MODEL
    from_cache: bool = False
    fallback: bool = False


def _lot_facts(l: PitchLot) -> dict[str, str]:
    return {
        "lot_id": l.lot_id,
        "caption": l.caption,
        "max_bid": f"${l.max_bid:.2f}",
    }


def _payload(facts: PitchFacts) -> dict:
    return {
        "alpha": [_lot_facts(l) for l in facts.alpha],
        "fast_smalls": [_lot_facts(l) for l in facts.fast_smalls],
        "ruled_out": list(facts.ruled_out),
        "committed_max": f"${facts.committed_max:,.2f}",
        "committed_all_in": f"${facts.committed_all_in:,.2f}",
    }


def template_voice(facts: PitchFacts) -> PitchVoice:
    if not facts.alpha and not facts.fast_smalls:
        return PitchVoice(
            alpha="No allocated lots to pitch this cycle.",
            fast_smalls="None this cycle.",
            wildcard="None this cycle.",
            pushback=None,
            fallback=True,
        )
    alpha = ", ".join(f"{l.lot_id} {l.caption} (${l.max_bid:.0f} max)" for l in facts.alpha)
    smalls = (
        ", ".join(f"{l.lot_id} {l.caption} (${l.max_bid:.0f} max)" for l in facts.fast_smalls)
        or "None this cycle."
    )
    ruled = "; ".join(facts.ruled_out) if facts.ruled_out else "None this cycle."
    return PitchVoice(
        alpha=alpha or "None this cycle.",
        fast_smalls=smalls,
        wildcard=ruled,
        pushback=None,
        fallback=True,
    )


def _prose(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _trusted(voice: PitchVoice, facts: PitchFacts) -> bool:
    blob = " ".join(
        p for p in (voice.alpha, voice.fast_smalls, voice.wildcard, voice.pushback or "")
        if p
    )
    return not invented_amounts(blob, facts.allowed_amounts)


def _from_model(data: dict) -> PitchVoice | None:
    alpha = _prose(data.get("alpha"))
    smalls = _prose(data.get("fast_smalls"))
    wild = _prose(data.get("wildcard"))
    if not (alpha and smalls and wild):
        return None
    push = data.get("pushback")
    return PitchVoice(
        alpha=alpha,
        fast_smalls=smalls,
        wildcard=wild,
        pushback=_prose(push) if push is not None else None,
        model=GEMMA_MODEL,
        fallback=False,
    )


def _parse_text(text: str) -> dict | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _call_gemma(client: Any, user: str) -> str:
    from google.genai import types
    resp = client.models.generate_content(
        model=GEMMA_MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=VOICE_SYSTEM,
            response_mime_type="application/json",
            response_schema=to_vertex(VOICE_SCHEMA),
            temperature=0.2,
        ),
    )
    return getattr(resp, "text", None) or ""


def write_pitch_voice(
    facts: PitchFacts,
    *,
    client: Any = None,
    cache_path: str | Path | None = None,
) -> PitchVoice:
    """Gemma writes copy. Invented dollars, missing client, or JSON echo → template."""
    fallback = template_voice(facts)
    if not facts.alpha and not facts.fast_smalls:
        return fallback

    key = json.dumps(_payload(facts), sort_keys=True)
    path = Path(cache_path) if cache_path else None
    if path and path.exists():
        try:
            cached = json.loads(path.read_text())
            if cached.get("key") == key and isinstance(cached.get("voice"), dict):
                v = cached["voice"]
                voice = PitchVoice(
                    alpha=v["alpha"],
                    fast_smalls=v["fast_smalls"],
                    wildcard=v["wildcard"],
                    pushback=v.get("pushback"),
                    model=v.get("model", GEMMA_MODEL),
                    from_cache=True,
                    fallback=False,
                )
                if _trusted(voice, facts):
                    return voice
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass

    if client is None:
        return fallback

    user = (
        "Write curator voice. Each of alpha, fast_smalls, wildcard is prose. "
        "Do not copy the facts as JSON.\nFacts:\n"
        + json.dumps(_payload(facts))
        + "\nFIGURES YOU MAY USE: "
        + ", ".join(f"${a:,.2f}" for a in sorted(facts.allowed_amounts))
    )
    try:
        text = _call_gemma(client, user)
    except Exception:
        return fallback

    data = _parse_text(text)
    if not data:
        return fallback
    voice = _from_model(data)
    if voice is None or not _trusted(voice, facts):
        return fallback

    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "key": key,
            "voice": {
                "alpha": voice.alpha,
                "fast_smalls": voice.fast_smalls,
                "wildcard": voice.wildcard,
                "pushback": voice.pushback,
                "model": voice.model,
            },
        }, indent=2))
    return voice
