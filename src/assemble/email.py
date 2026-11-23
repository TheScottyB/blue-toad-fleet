"""Clerk-facing absentee bid email. Descriptions survive whole."""
import textwrap
from typing import Iterable

from src.bidmath import (
    ABSENTEE_FEE, BidMechanic, Decision, Lot, clerk_directive, opening_bid, summarize,
    units_committed,
)


def _single_line(value: str) -> str:
    return " ".join(
        str(value or "").replace("\x00", " ").replace("\r", " ").replace("\n", " ").split()
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
    approved = [
        d for d in decisions
        if d.allocated
        and d.max_bid is not None
        and not d.needs_election
        and not d.needs_mechanic_ruling
        and d.mechanic is not BidMechanic.UNKNOWN
    ]
    firm = [d for d in approved if not d.speculative]
    contingent = [d for d in approved if d.speculative]
    summary = summarize(approved)

    clean_to = _single_line(to)
    clean_subject = _single_line(subject)
    clean_date = _single_line(
        deadline or "Friday, August 21, 2026 (Before 8:00 PM CDT Cutoff)"
    )
    clean_auction_date = _single_line(auction_date)
    clean_venue = _single_line(venue)
    clean_bidder = _single_line(bidder)

    lines = [
        f"TO: {clean_to}",
        f"SUBJECT: {clean_subject}",
        f"DATE: {clean_date}",
        "",
        "Blue Toad Auctions,",
        "",
        f"Please register the following absentee proxy bids for the {clean_auction_date} auction",
        f"at {clean_venue}.",
        "",
        "Bidder Info:",
        f"  Name: {clean_bidder}",
        "  Resale Certificate: On file (Wisconsin Tax-Exempt)",
        f"  Terms: {round(ABSENTEE_FEE * 100)}% Absentee Buyer Fee acknowledged (Credit Card on File)",
        "",
        "-" * 89,
    ]

    for i, d in enumerate(firm, 1):
        lot = by_id.get(d.lot_id)
        description = _single_line((lot.caption if lot else "") or d.category)
        wrapped = textwrap.wrap(description, width=78) or [description]
        start_bid = opening_bid(d.max_bid)
        clean_id = _single_line(d.lot_id)
        lines.append(f"{i:>2}) [{clean_id}]  {wrapped[0]}")
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
        lines.append(f"      >> {_single_line(clerk_directive(d))} <<")
        lines.append("")

    if contingent:
        lines.append("Contingent Remainder Opportunities (Only If Lot Re-Opens):")
        lines.append("")
        for d in contingent:
            lot = by_id.get(d.lot_id) or by_id.get(d.lot_id.removesuffix("-R"))
            description = _single_line((lot.caption if lot else "") or d.category)
            wrapped = textwrap.wrap(description, width=78) or [description]
            clean_id = _single_line(d.lot_id)
            lines.append(f"  - [{clean_id}]  {wrapped[0]}")
            lines.extend(f"      {line}" for line in wrapped[1:])
            lines.append(f"      >> {_single_line(clerk_directive(d))} <<")
            lines.append("")

    if extra_instructions is None:
        exceptions = [
            f"{_single_line(d.lot_id)} is an exception to the one-unit rule: take "
            f"{units_committed(d.mechanic, d.unit_count, d.units_wanted)} of the "
            f"{d.unit_count} at the per-unit price."
            for d in firm
            if units_committed(d.mechanic, d.unit_count, d.units_wanted) > 1
        ]
        extra_instructions = [
            *exceptions,
            "For any OTHER 'Buyer's Choice / Times the Money' shelf lot, max quantity is 1 unit only.",
            "Standard $5.00 bidding increments applied.",
            "Please confirm receipt of these absentee bids by reply email.",
        ]
    instructions = [_single_line(item) for item in extra_instructions]
    lines.extend([
        "-" * 89,
        f"TOTAL COMMITTED PROXY BIDS: ${summary.committed_max:,.2f} "
        f"(${summary.committed_all_in:,.2f} all-in w/ {round(ABSENTEE_FEE * 100)}% fee)",
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
