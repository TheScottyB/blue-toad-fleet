#!/usr/bin/env python3
"""
Credential-free demo of the Blue Toad decision pipeline.

Runs the real bid math over a seeded set of appraised lots using stub
adapters, so a judge (or anyone) can see the full decision path without a
GCP project, an OAuth consent screen, or a single API key.

    make demo

In production the seeded lots come from the Appraiser (Gemini 3.5 multimodal
over the gallery drop) and the comps from the Comps agent. Everything
downstream of that point is exactly this code.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.bidmath import (  # noqa: E402
    CompEstimate, Confidence, Lot, Priority, allocate, price_lot, summarize,
)

SEED = pathlib.Path(__file__).parent / "seed" / "lots.json"
BUDGET_CAP = 2205.00        # last cycle's actual all-in commitment
AUTO_SEND_THRESHOLD = 40.00  # lots at or under $40 all-in go without approval
CALIBRATION = {}             # empty: cycle 1 of the ledger, no hammer data yet

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"
GREEN, YELLOW, RED, CYAN = "\033[32m", "\033[33m", "\033[31m", "\033[36m"


def load_lots() -> list[Lot]:
    out = []
    for r in json.loads(SEED.read_text()):
        c = r["comp"]
        out.append(Lot(
            lot_id=r["lot_id"], caption=r["caption"], category=r["category"],
            fit_score=r["fit_score"], condition_penalty=r["condition_penalty"],
            comp=CompEstimate(low=c["low"], high=c["high"],
                              source_count=c["source_count"],
                              confidence=Confidence(c["confidence"])),
        ))
    return out


def card(lot: Lot, d) -> str:
    colour = {Priority.A: GREEN, Priority.B: CYAN,
              Priority.C: YELLOW, Priority.SKIP: DIM}[d.priority]
    lines = [
        f"{BOLD}{d.lot_id}{RESET}  {colour}[{d.priority.value}]{RESET}  {DIM}{lot.category}{RESET}",
        f"  {lot.caption}",
    ]
    if d.needs_human_pricing:
        lines.append(f"  {RED}NO EXTERNAL COMP — human pricing required{RESET}")
    elif d.max_bid is None:
        lines.append(f"  {DIM}{d.reason}{RESET}")
    else:
        flag = ""
        if d.allocated and d.auto_send:
            flag = f"  {GREEN}AUTO-SEND{RESET}"
        elif d.allocated:
            flag = f"  {YELLOW}NEEDS APPROVAL{RESET}"
        else:
            flag = f"  {DIM}not allocated{RESET}"
        lines.append(
            f"  est ${lot.comp.low:.0f}-${lot.comp.high:.0f}"
            f"  ->  max {BOLD}${d.max_bid:.2f}{RESET}"
            f"  all-in {BOLD}${d.all_in:.2f}{RESET}{flag}"
        )
        lines.append(f"  {DIM}{d.reason}{RESET}")
    return "\n".join(lines)


def main() -> int:
    lots = load_lots()
    decisions = [price_lot(l, CALIBRATION) for l in lots]
    decisions = allocate(decisions, BUDGET_CAP, AUTO_SEND_THRESHOLD)
    by_id = {d.lot_id: d for d in decisions}

    print(f"\n{BOLD}BLUE TOAD FLEET — cycle demo{RESET}")
    print(f"{DIM}{len(lots)} appraised lots  ·  budget cap ${BUDGET_CAP:,.2f}"
          f"  ·  auto-send at or under ${AUTO_SEND_THRESHOLD:.2f}{RESET}\n")

    for lot in lots:
        print(card(lot, by_id[lot.lot_id]))
        print()

    s = summarize(decisions)
    print(f"{BOLD}SHEET{RESET}")
    print(f"  lots appraised        {s.total_lots}")
    print(f"  bids allocated        {s.allocated}   "
          f"({GREEN}{s.auto_send} auto-send{RESET}, "
          f"{YELLOW}{s.needs_approval} need approval{RESET})")
    print(f"  human pricing needed  {s.needs_human_pricing}")
    print(f"  skipped on fit        {s.skipped}")
    print(f"  committed max         ${s.committed_max:,.2f}")
    print(f"  committed all-in      ${s.committed_all_in:,.2f} "
          f"{DIM}of ${BUDGET_CAP:,.2f} cap{RESET}")
    print(f"  by priority           {dict(sorted(s.by_priority.items()))}\n")
    print(f"{DIM}Next in production: Gate console renders these cards, the human trims,")
    print(f"approved bids become a Gmail draft in Blue Toad's absentee format.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
