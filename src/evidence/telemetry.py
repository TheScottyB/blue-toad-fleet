"""Measured model-call and stage telemetry, kept separate from cost estimates."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _value(source: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(source, name, None)
        if value is None and isinstance(source, dict):
            value = source.get(name)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None


@dataclass(frozen=True)
class UsageRecord:
    schema_version: int
    cycle_id: str
    stage: str
    model: str
    started_at: str
    finished_at: str
    duration_ms: float
    status: str
    retry_index: int
    fallback: bool
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    usage_units: dict[str, int]
    rate_snapshot_usd_per_million: dict[str, float] | None
    measured_cost_usd: float | None
    error: str | None = None


@dataclass(frozen=True)
class StageRecord:
    schema_version: int
    cycle_id: str
    stage: str
    started_at: str
    finished_at: str
    duration_ms: float
    status: str
    error: str | None = None


class UsageTelemetry:
    """Thread-safe, append-only telemetry for one cycle."""

    def __init__(
        self,
        cycle_id: str,
        *,
        rates_usd_per_million: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        if not cycle_id:
            raise ValueError("telemetry requires a cycle id")
        self.cycle_id = cycle_id
        self.rates = dict(rates_usd_per_million or {})
        self.calls: list[UsageRecord] = []
        self.stages: list[StageRecord] = []
        self._lock = threading.Lock()

    def call(
        self,
        *,
        stage: str,
        model: str,
        retry_index: int,
        fallback: bool,
        invoke: Callable[[], Any],
    ) -> Any:
        """Run one request and retain measured latency and provider usage."""
        started_at = _utc_now()
        started = time.perf_counter()
        response = None
        error = None
        try:
            response = invoke()
            return response
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            finished_at = _utc_now()
            metadata = getattr(response, "usage_metadata", None)
            input_tokens = _value(
                metadata, "prompt_token_count", "prompt_tokens", "input_tokens",
            )
            output_tokens = _value(
                metadata, "candidates_token_count", "candidate_token_count",
                "output_tokens",
            )
            total_tokens = _value(metadata, "total_token_count", "total_tokens")
            units = {}
            cached = _value(metadata, "cached_content_token_count", "cached_tokens")
            if cached is not None:
                units["cached_input_tokens"] = cached
            rate = self.rates.get(model)
            measured_cost = None
            rate_snapshot = None
            if rate is not None:
                rate_snapshot = {"input": rate[0], "output": rate[1]}
                if input_tokens is not None and output_tokens is not None:
                    measured_cost = round(
                        (input_tokens * rate[0] + output_tokens * rate[1]) / 1_000_000,
                        8,
                    )
            record = UsageRecord(
                schema_version=1,
                cycle_id=self.cycle_id,
                stage=stage,
                model=model,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                status="failed" if error else "succeeded",
                retry_index=retry_index,
                fallback=fallback,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                usage_units=units,
                rate_snapshot_usd_per_million=rate_snapshot,
                measured_cost_usd=measured_cost,
                error=error,
            )
            with self._lock:
                self.calls.append(record)

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started_at = _utc_now()
        started = time.perf_counter()
        error = None
        try:
            yield
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            record = StageRecord(
                schema_version=1,
                cycle_id=self.cycle_id,
                stage=name,
                started_at=started_at,
                finished_at=_utc_now(),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                status="failed" if error else "succeeded",
                error=error,
            )
            with self._lock:
                self.stages.append(record)

    def aggregate(self) -> dict:
        with self._lock:
            calls = list(self.calls)
            stages = list(self.stages)
        input_known = [row.input_tokens for row in calls if row.input_tokens is not None]
        output_known = [row.output_tokens for row in calls if row.output_tokens is not None]
        costs = [row.measured_cost_usd for row in calls if row.measured_cost_usd is not None]
        if not calls:
            measured_cost = None
            cost_status = "no_calls"
        elif len(costs) == len(calls):
            measured_cost = round(sum(costs), 8)
            cost_status = "measured"
        else:
            measured_cost = None
            cost_status = "unavailable"
        return {
            "schema_version": 1,
            "cycle_id": self.cycle_id,
            "calls": [asdict(row) for row in calls],
            "stages": [asdict(row) for row in stages],
            "summary": {
                "request_count": len(calls),
                "failed_request_count": sum(row.status == "failed" for row in calls),
                "retry_request_count": sum(row.retry_index > 0 for row in calls),
                "fallback_request_count": sum(row.fallback for row in calls),
                "input_tokens": sum(input_known) if len(input_known) == len(calls) else None,
                "output_tokens": sum(output_known) if len(output_known) == len(calls) else None,
                "measured_cost_usd": measured_cost,
                "cost_status": cost_status,
                "stage_duration_ms": round(sum(row.duration_ms for row in stages), 3),
            },
        }

    def reset(self) -> None:
        """Tests only. Clears in-process Google call records."""
        with self._lock:
            self.calls.clear()
            self.stages.clear()

    def write(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(json.dumps(self.aggregate(), indent=2, sort_keys=True) + "\n")
        temporary.replace(destination)
        return destination
