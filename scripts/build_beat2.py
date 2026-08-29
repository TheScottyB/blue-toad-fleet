#!/usr/bin/env python3
"""Build the facts-driven Beat 2 intake/grouping animation page."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run_vertex_pipeline import trusted_lot_flags
from video_common import (
    VideoBuildError,
    atomic_write_text,
    display_path,
    load_json_object,
    load_verified_facts,
    project_path,
    require_file,
    require_keys,
)


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _real_pairs(gallery: dict, triage: list, limit: int) -> list[dict]:
    photos = gallery.get("photos")
    if not isinstance(photos, list) or not photos:
        raise VideoBuildError("gallery manifest has no photos")
    verdicts = {
        item.get("photo_id"): item
        for item in triage
        if isinstance(item, dict) and item.get("photo_id")
    }
    pairs: list[dict] = []
    for index, photo in enumerate(photos):
        verdict = verdicts.get(photo.get("photo_id"))
        _, same = trusted_lot_flags(
            verdict,
            str(photo.get("caption") or ""),
            bool(index and photos[index - 1].get("has_caption")),
            index,
        )
        if not same or index == 0:
            continue
        previous = photos[index - 1]
        first = require_file(previous["local_path"], "Beat 2 pair image")
        second = require_file(photo["local_path"], "Beat 2 pair image")
        pairs.append(
            {
                "first": first,
                "second": second,
                "first_sequence": int(previous["sequence"]),
                "second_sequence": int(photo["sequence"]),
                "caption": previous.get("caption") or (verdict or {}).get("summary") or "Grouped lot",
            }
        )
        if len(pairs) == limit:
            break
    if not pairs:
        raise VideoBuildError("triage results contain no real same-lot pair examples")
    return pairs


def build(video_manifest_value: str, output_value: str | None, pair_limit: int) -> Path:
    video_manifest = load_json_object(video_manifest_value, "video manifest")
    require_keys(video_manifest, ["sources", "recordings", "facts"], "video manifest")
    facts = load_verified_facts(video_manifest)
    gallery = load_json_object(
        video_manifest["sources"]["gallery_manifest"], "gallery manifest"
    )
    triage_path = require_file(video_manifest["sources"]["triage_results"], "triage results")
    try:
        triage = json.loads(triage_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VideoBuildError(f"invalid triage results: {exc}") from exc
    if not isinstance(triage, list):
        raise VideoBuildError("triage results must be a list")
    if pair_limit <= 0:
        raise VideoBuildError("pair limit must be positive")
    pairs = _real_pairs(gallery, triage, pair_limit)

    cycle = facts["cycle"]
    require_keys(
        cycle,
        [
            "photos",
            "captioned_photos",
            "uncaptioned_photos",
            "groups",
            "duplicate_or_non_lot_photos",
        ],
        "submission facts cycle",
    )
    wall = "".join(
        f'<img src="{html.escape(project_path(photo["local_path"]).as_uri(), quote=True)}" alt="">'
        for photo in gallery["photos"][:120]
        if project_path(photo["local_path"]).is_file()
    )
    pair_markup = "".join(
        f'''<div class="pair" data-i="{index}"><div class="thumbs">
        <figure><img src="{html.escape(pair["first"].as_uri(), quote=True)}"><figcaption>photo {pair["first_sequence"]}<br><span>primary view</span></figcaption></figure>
        <figure class="dup"><img src="{html.escape(pair["second"].as_uri(), quote=True)}"><figcaption>photo {pair["second_sequence"]}<br><span>another angle</span></figcaption></figure>
        </div><div class="verdict">same lot &mdash; one bid slot<em>{_escape(pair["caption"])}</em></div></div>'''
        for index, pair in enumerate(pairs)
    )

    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>beat2</title><style>
*{{box-sizing:border-box;margin:0}}body{{width:1600px;height:900px;background:#080b11;overflow:hidden;color:#f1f5f9;font-family:-apple-system,"SF Pro Display","Helvetica Neue",sans-serif}}
.stage{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;opacity:0;transition:opacity .6s}}.stage.on{{opacity:1}}
.kick{{font-size:20px;letter-spacing:.36em;color:#22d3ee;text-transform:uppercase;font-weight:600}}h1{{font-size:74px;font-weight:800;letter-spacing:-.02em;margin-top:18px}}.sub{{font-size:30px;color:#94a3b8;margin-top:16px}}
#wall{{position:absolute;inset:0;display:grid;grid-template-columns:repeat(12,1fr);gap:6px;padding:24px;opacity:.20;filter:saturate(.5)}}#wall img{{width:100%;height:104px;object-fit:cover;border-radius:3px}}
.pair{{display:none;flex-direction:column;align-items:center}}.pair.on{{display:flex}}.thumbs{{display:flex;gap:60px;transition:gap .9s cubic-bezier(.6,0,.2,1)}}.thumbs.merge{{gap:0}}figure{{text-align:center}}figure img{{width:330px;height:250px;object-fit:cover;border-radius:10px;border:2px solid #1e293b}}.dup img{{border-color:#8b5cf6}}figcaption{{margin-top:12px;font-size:21px;color:#cbd5e1}}figcaption span{{color:#64748b;font-size:18px}}.dup figcaption span{{color:#8b5cf6}}
.verdict{{margin-top:30px;font-size:30px;color:#34d399;font-weight:600;opacity:0;transition:opacity .5s;text-align:center}}.verdict.on{{opacity:1}}.verdict em{{display:block;color:#94a3b8;font-size:22px;font-style:normal;margin-top:8px}}
.big{{font-size:150px;font-weight:800;letter-spacing:-.03em}}.arrow{{font-size:70px;color:#22d3ee;margin:0 46px}}.row{{display:flex;align-items:center}}.lbl{{font-size:22px;letter-spacing:.14em;text-transform:uppercase;color:#64748b;text-align:center;margin-top:10px}}.note{{margin-top:44px;font-size:28px;color:#34d399;text-align:center}}
.flow{{display:flex;gap:20px;align-items:center;margin-top:45px}}.flow b{{padding:24px;border:1px solid #334155;border-radius:10px;background:#0d1219;font-size:22px}}.flow i{{font-style:normal;color:#22d3ee;font-size:34px}}
.card{{border:1px solid #1e293b;border-left:5px solid #f59e0b;background:#0d1219;padding:38px 46px;border-radius:12px;max-width:1080px}}.card .q{{font-size:38px;color:#f1f5f9;font-weight:600}}.card .a{{font-size:30px;color:#f59e0b;margin-top:20px;font-family:ui-monospace,Menlo,monospace}}.card .w{{font-size:22px;color:#64748b;margin-top:20px}}
</style></head><body><div id="wall">{wall}</div>
<div class="stage" id="s1"><div class="kick">One sanctioned gallery drop</div><h1>{int(cycle["photos"])} photos, no lot numbers</h1><div class="sub">{int(cycle["captioned_photos"])} captioned &middot; {int(cycle["uncaptioned_photos"])} without captions</div></div>
<div class="stage" id="s2">{pair_markup}</div>
<div class="stage" id="s3"><div class="row"><div><div class="big">{int(cycle["photos"])}</div><div class="lbl">photos in</div></div><div class="arrow">&rarr;</div><div><div class="big" style="color:#34d399">{int(cycle["groups"])}</div><div class="lbl">groups out</div></div></div><div class="note">{int(cycle["duplicate_or_non_lot_photos"])} duplicate-angle or non-lot photos do not become separate bids</div></div>
<div class="stage" id="s4"><div class="kick">Evidence-preserving pricing</div><div class="flow"><b>Grounded research</b><i>&rarr;</i><b>Structured extraction</b><i>&rarr;</i><b>Median of three</b><i>&rarr;</i><b>Cite or refuse</b></div><div class="note">Search evidence stays separate from constrained decoding</div></div>
<div class="stage" id="s5"><div class="card"><div class="q">No reproducible completed-sale evidence.</div><div class="a">"NO EXTERNAL COMP &mdash; human pricing required"</div><div class="w">The lot is surfaced for a person to price. The system does not invent a number.</div></div></div>
<script>
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));const show=id=>document.getElementById(id).classList.add('on');const hide=id=>document.getElementById(id).classList.remove('on');
(async()=>{{await sleep(400);show('s1');await sleep(8200);hide('s1');await sleep(700);show('s2');for(const pair of document.querySelectorAll('.pair')){{pair.classList.add('on');await sleep(1500);pair.querySelector('.thumbs').classList.add('merge');await sleep(800);pair.querySelector('.verdict').classList.add('on');await sleep(2500);pair.classList.remove('on')}}hide('s2');await sleep(700);show('s3');await sleep(10500);hide('s3');await sleep(700);show('s4');await sleep(12000);hide('s4');await sleep(700);show('s5');await sleep(13500);document.title='done'}})();
</script></body></html>'''
    page_value = output_value or video_manifest["recordings"]["beat2"]["page"]
    return atomic_write_text(page_value, page)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output")
    parser.add_argument("--pair-limit", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        output = build(args.manifest, args.output, args.pair_limit)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"Beat 2 page build failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {display_path(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
