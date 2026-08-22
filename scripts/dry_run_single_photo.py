#!/usr/bin/env python3
"""
scripts/dry_run_single_photo.py — put ONE gallery photo through the whole chain.

The corpus runner answers "what should the sheet say". This answers a different
question: "what does the system actually do to one photograph, at every stage,
right now, against the live models". It exists because a 462-photo run hides the
individual decision — you see 228 appraisals and a sheet, not the moment triage
decided a lot was not worth a slow look.

Nothing is sent. Nothing under the cycle's data dir is overwritten; artifacts go
to a separate --out directory.

Source of truth is the live listing. AuctionZip sits behind CloudFront + AWS WAF:
the first few requests return 200, then it answers 202 with
`x-amzn-waf-action: challenge` — a JS challenge only a real browser can solve.
That is NOT a 403 and NOT permanent. When it trips, this falls back to the cached
drop and SAYS SO in the log and in the report, because "where did these bytes come
from" is exactly the question a dry run exists to answer honestly.

    python scripts/dry_run_single_photo.py --seq 183
    python scripts/dry_run_single_photo.py --seq 001 --force-appraise
    python scripts/dry_run_single_photo.py --seq 050 --no-pricing
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cache_gallery import _PHOTO_PATTERN, _atomic_write
from scripts.run_vertex_pipeline import DEFAULT_STANDING_RULES, REFERENCE_COMPS
from src.appraisal import build_queue
from src.appraiser import AppraisalEngine
from src.appraiser.images import assert_appraisal_grade, image_dimensions
from src.appraiser.pricing import (MIN_CALLS, median_price, price_is_usable,
                                   usable_sources)
from src.appraiser.routing import (APPRAISAL_MODEL, TRIAGE_MODEL,
                                   estimate_cost_usd)
from src.bidmath import (CompEstimate, Confidence as BidConfidence, Lot,
                         allocate, opening_bid, price_lot, summarize)
from src.intake.manifest import (TriagedPhoto, clean_caption, group_into_lots,
                                 lot_number_from)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")


class WafChallenge(RuntimeError):
    """AuctionZip's WAF asked for a browser. Distinct from a network error, and
    distinct from a 403 — an earlier note recorded this as 'always 403' without
    reading the response, and that one wrong word became a standing gate."""


def bar(n, title):
    print(f"\n{'=' * 78}\n[STAGE {n}] {title}\n{'=' * 78}")


def fetch(url, referer="https://www.auctionzip.com/", timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        if resp.headers.get("x-amzn-waf-action") == "challenge" or resp.status == 202:
            raise WafChallenge(f"WAF challenge on {url} (HTTP {resp.status})")
        return body


def panel_url(listing):
    return (f"https://www.auctionzip.com/cgi-bin/photopanel.cgi?listingid={listing}"
            f"&feed=129&gid=0&category=0&zip=&kwd=&PageImages=0")


def frame_url(listing, seq):
    return f"https://www.auctionzip.com/Full-Image/{listing}/fpx{seq}.cgi"


def row_for_sequence(panel_html, seq):
    """
    (photo_id, caption) for one sequence in the photopanel markup.

    Index by the `DisplayFullImage(listing, N, feed)` argument, never by position
    in the list of `_th` matches — the two disagree, and indexing by position put
    us two photos off the one we were asked about.
    """
    for _listing, n, _feed, src, caption in _PHOTO_PATTERN.findall(panel_html):
        if int(n) != int(seq):
            continue
        m = re.search(r"/(\d+)(?:_th|_fl)?$", src)
        return (m.group(1) if m else None), clean_caption(caption)
    return None, None


def estatesales_image(seq, data_dir):
    """
    (bytes, url) for the estatesales copy of an AuctionZip sequence, or None.

    Blue Toad cross-lists the same sale on estatesales.net at 1200x900 JPEG —
    five times the pixels of AuctionZip's 560x420, and no WAF. It publishes only
    a subset (171 of 462) with no captions, so this is a source for PIXELS only;
    the caption still comes from AuctionZip. `estatesales_link.json` carries the
    correspondence, established by perceptual hash: order-preserving, but not
    contiguous, so the sequence cannot be computed by an offset.
    """
    link_path = Path(data_dir) / "estatesales_link.json"
    if not link_path.is_file():
        return None
    links = json.loads(link_path.read_text())["links"]
    row = next((r for r in links if r["az_sequence"] == int(seq)), None)
    if row is None:
        return None

    cache = Path(data_dir) / "estatesales_images" / f"order{row['es_order']:03d}.jpg"
    if cache.is_file() and cache.stat().st_size > 0:
        return cache.read_bytes(), row["es_url"]
    req = urllib.request.Request(row["es_url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    assert_appraisal_grade(data, lot_id=f"DRY-RUN-{seq}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(cache, data)
    return data, row["es_url"]


def resolve_photo(listing, seq, data_dir, offline=False, source="auctionzip"):
    """Caption and full-size bytes for one photo, live if the WAF allows it."""
    panel_src = img_src = "CACHED (offline requested)"
    panel_html = None

    if not offline:
        try:
            panel_html = fetch(panel_url(listing)).decode("utf-8", "ignore")
            panel_src = "LIVE"
        except WafChallenge as e:
            print(f"[!] {e}")
        except Exception as e:
            print(f"[!] photopanel fetch failed: {e}")

    manifest_path = Path(data_dir) / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        manifest = {p["sequence"]: p
                    for p in json.loads(manifest_path.read_text())["photos"]}

    if panel_html:
        photo_id, caption = row_for_sequence(panel_html, seq)
        total = len(_PHOTO_PATTERN.findall(panel_html))
    else:
        entry = manifest.get(int(seq))
        if not entry:
            raise SystemExit(f"[FATAL] seq {seq} is in neither the live panel nor {manifest_path}")
        photo_id, caption, total = entry["photo_id"], entry["caption"], len(manifest)
        panel_src = "CACHED manifest.json (live panel unavailable)"

    if photo_id is None:
        raise SystemExit(f"[FATAL] seq {seq} not present in the live photopanel")

    img = None
    img_url = f"https://www.auctionzip.com/Full-Image/{listing}/fi{seq}.cgi"

    if source == "estatesales":
        got = estatesales_image(seq, data_dir)
        if got is None:
            raise SystemExit(
                f"[FATAL] seq {seq} has no estatesales counterpart — it is one of the "
                f"291 photos AuctionZip carries and estatesales does not. "
                f"Re-run with --source auctionzip.")
        img, img_url = got
        img_src = "ESTATESALES 1200x900 JPEG (pixels), caption from AuctionZip"
        return _photo_result(photo_id, caption, img, img_url, panel_src, img_src,
                             total, manifest, seq)

    if not offline:
        try:
            frame = fetch(frame_url(listing, seq)).decode("utf-8", "ignore")
            m = re.search(r"""iframe[^>]*src=['"]([^'"]+)['"]""", frame)
            if m:
                path = m.group(1)
                img_url = "https:" + path if path.startswith("//") else path
            img = fetch(img_url, referer=frame_url(listing, seq))
            img_src = "LIVE"
        except WafChallenge as e:
            print(f"[!] {e}")
        except Exception as e:
            print(f"[!] image fetch failed: {e}")

    cached_path = None
    entry = manifest.get(int(seq))
    if entry:
        cached_path = ROOT / entry["local_path"]
    if img is None:
        if not (cached_path and cached_path.is_file()):
            raise SystemExit(f"[FATAL] no live bytes and no cached image for seq {seq}")
        img = cached_path.read_bytes()
        img_src = f"CACHED {cached_path.name} (live image unavailable)"

    return _photo_result(photo_id, caption, img, img_url, panel_src, img_src,
                         total, manifest, seq)


def _photo_result(photo_id, caption, img, img_url, panel_src, img_src, total,
                  manifest, seq):
    entry = manifest.get(int(seq)) if manifest else None
    cached_path = ROOT / entry["local_path"] if entry else None
    return {
        "photo_id": photo_id, "caption": caption, "image": img,
        "image_url": img_url, "panel_source": panel_src, "image_source": img_src,
        "panel_total": total, "cached_path": cached_path,
    }


def run(listing, seq, data_dir, out_dir, force_appraise=False,
        do_pricing=True, offline=False, budget_cap=1000.0, auto_send_threshold=0.0,
        source="auctionzip", standing_rules=None):
    """
    `standing_rules` defaults to the corpus runner's DEFAULT_STANDING_RULES, and
    that default is load-bearing rather than cosmetic. Passing an empty list —
    which this script originally did — drops fit_score on a bulk costume jewelry
    tray from 0.85 to 0.2 and flips the bidmath gate from BID to SKIP, because
    the rule "BUY - bulk estate costume jewelry moves in the storefront" is what
    tells the model the shop wants a category its own fit heuristic scores at 0.1.
    A dry run without the operator's standing rules is not a dry run of this
    system; it is a dry run of a system that has forgotten every decision he made.
    """
    if standing_rules is None:
        standing_rules = DEFAULT_STANDING_RULES
    lot_id = f"BT-{int(seq):03d}"
    report = {
        "source_url": frame_url(listing, seq), "listing_id": listing,
        "sequence": int(seq), "lot_id": lot_id, "mode": "DRY RUN — nothing sent",
        "waf_note": ("CloudFront + AWS WAF: 202 x-amzn-waf-action=challenge after a "
                     "short burst. Not a 403, not permanent."),
    }

    # ------------------------------------------------------------ 0. fetch
    bar(0, "FETCH — live listing, cached fallback, provenance recorded")
    t0 = time.time()
    got = resolve_photo(listing, seq, data_dir, offline=offline, source=source)
    img, caption = got["image"], got["caption"]
    dims = image_dimensions(img)
    print(f"[*] photopanel      {got['panel_source']}  ({got['panel_total']} photos)")
    print(f"[*] image           {got['image_source']}")
    print(f"[+] seq {seq}         photo_id={got['photo_id']}  "
          f"caption={caption!r} ({'captioned' if caption else 'UNCAPTIONED'})")
    print(f"[+] bytes           {len(img):,}  {dims}  in {time.time() - t0:.1f}s")
    if got["cached_path"] and got["cached_path"].is_file() and got["image_source"] == "LIVE":
        same = got["cached_path"].read_bytes() == img
        print(f"[{'✓' if same else '!'}] vs cache        "
              f"{'byte-identical' if same else 'DIFFERS FROM CACHE'}")
        report["matches_cached_bytes"] = same
    report.update({k: v for k, v in got.items() if k not in ("image", "cached_path")},
                  image_bytes=len(img), dimensions=list(dims) if dims else None)

    # ------------------------------------------------------ 1. image guard
    bar(1, "IMAGE GUARD — assert_appraisal_grade")
    try:
        assert_appraisal_grade(img, lot_id=lot_id)
    except Exception as e:
        report["image_guard"] = f"refused: {e}"
        _write(out_dir, seq, report, None, None)
        raise SystemExit(f"[FATAL] {e}")
    print(f"[✓] PASS  {dims} short edge >= 300px — appraisal grade")
    report["image_guard"] = "pass"

    engine = AppraisalEngine()
    if engine.client is None:
        raise SystemExit("[FATAL] no Vertex client — cannot run live")
    print(f"[✓] Vertex  project={engine.project} location={engine.location}")

    # ----------------------------------------------------------- 2. triage
    bar(2, f"STAGE 1 TRIAGE — {TRIAGE_MODEL} (LIVE)")
    t = time.time()
    verdict = engine.triage_photo(photo_id=got["photo_id"], caption=caption,
                                  image_bytes=img, previous_summary=None)
    print(f"[✓] {time.time() - t:.1f}s  model={verdict.get('model_used')}")
    print(json.dumps({k: v for k, v in verdict.items() if k != "photo_id"}, indent=2))
    report["triage"] = verdict

    # --------------------------------------------------------- 3. grouping
    bar(3, "GROUPING — group_into_lots")
    tp = TriagedPhoto(photo_id=got["photo_id"], caption=caption,
                      is_lot=bool(verdict.get("is_lot", True)),
                      same_lot_as_previous=bool(verdict.get("same_lot_as_previous", False)))
    groups = group_into_lots([tp])
    print(f"[i] caption lot number : {lot_number_from(caption)!r}")
    print(f"[i] is_lot={tp.is_lot}  same_lot_as_previous={tp.same_lot_as_previous}")
    print("[!] single-photo run: `same_lot_as_previous` has NO previous to attach to.")
    print(f"    In the full corpus this photo may merge into seq {int(seq) - 1}'s group,")
    print("    so a lot here is not proof of a lot there.")
    print(f"[✓] {len(groups)} lot group(s): {[(g.lot_key, g.photo_ids) for g in groups]}")
    report["grouping"] = {
        "groups": [{"lot_key": g.lot_key, "photo_ids": list(g.photo_ids)} for g in groups],
        "caveat": "same_lot_as_previous cannot be evaluated on an isolated photo",
    }
    if not groups:
        print("\n[STOP] Triage says this is not a lot. The corpus run drops it here.")
        return _write(out_dir, seq, report, None, "not a lot")

    # ------------------------------- 3b. triage note (not a coverage gate)
    worth = bool(verdict.get("worth_appraising", True))
    if not worth:
        print("\n[!] triage says worth_appraising=false; continuing — it is not a coverage gate.")
        report["worth_appraising"] = False

    # -------------------------------------------------------- 4. appraisal
    bar(4, f"STAGE 2 APPRAISAL — {APPRAISAL_MODEL} (LIVE)")
    t = time.time()
    cat_hint = REFERENCE_COMPS.get(lot_id, {}).get("cat") or verdict.get("category")
    print(f"[i] category_hint={cat_hint!r}  standing_rules={len(standing_rules)}")
    raw = engine.appraise_lot(lot_id=lot_id, caption=caption, image_bytes=img,
                              category_hint=cat_hint, standing_rules=standing_rules)
    print(f"[✓] {time.time() - t:.1f}s  model={raw.get('model_used')}")
    print(json.dumps(raw, indent=2))
    _appraisal, questions = AppraisalEngine.parse_appraisal_to_domain(raw)
    report["appraisal"] = raw
    identification = raw.get("identification", "")
    category = raw.get("category", "other")
    fit = float(raw.get("fit_score", 0.5))
    penalty = float(raw.get("condition_penalty", 0.0))

    # ---------------------------------------------------------- 5. pricing
    comp = CompEstimate(low=None, high=None, source_count=0,
                        confidence=BidConfidence.NONE)
    if do_pricing:
        bar(5, f"GROUNDED PRICING — {MIN_CALLS} independent search-grounded calls (LIVE)")
        prices = []
        for i in range(MIN_CALLS):
            t = time.time()
            try:
                gp = engine.price_lot_grounded(identification, category)
            except Exception as e:
                gp = None
                print(f"  call {i + 1}: ERROR {e}")
            if gp:
                print(f"  call {i + 1}: ${gp.low:.2f}-${gp.high:.2f}  "
                      f"comps={gp.sold_comp_count}  sources={len(usable_sources(gp.sources))}  "
                      f"({time.time() - t:.1f}s)")
            elif gp is None:
                print(f"  call {i + 1}: no price returned ({time.time() - t:.1f}s)")
            prices.append(gp)

        usable, merged = price_is_usable(prices), median_price(prices)
        print(f"\n[{'✓' if usable else '!'}] price_is_usable = {usable}")
        if merged:
            print(f"[i] median ${merged.low:.2f}-${merged.high:.2f}  "
                  f"comps={merged.sold_comp_count}  {len(merged.sources)} citation(s)")
        if not usable:
            print("[i] REFUSED -> lot goes to the operator unpriced. Designed outcome.")
        report["pricing"] = {
            "usable": usable,
            "calls": [None if p is None else {
                "low": p.low, "high": p.high, "sold_comp_count": p.sold_comp_count,
                "sources": usable_sources(p.sources)} for p in prices],
            "median": None if not merged else {
                "low": merged.low, "high": merged.high,
                "sold_comp_count": merged.sold_comp_count, "sources": merged.sources},
        }
        if usable and merged:
            comp = CompEstimate(low=merged.low, high=merged.high,
                                source_count=len(merged.sources),
                                confidence=BidConfidence.MEDIUM)
    else:
        bar(5, "GROUNDED PRICING — SKIPPED (--no-pricing)")
        print("[i] no comp -> bidmath will route this to human pricing.")
        report["pricing"] = {"skipped": True}

    # ------------------------------------------------------------ 6. queue
    bar(6, "QUESTION QUEUE — build_queue")
    qres = build_queue(questions, standing_rules=standing_rules)
    print(f"[✓] asked={len(qres.asked)} auto_answered={len(qres.auto_answered)} "
          f"deferred={len(qres.deferred)} dropped={len(qres.dropped)}")
    for q in qres.asked:
        print(f"  ASK    [{q.kind.value}] {q.prompt}")
    for q in qres.deferred:
        print(f"  DEFER  [{q.kind.value}] {q.prompt}")
    report["queue"] = {
        "asked": [{"kind": q.kind.value, "prompt": q.prompt} for q in qres.asked],
        "deferred": [{"kind": q.kind.value, "prompt": q.prompt} for q in qres.deferred],
        "dropped": len(qres.dropped),
    }

    # ---------------------------------------------------------- 7. bidmath
    bar(7, "BIDMATH — price_lot -> allocate -> summarize")
    lot = Lot(lot_id=lot_id, caption=caption or identification, category=category,
              fit_score=fit, condition_penalty=penalty, comp=comp)
    d = allocate([price_lot(lot)], budget_cap=budget_cap,
                 auto_send_threshold=auto_send_threshold)[0]
    summary = summarize([d])
    print(f"[i] priority            {d.priority.value}")
    print(f"[i] max_bid             {'—' if d.max_bid is None else f'${d.max_bid:.2f}'}")
    print(f"[i] all_in (15% fee)    {'—' if d.all_in is None else f'${d.all_in:.2f}'}")
    print(f"[i] needs_human_pricing {d.needs_human_pricing}")
    print(f"[i] allocated           {d.allocated}   auto_send={d.auto_send}")
    print(f"[i] reason              {d.reason}")
    report["source_kind"] = source
    report["decision"] = {k: (v.value if hasattr(v, "value") else v)
                          for k, v in d.__dict__.items()}
    report["summary"] = summary.__dict__
    report["model_cost_estimate_usd"] = estimate_cost_usd(1, 1)
    return _write(out_dir, seq, report, d, identification)


def _write(out_dir, seq, report, decision, identification):
    bar(8, "ARTIFACTS — disk only, nothing sent")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jf = out / f"dryrun_seq{int(seq):03d}.json"
    jf.write_text(json.dumps(report, indent=2))
    print(f"[✓] {jf}")

    if decision is not None and decision.allocated and decision.max_bid:
        start = opening_bid(decision.max_bid)
        body = (
            f"DRY RUN — NOT SENT\n"
            f"TO: info@bluetoadauctions.com\n\n"
            f"Hi Bill,\n\nOne lot for Saturday:\n\n"
            f"1. Photo #{int(seq)} — {identification}\n"
            f"   start ${start:.0f} / max ${decision.max_bid:.0f}\n\n"
            f"All-in with the 15% absentee fee: ${decision.all_in:.2f}. Our WI\n"
            f"resale/sales-tax exemption certificate is on file with you.\n\n"
            f"We'll pick up over the weekend as usual.\n\n"
            f"Thanks,\nScott — Richmond General\n")
    else:
        reason = (decision.reason if decision is not None else identification) or "stopped upstream"
        body = (f"DRY RUN — NOT SENT — NO BID DRAFTED\n\n"
                f"Photo #{int(seq)} produced no bid.\nReason: {reason}\n\n"
                f"The chain ran and declined to name a number.\n")
    ef = out / f"dryrun_seq{int(seq):03d}_email.txt"
    ef.write_text(body)
    print(f"[✓] {ef}\n")
    print(body)
    print("=" * 78)
    print("DRY RUN COMPLETE — nothing sent, no cycle data file written.")
    print("=" * 78)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listing", default="4160518", help="AuctionZip listing id")
    ap.add_argument("--seq", type=int, default=183, help="photo sequence within the listing")
    ap.add_argument("--data-dir", default="data/aug22_gallery_4160518",
                    help="cached drop, used for fallback and byte comparison")
    ap.add_argument("--out", default="data/dryruns", help="where artifacts are written")
    ap.add_argument("--force-appraise", action="store_true",
                    help="deprecated no-op: worth_appraising no longer stops the dry run")
    ap.add_argument("--no-pricing", action="store_true",
                    help="skip the grounded pricing calls (they are the expensive part)")
    ap.add_argument("--source", choices=["auctionzip", "estatesales"], default="auctionzip",
                    help="where the PIXELS come from. estatesales is 1200x900 JPEG "
                         "(5x the pixels, no WAF) but covers only 171 of 462 photos; "
                         "the caption always comes from AuctionZip either way")
    ap.add_argument("--offline", action="store_true",
                    help="do not touch AuctionZip; use the cached drop only")
    ap.add_argument("--no-standing-rules", action="store_true",
                    help="appraise with NO operator standing rules. Diagnostic only: "
                         "it changes the verdict (jewelry fit 0.85 -> 0.2), it is not "
                         "what a live cycle does")
    ap.add_argument("--budget-cap", type=float, default=1000.0)
    args = ap.parse_args()

    run(listing=args.listing, seq=args.seq, data_dir=args.data_dir, out_dir=args.out,
        force_appraise=args.force_appraise, do_pricing=not args.no_pricing,
        offline=args.offline, budget_cap=args.budget_cap, source=args.source,
        standing_rules=[] if args.no_standing_rules else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
