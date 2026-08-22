"""Gemma writes curator prose. BidMath still owns the dollars."""
import json
from types import SimpleNamespace

from src.gate.pitch import PitchFacts, PitchLot, invented_amounts
from src.gate.voice import VOICE_SYSTEM, template_voice, write_pitch_voice


def sample_facts(**kw) -> PitchFacts:
    facts = PitchFacts(
        alpha=[PitchLot("BT-001", "Topps cards", "vintage cards", 100.0)],
        fast_smalls=[PitchLot("BT-066", "handheld games", "vintage toys", 10.0)],
        ruled_out=["sports memorabilia — SKIP — store currently overstocked"],
        committed_max=110.0,
        committed_all_in=126.5,
    )
    for k, v in kw.items():
        object.__setattr__(facts, k, v) if False else None
    return facts


class FakeClient:
    def __init__(self, payload, error=None):
        self.payload = payload
        self.error = error
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error:
            raise self.error
        return SimpleNamespace(text=json.dumps(self.payload))


class TestTemplateFallback:
    def test_empty_pitch_has_empty_copy(self):
        voice = template_voice(PitchFacts())
        assert "No allocated lots" in voice.alpha
        assert voice.fallback is True

    def test_template_names_the_alpha_lot(self):
        voice = template_voice(sample_facts())
        assert "BT-001" in voice.alpha
        assert "Topps cards" in voice.alpha


class TestWritePitchVoice:
    def test_uses_prose_from_the_model(self):
        client = FakeClient({
            "alpha": "Keep BT-001 Topps cards at the $100 cap.",
            "fast_smalls": "BT-066 handheld games is a cheap turn at $10.",
            "wildcard": "Sports memorabilia stays skipped.",
            "pushback": "Understood on dropping sports memorabilia, but BT-001 stays at $100.",
        })
        voice = write_pitch_voice(sample_facts(), client=client)
        assert voice.alpha.startswith("Keep BT-001")
        assert voice.fallback is False
        assert client.calls and "gemma" in client.calls[0]["model"].lower()

    def test_falls_back_when_the_client_raises(self):
        client = FakeClient({}, error=RuntimeError("vertex down"))
        voice = write_pitch_voice(sample_facts(), client=client)
        assert voice.fallback is True
        assert "BT-001" in voice.alpha

    def test_falls_back_when_the_model_echoes_json_instead_of_prose(self):
        client = FakeClient({
            "alpha": [{"lot_id": "BT-001", "max_bid": 100}],
            "fast_smalls": [],
            "wildcard": {"lot_id": "BT-066"},
            "pushback": None,
        })
        voice = write_pitch_voice(sample_facts(), client=client)
        assert voice.fallback is True

    def test_invented_dollar_discards_the_whole_read(self):
        client = FakeClient({
            "alpha": "These Topps will clear $450 all day.",
            "fast_smalls": "BT-066 at $10.",
            "wildcard": "skip sports.",
            "pushback": None,
        })
        facts = sample_facts()
        assert invented_amounts("These Topps will clear $450 all day.", facts.allowed_amounts)
        voice = write_pitch_voice(facts, client=client)
        assert voice.fallback is True
        assert "$450" not in voice.alpha

    def test_system_prompt_forbids_inventing_prices(self):
        assert "Never invent a price" in VOICE_SYSTEM
        assert "yes-man" in VOICE_SYSTEM.lower()

    def test_cache_avoids_a_second_model_call(self, tmp_path):
        cache = tmp_path / "gemma_voice.json"
        client = FakeClient({
            "alpha": "Keep BT-001 at $100.",
            "fast_smalls": "BT-066 at $10.",
            "wildcard": "skip sports.",
            "pushback": None,
        })
        facts = sample_facts()
        a = write_pitch_voice(facts, client=client, cache_path=cache)
        b = write_pitch_voice(facts, client=client, cache_path=cache)
        assert a.alpha == b.alpha == "Keep BT-001 at $100."
        assert len(client.calls) == 1
        assert b.from_cache is True
