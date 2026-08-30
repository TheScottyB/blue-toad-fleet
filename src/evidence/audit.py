"""Append-only operator and agent events for one cycle. Not a Google invoice."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuditEvent:
    schema_version: int
    at: str
    cycle_id: str
    actor: str
    kind: str
    detail: dict[str, Any]
    measured_cost_usd: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditTrail:
    """Thread-safe, in-process trail. Cloud Run recycle clears it."""

    def __init__(self, cycle_id: str) -> None:
        if not cycle_id:
            raise ValueError("audit trail requires a cycle id")
        self.cycle_id = cycle_id
        self.events: list[AuditEvent] = []
        self._lock = threading.Lock()

    def record(
        self,
        *,
        actor: str,
        kind: str,
        detail: dict[str, Any],
        measured_cost_usd: float | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            schema_version=1,
            at=_utc_now(),
            cycle_id=self.cycle_id,
            actor=actor,
            kind=kind,
            detail=dict(detail),
            measured_cost_usd=measured_cost_usd,
        )
        with self._lock:
            self.events.append(event)
        return event

    def reset(self) -> None:
        with self._lock:
            self.events.clear()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [event.as_dict() for event in self.events]
