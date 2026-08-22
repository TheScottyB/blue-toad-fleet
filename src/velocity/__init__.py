"""Cadence gate from public eBay sold+active counts.

The shop's two-week absentee cycle needs lots that can clear in under 14 days.
Public eBay search only goes ~90 days on completed listings. Days-on-market
per listing is not required.

    days_of_supply = window_days * active_now / sold_units_in_window
    clears_in_14   = days_of_supply <= 14

Equivalent: sold/active >= window/cadence (90/14 ≈ 6.43).
"""

CADENCE_DAYS = 14
WINDOW_DAYS = 90


def days_of_supply(
    sold_units: int,
    active_listings: int,
    window_days: int = WINDOW_DAYS,
) -> float | None:
    """Implied days to clear the standing pile. None if nothing sold."""
    if sold_units <= 0:
        return None
    if active_listings < 0 or window_days <= 0:
        raise ValueError("active_listings and window_days must be non-negative / positive")
    return window_days * active_listings / sold_units


def clears_within_cadence(
    sold_units: int,
    active_listings: int,
    *,
    cadence_days: int = CADENCE_DAYS,
    window_days: int = WINDOW_DAYS,
) -> bool:
    """True when implied supply lasts no longer than the absentee cadence."""
    dos = days_of_supply(sold_units, active_listings, window_days)
    return dos is not None and dos <= cadence_days
