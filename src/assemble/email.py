"""Clerk-facing absentee bid email. Descriptions survive whole."""
import textwrap
from typing import Iterable

from src.bidmath import (
    ABSENTEE_FEE, BidMechanic, Decision, Lot, clerk_directive, opening_bid, summarize,
    units_committed,
)


def compile_absentee_email(
    *,
    to: str,
    subject: str,
    auction_date: str,
    venue: str,
    lots: Iterable[Lot],
    decisions: Iterable[Decision],
    bidder: str = "Richmond General (Scott)",
    deadline: str | None = None,
    extra_instructions: list[str] | None = None,
) -> str:
    by_id = {l.lot_id: l for l in lots}
    approved = [d for d in decisions if d.allocated and d.max_bid is not None]
    summary = summarize(approved)

    lines = [
        f"TO: {to}",
        f"SUBJECT: {subject}",
        f"DATE: {deadline or 'Friday, August 21, 2026 (Before 8:00 PM CDT Cutoff)'}",
        "",
        "Blue Toad Auctions,",
        "",
        f"Please register the following absentee proxy bids for the {auction_date} auction",
        f"at {venue}.",
        "",
        "Bidder Info:",
        f"  Name: {bidder}",
        "  Resale Certificate: On file (Wisconsin Tax-Exempt)",
        f"  Terms: {int(ABSENTEE_FEE * 100)}% Absentee Buyer Fee acknowledged (Credit Card on File)",
        "",
        "-" * 89,
    ]

    for i, d in enumerate(approved, 1):
        lot = by_id.get(d.lot_id)
        description = " ".join(((lot.caption if lot else "") or d.category).split())
        wrapped = textwrap.wrap(description, width=78) or [description]
        start_bid = opening_bid(d.max_bid)
        lines.append(f"{i:>2}) [{d.lot_id}]  {wrapped[0]}")
        lines.extend(f"      {line}" for line in wrapped[1:])
        # The bid line has to state the MECHANIC, not just the number. A lot
        # sold times-the-money charges the max once per unit, so a line reading
        # "MAX $25.00" beside a sheet total of $285.00 is off by $50 and the
        # clerk cannot see why. This is the sentence the operator typed by hand
        # into the revised sheet on cutoff day; the system writes it now.
        if d.mechanic is BidMechanic.TIMES_THE_MONEY and d.unit_count > 1:
            k = units_committed(d.mechanic, d.unit_count, d.units_wanted)
            lines.append(
                f"      START ${start_bid:,.2f}   MAX ${d.max_bid:,.2f} PER UNIT "
                f"x {k} = ${d.committed_max:,.2f} TOTAL")
        elif d.mechanic is BidMechanic.CHOICE and d.unit_count > 1:
            k = units_committed(d.mechanic, d.unit_count, d.units_wanted)
            lines.append(
                f"      START ${start_bid:,.2f}   MAX ${d.max_bid:,.2f} PER UNIT "
                f"x {k} of {d.unit_count} = ${d.committed_max:,.2f} TOTAL")
        else:
            lines.append(f"      START ${start_bid:,.2f}   MAX ${d.max_bid:,.2f}")
        lines.append(f"      >> {clerk_directive(d)} <<")
        lines.append("")

    if extra_instructions is None:
        exceptions = [
            f"{d.lot_id} is an exception to the one-unit rule: take "
            f"{units_committed(d.mechanic, d.unit_count, d.units_wanted)} of the "
            f"{d.unit_count} at the per-unit price."
            for d in approved
            if units_committed(d.mechanic, d.unit_count, d.units_wanted) > 1
        ]
        extra_instructions = [
            *exceptions,
            "For any OTHER 'Buyer's Choice / Times the Money' shelf lot, max quantity is 1 unit only.",
            "Standard $5.00 bidding increments applied.",
            "Please confirm receipt of these absentee bids by reply email.",
        ]
    instructions = extra_instructions
    lines.extend([
        "-" * 89,
        f"TOTAL COMMITTED PROXY BIDS: ${summary.committed_max:,.2f} "
        f"(${summary.committed_all_in:,.2f} all-in w/ {int(ABSENTEE_FEE * 100)}% fee)",
    ])
    if summary.contingent:
        lines.append(
            f"CONTINGENT REMAINDER EXPOSURE: ${summary.contingent_max:,.2f} "
            f"(${summary.contingent_all_in:,.2f} all-in; only if stated conditions occur)"
        )
    lines.extend(["", "Special Instructions:"])
    lines.extend(f"  - {item}" for item in instructions)
    lines.extend(["", "Thank you,", "Richmond General"])
    return "\n".join(lines)
