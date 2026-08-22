"""Validated records shared by the uploader, service, and processing job."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
CYCLE_STATES = frozenset({
    "staged", "running", "degraded", "validated", "published", "failed",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str, field: str) -> str:
    value = (value or "").strip().lower()
    if not _ID.fullmatch(value):
        raise ValueError(
            f"{field} must start with a letter or number and contain only "
            "lowercase letters, numbers, and hyphens (63 characters max)"
        )
    return value


def cycle_prefix(shop_id: str, cycle_id: str) -> str:
    """Return the only permitted durable prefix for a shop/cycle pair."""
    return f"shops/{_safe_id(shop_id, 'shop_id')}/cycles/{_safe_id(cycle_id, 'cycle_id')}"


def _required_text(value: str, field: str, *, maximum: int = 500) -> str:
    normalized = (value or "").strip()
    if not normalized or len(normalized) > maximum or "\x00" in normalized:
        raise ValueError(f"{field} is missing or invalid")
    return normalized


def _iso_date(value: str, field: str) -> str:
    normalized = _required_text(value, field, maximum=10)
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc


def _iso_datetime(value: str, field: str) -> str:
    normalized = _required_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include an explicit UTC offset")
    return parsed.isoformat()


@dataclass(frozen=True)
class CycleRequest:
    cycle_id: str
    listing_id: str
    auction_title: str
    auction_date: str
    timezone_name: str
    venue: str
    deadline: str
    shop_id: str = "richmond-general"
    budget_cap: float = 600.0
    auto_send_threshold: float = 35.0
    email_to: str = "info@bluetoadauctions.com"
    created_at: str = ""
    source: str = "sanctioned-gallery-drop"

    def __post_init__(self):
        object.__setattr__(self, "cycle_id", _safe_id(self.cycle_id, "cycle_id"))
        object.__setattr__(self, "shop_id", _safe_id(self.shop_id, "shop_id"))
        listing = (self.listing_id or "").strip()
        if not listing or len(listing) > 128 or "/" in listing or ".." in listing:
            raise ValueError("listing_id is missing or unsafe")
        object.__setattr__(self, "listing_id", listing)
        object.__setattr__(
            self, "auction_title", _required_text(self.auction_title, "auction_title"))
        object.__setattr__(
            self, "auction_date", _iso_date(self.auction_date, "auction_date"))
        timezone_name = _required_text(
            self.timezone_name, "timezone_name", maximum=128)
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone_name: {timezone_name}") from exc
        object.__setattr__(self, "timezone_name", timezone_name)
        object.__setattr__(self, "venue", _required_text(self.venue, "venue"))
        object.__setattr__(self, "deadline", _iso_datetime(self.deadline, "deadline"))
        object.__setattr__(
            self, "email_to", _required_text(self.email_to, "email_to", maximum=320))
        if not 0 < float(self.budget_cap) <= 1_000_000:
            raise ValueError("budget_cap must be greater than zero")
        if not 0 <= float(self.auto_send_threshold) <= float(self.budget_cap):
            raise ValueError("auto_send_threshold must be between zero and budget_cap")
        object.__setattr__(self, "budget_cap", float(self.budget_cap))
        object.__setattr__(self, "auto_send_threshold", float(self.auto_send_threshold))
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now())

    @property
    def prefix(self) -> str:
        return cycle_prefix(self.shop_id, self.cycle_id)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "CycleRequest":
        return cls(
            cycle_id=raw["cycle_id"],
            listing_id=str(raw["listing_id"]),
            auction_title=raw["auction_title"],
            auction_date=raw["auction_date"],
            timezone_name=raw["timezone_name"],
            venue=raw["venue"],
            deadline=raw["deadline"],
            shop_id=raw.get("shop_id") or "richmond-general",
            budget_cap=float(raw.get("budget_cap", 600.0)),
            auto_send_threshold=float(raw.get("auto_send_threshold", 35.0)),
            email_to=raw.get("email_to") or "info@bluetoadauctions.com",
            created_at=raw.get("created_at") or "",
            source=raw.get("source") or "sanctioned-gallery-drop",
        )


@dataclass(frozen=True)
class CycleStatus:
    state: str
    cycle_id: str
    shop_id: str
    updated_at: str
    detail: str = ""
    operation_name: str | None = None
    artifacts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in CYCLE_STATES:
            raise ValueError(f"invalid cycle state: {self.state}")

    def as_dict(self) -> dict:
        data = asdict(self)
        data["artifacts"] = list(self.artifacts)
        return data

    @classmethod
    def make(
        cls,
        request: CycleRequest,
        state: str,
        detail: str = "",
        operation_name: str | None = None,
        artifacts=(),
    ) -> "CycleStatus":
        return cls(
            state=state,
            cycle_id=request.cycle_id,
            shop_id=request.shop_id,
            updated_at=utc_now(),
            detail=detail,
            operation_name=operation_name,
            artifacts=tuple(artifacts),
        )

    @classmethod
    def from_dict(cls, raw: dict) -> "CycleStatus":
        return cls(
            state=raw["state"],
            cycle_id=raw["cycle_id"],
            shop_id=raw["shop_id"],
            updated_at=raw["updated_at"],
            detail=raw.get("detail") or "",
            operation_name=raw.get("operation_name"),
            artifacts=tuple(raw.get("artifacts") or ()),
        )
