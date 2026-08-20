#!/usr/bin/env python3
"""
scripts/run_aug22_cycle.py — August 22, 2026 Sourcing Run (Refined Owner Directives).

Final fine-tuning based on multimodal inspection:
- Costume Jewelry: KEEP (50-70 pieces per tray, $15-$20 defensive bids for 5x gross)
- Handheld Games (BT-066): REDUCED to $15.00 (5 units: Radica/LCD mix, not vintage Mattel)
- Vintage Topps Cards (BT-001, BT-284): HIGH PRIORITY ($71.72 max for 13 Golden Era 1959-1969 cards)
- Edison Cylinders (BT-041): HIGH PRIORITY ($50.00 max for 11-12 canisters + 1 exposed roll)
- Tonka Trucks/Crane: DEFENSIVE LOWBALL ($25.00 max)
- Advertising / Bottles (Coca-Cola): KEEP ($18.56 max)
- Princess Phone & ET Nightlight: KEEP ($18.56 max)
- Tools (Toolbox, Wrenches): SKIPPED (store backlog)
- Beer Pitchers & Bears Glasses: SKIPPED
- Bobbleheads & Games: SKIPPED
- Dishes & Uncertified Autographs: SKIPPED
- Credit Card Hard Budget Cap: $600 - $800 total
"""

import json
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from src.intake.manifest import parse_drop, group_into_lots, TriagedPhoto
from src.bidmath import (
    Lot, CompEstimate, Confidence,
    price_lot, allocate, summarize
)

# Targeted catalog taxonomy aligned with refined owner directives
AUG22_CATALOG_TAXONOMY = [
    # Golden Era Cards & Core Showpieces
    (["topps", "baseball cards"], (250, 500), "vintage cards", 0.95),
    (["edison"], (100, 160), "phonograph / records", 0.95),

    # Fast-Turning Smalls & Gold Mining Box Lots
    (["costume jewelry"], (80, 160), "jewelry", 0.85),
    (["estate costume jewelry"], (80, 160), "jewelry", 0.85),
    (["coca-cola bottles"], (40, 100), "advertising / bottles", 0.85),
    (["coca-cola collectibles"], (40, 100), "advertising / bottles", 0.80),
    (["century progress bottle"], (30, 80), "advertising / bottles", 0.80),
    (["princess phone"], (40, 100), "vintage electronics", 0.80),
    (["et nightlight"], (40, 100), "vintage smalls", 0.80),
    (["marilyn monroe plates"], (40, 120), "collectibles", 0.75),
    (["lionel building set"], (50, 120), "vintage toys", 0.75),

    # Defensive Lowball Allocations
    (["tonka"], (50, 120), "vintage toys", 0.70),
    (["hand held video games"], (25, 45), "vintage toys / electronics", 0.65),

    # Trading Cards
    (["trading cards"], (30, 80), "vintage cards", 0.65),
    (["vintage baseball cards"], (40, 100), "vintage cards", 0.70),

    # Explicit Exclusions / Skips by Owner Directive
    (["toolbox"], (0, 0), "tools / skip backlog", 0.0),
    (["wrenches"], (0, 0), "tools / skip backlog", 0.0),
    (["beer pitchers"], (0, 0), "barware / skip", 0.0),
    (["chicago bears glasses"], (0, 0), "barware / skip", 0.0),
    (["bobble heads"], (0, 0), "collectibles / skip", 0.0),
    (["board games"], (0, 0), "games / skip", 0.0),
    (["mahjong"], (0, 0), "games / skip", 0.0),
    (["poppy trail"], (0, 0), "dishes / skip", 0.0),
    (["jordan"], (0, 0), "uncertified autographs / skip", 0.0),
    (["dimaggio"], (0, 0), "uncertified autographs / skip", 0.0),
    (["manning"], (0, 0), "uncertified autographs / skip", 0.0),
    (["marino"], (0, 0), "uncertified autographs / skip", 0.0),
    (["reggie bush"], (0, 0), "uncertified autographs / skip", 0.0),
    (["rusty wallace"], (0, 0), "uncertified autographs / skip", 0.0),
    (["signed sports photos"], (0, 0), "uncertified autographs / skip", 0.0),
    (["hp printer"], (0, 0), "modern tech / skip", 0.0),
    (["battery chargers"], (0, 0), "modern tech / skip", 0.0),
    (["hardware"], (0, 0), "general hardware / skip", 0.0),
]

def evaluate_catalog_comp(desc: str) -> tuple[CompEstimate | None, str, float]:
    d = (desc or "").lower()
    for keys, (lo, hi), cat, fit in AUG22_CATALOG_TAXONOMY:
        if all(k in d for k in keys):
            if fit <= 0.20 or lo == 0:
                return None, cat, fit
            return CompEstimate(low=float(lo), high=float(hi), source_count=3, confidence=Confidence.HIGH), cat, fit
    return None, "general estate", 0.20

def main():
    manifest_path = Path("data/aug22_gallery_4160518/manifest.json")
    print(f"[*] Loading August 22 manifest from {manifest_path}...")
    manifest = json.loads(manifest_path.read_text())
    photos = manifest["photos"]
    print(f"[+] Loaded {len(photos)} photos.")

    triaged = []
    for i, p in enumerate(photos):
        cap = p["caption"].lower()
        has_cap = bool(cap.strip())
        is_extra_angle = (not has_cap and i > 0 and photos[i-1]["has_caption"])
        triaged.append(TriagedPhoto(
            photo_id=p["photo_id"],
            caption=p["caption"],
            is_lot=not is_extra_angle,
            same_lot_as_previous=is_extra_angle,
        ))

    lot_groups = group_into_lots(triaged)

    lots = []
    for g in lot_groups:
        primary_photo = next(p for p in photos if p["photo_id"] == g.primary_photo_id)
        caption = primary_photo["caption"]

        comp, cat, fit = evaluate_catalog_comp(caption)
        lots.append(Lot(
            lot_id=f"BT-{primary_photo['sequence']:03d}",
            caption=caption or f"Uncaptioned lot (Photo #{primary_photo['sequence']})",
            category=cat,
            fit_score=fit,
            condition_penalty=0.10,
            comp=comp or CompEstimate(low=0.0, high=0.0, source_count=0, confidence=Confidence.NONE),
        ))

    # Refined Owner Budget Cap: $600 credit card envelope
    budget_cap = 600.00
    auto_send_thresh = 35.00
    decisions = [price_lot(l) for l in lots]
    decisions = allocate(decisions, budget_cap=budget_cap, auto_send_threshold=auto_send_thresh)
    s = summarize(decisions)

    print("\n" + "=" * 75)
    print("BLUE TOAD FLEET — FINAL REFINED AUGUST 22 BID SHEET")
    print("=" * 75)
    print(f"Total Raw Photos:             {len(photos)}")
    print(f"Consolidated Physical Lots:   {len(lot_groups)}")
    print(f"Bids Allocated:               {s.allocated} targeted lots")
    print(f"  • Auto-Send (<= $35):       {s.auto_send} lots  (Costume jewelry bins, bottles, phone, nightlight)")
    print(f"  • Operator Sign-Off:        {s.needs_approval} lots  (Edison rolls, 1959-69 Topps baseball cards)")
    print(f"Skipped on Directive:         {s.skipped} lots  (Tools, beer glassware, dishes, autographs)")
    print(f"Committed Max Bids:           ${s.committed_max:,.2f}")
    print(f"Committed All-In (w/ 15% fee):${s.committed_all_in:,.2f} of ${budget_cap:,.2f} budget cap")
    print("=" * 75)

    print("\n[★] Final Allocated Bids for August 22:")
    allocated_decisions = [d for d in decisions if d.allocated]
    for d in allocated_decisions:
        lot_obj = next(l for l in lots if l.lot_id == d.lot_id)
        tag = "[AUTO-SEND]" if d.auto_send else "[NEEDS APPROVAL]"
        print(f"  {d.lot_id} | {tag:<16} | {lot_obj.caption:<38} | Est: ${lot_obj.comp.low:.0f}-${lot_obj.comp.high:.0f} | Max Bid: ${d.max_bid:.2f} (All-in: ${d.all_in:.2f})")

    # Generate Final Sealed Absentee Bid Email Draft
    email_draft_path = Path("data/aug22_absentee_bid_email.txt")
    email_lines = [
        "TO: info@bluetoadauctions.com",
        "SUBJECT: Absentee Bids - August 22 Antique & Estate Auction (Bidder: Richmond General)",
        "DATE: Friday, August 21, 2026 (Before 8:00 PM CDT Cutoff)",
        "",
        "Blue Toad Auctions,",
        "",
        "Please register the following absentee proxy bids for the Saturday, August 22, 2026 auction",
        "at 200 Elizabeth Lane, Genoa City, WI.",
        "",
        "Bidder Info:",
        "  Name: Richmond General (Scott)",
        "  Resale Certificate: On file (Wisconsin Tax-Exempt)",
        "  Terms: 15% Absentee Buyer Fee acknowledged (Credit Card on File)",
        "",
        "-----------------------------------------------------------------------------------------",
        "ITEM DESCRIPTION                                     PHOTO REF     START ($)  MAX BID ($)",
        "-----------------------------------------------------------------------------------------",
    ]

    for d in allocated_decisions:
        lot_obj = next(l for l in lots if l.lot_id == d.lot_id)
        start_bid = max(10.0, round(d.max_bid * 0.40 / 5.0) * 5.0)
        email_lines.append(f"{lot_obj.caption[:48]:<50} {d.lot_id:<12} ${start_bid:>8.2f} ${d.max_bid:>9.2f}")

    email_lines.extend([
        "-----------------------------------------------------------------------------------------",
        f"TOTAL COMMITTED PROXY BIDS: ${s.committed_max:,.2f} (${s.committed_all_in:,.2f} all-in w/ 15% fee)",
        "",
        "Special Instructions:",
        "  - For 'Buyer's Choice / Times the Money' shelf lots, max quantity is 1 unit only.",
        "  - Please confirm receipt of these absentee bids by reply email.",
        "",
        "Thank you,",
        "Richmond General",
    ])
    email_draft_path.write_text("\n".join(email_lines))
    print(f"\n[✓] Generated Final Sealed Absentee Bid Email: {email_draft_path}")

    # Generate Excel Sourcing Sheet
    out_excel = Path("data/BlueToad_2026-08-22_BidSheet.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Aug 22 Bid Sheet"

    hdr_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    hdr_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

    headers = ["Lot ID", "Priority", "Category", "Description", "Est Low ($)", "Est High ($)", "Max Bid ($)", "All-In ($)", "Status", "Reason"]
    ws.append(headers)
    for c in range(1, 11):
        ws.cell(1, c).fill = hdr_fill
        ws.cell(1, c).font = hdr_font

    for idx, (lot, d) in enumerate(zip(lots, decisions), 2):
        if d.allocated:
            status = "AUTO-SEND" if d.auto_send else "NEEDS APPROVAL"
            fill = green_fill if d.auto_send else yellow_fill
        else:
            status = "SKIPPED"
            fill = None

        ws.append([
            d.lot_id,
            d.priority.value,
            lot.category,
            lot.caption,
            lot.comp.low if lot.comp.source_count > 0 else "-",
            lot.comp.high if lot.comp.source_count > 0 else "-",
            d.max_bid or "-",
            d.all_in or "-",
            status,
            d.reason,
        ])
        if fill:
            ws.cell(idx, 9).fill = fill

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    wb.save(out_excel)
    print(f"[✓] Saved updated Excel Bid Sheet: {out_excel}")

if __name__ == "__main__":
    main()
