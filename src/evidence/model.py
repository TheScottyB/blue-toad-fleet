"""Evidence records whose derived figures may influence a cycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path


@dataclass(frozen=True)
class AbsorptionEvidence:
    schema_version: int
    lot_id: str
    query: str
    marketplace: str
    window_start: str
    window_end: str
    displayed_window: str
    sold_units_last_365_days: int
    sold_rows: int
    active_listings_now: int
    sold_pages_complete: bool
    sold_page_count: int
    captured_at: str
    reviewer: str
    source_sha256: dict[str, str]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported absorption evidence schema")
        start = date.fromisoformat(self.window_start)
        end = date.fromisoformat(self.window_end)
        if (end - start).days != 365:
            raise ValueError("sold window must be exactly 365 days")
        if self.sold_units_last_365_days < self.sold_rows:
            raise ValueError("sold units cannot be lower than sold listing rows")
        if self.active_listings_now <= 0:
            raise ValueError("active listing denominator must be positive")
        if not self.sold_pages_complete or self.sold_page_count < 1:
            raise ValueError("sold pagination must be complete")
        if not all((self.lot_id, self.query, self.displayed_window,
                    self.captured_at, self.reviewer)):
            raise ValueError("absorption evidence is missing required identity")
        if not self.source_sha256:
            raise ValueError("absorption evidence requires source hashes")

    @property
    def absorption(self) -> float:
        return round(self.sold_units_last_365_days / self.active_listings_now, 2)

    @property
    def months_of_supply(self) -> float:
        return round(12 / self.absorption, 1)

    def as_dict(self) -> dict:
        return {
            **asdict(self),
            "absorption": self.absorption,
            "months_of_supply": self.months_of_supply,
            "metric": "sold_units_last_365_days / active_listings_now",
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "AbsorptionEvidence":
        fields = {
            "schema_version", "lot_id", "query", "marketplace", "window_start",
            "window_end", "displayed_window", "sold_units_last_365_days",
            "sold_rows", "active_listings_now", "sold_pages_complete",
            "sold_page_count", "captured_at", "reviewer", "source_sha256",
        }
        return cls(**{name: raw[name] for name in fields})


def load_absorption_evidence(path: str | Path) -> list[AbsorptionEvidence]:
    source = Path(path)
    raw = json.loads(source.read_text())
    rows = raw if isinstance(raw, list) else [raw]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("absorption evidence must contain one or more records")
    evidence = [AbsorptionEvidence.from_dict(row) for row in rows]
    ids = [row.lot_id for row in evidence]
    if len(ids) != len(set(ids)):
        raise ValueError("absorption evidence contains duplicate lot ids")
    return evidence
