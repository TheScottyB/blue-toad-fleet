import json
from types import SimpleNamespace

import pytest

from src.evidence.telemetry import UsageTelemetry


def _response(input_tokens=100, output_tokens=25):
    return SimpleNamespace(usage_metadata=SimpleNamespace(
        prompt_token_count=input_tokens,
        candidates_token_count=output_tokens,
        total_token_count=input_tokens + output_tokens,
        cached_content_token_count=5,
    ))


def test_records_measured_usage_latency_and_cost():
    telemetry = UsageTelemetry(
        "cycle-1", rates_usd_per_million={"model-a": (1.0, 2.0)},
    )
    response = telemetry.call(
        stage="appraisal", model="model-a", retry_index=0, fallback=False,
        invoke=lambda: _response(),
    )
    assert response.usage_metadata.total_token_count == 125
    row = telemetry.calls[0]
    assert row.input_tokens == 100
    assert row.output_tokens == 25
    assert row.duration_ms >= 0
    assert row.measured_cost_usd == pytest.approx(0.00015)
    assert telemetry.aggregate()["summary"]["cost_status"] == "measured"


def test_failed_retry_and_fallback_are_retained():
    telemetry = UsageTelemetry("cycle-1")
    with pytest.raises(RuntimeError):
        telemetry.call(
            stage="triage", model="primary", retry_index=0, fallback=False,
            invoke=lambda: (_ for _ in ()).throw(RuntimeError("quota")),
        )
    telemetry.call(
        stage="triage", model="fallback", retry_index=1, fallback=True,
        invoke=_response,
    )
    summary = telemetry.aggregate()["summary"]
    assert summary["request_count"] == 2
    assert summary["failed_request_count"] == 1
    assert summary["retry_request_count"] == 1
    assert summary["fallback_request_count"] == 1
    assert summary["measured_cost_usd"] is None


def test_stage_timing_and_atomic_report(tmp_path):
    telemetry = UsageTelemetry("cycle-1")
    with telemetry.stage("intake"):
        pass
    output = telemetry.write(tmp_path / "usage.json")
    payload = json.loads(output.read_text())
    assert payload["stages"][0]["stage"] == "intake"
    assert payload["stages"][0]["status"] == "succeeded"


def test_engine_records_provider_usage_and_fallback(monkeypatch):
    from src.appraiser.engine import AppraisalEngine

    class Models:
        def __init__(self):
            self.calls = 0

        def generate_content(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("primary unavailable")
            response = _response()
            response.text = json.dumps({
                "is_lot": True,
                "same_lot_as_previous": False,
                "category": "cards",
                "summary": "cards",
                "fit_score": 0.9,
                "worth_appraising": True,
                "needs_decomposition": False,
            })
            return response

    telemetry = UsageTelemetry("cycle-1")
    engine = AppraisalEngine(telemetry=telemetry)
    engine._client = SimpleNamespace(models=Models())
    result = engine.triage_photo("p1", "cards")
    assert result["model_used"] == "gemini-2.5-flash"
    assert [row.status for row in telemetry.calls] == ["failed", "succeeded"]
    assert telemetry.calls[1].fallback is True
