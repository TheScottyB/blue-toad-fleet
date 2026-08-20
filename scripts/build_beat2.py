#!/usr/bin/env python3
"""Render Beat 2 (intake -> lots) from the real Aug-22 manifest.

Shows only what the pipeline verifiably does: duplicate camera angles chained
onto their lot via `same_lot_as_previous`. Deliberately does NOT depict surface
classification or a reconstructed room graph -- no such code exists in src/.
Writes /tmp/beat2.html for scripts/record_beat2.mjs.
"""
import json, os, pathlib

d = json.loads(pathlib.Path("/tmp/beat2.json").read_text())
ph = json.loads(pathlib.Path("data/aug22_gallery_4160518/manifest.json").read_text())["photos"]

wall = "".join(
    f'<img src="file://{os.path.abspath(p["local_path"])}">'
    for p in ph[:120] if os.path.exists(p["local_path"]))

pairs = "".join(
    f'''<div class="pair" data-i="{i}">
      <div class="thumbs">
        <figure><img src="file://{p["imgs"][0]}"><figcaption>photo {p["seqs"][0]}<br><span>captioned</span></figcaption></figure>
        <figure class="dup"><img src="file://{p["imgs"][1]}"><figcaption>photo {p["seqs"][1]}<br><span>no caption</span></figcaption></figure>
      </div>
      <div class="verdict">same lot &mdash; one bid slot<em>{p["caption"]}</em></div>
    </div>''' for i, p in enumerate(d["pairs"]))

page = f"""<meta charset="utf-8"><title>beat2</title><style>
*{{box-sizing:border-box;margin:0}}
body{{width:1600px;height:900px;background:#080b11;overflow:hidden;color:#f1f5f9;
 font-family:-apple-system,"SF Pro Display","Helvetica Neue",sans-serif}}
.stage{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
 justify-content:center;opacity:0;transition:opacity .6s}}
.stage.on{{opacity:1}}
.kick{{font-size:20px;letter-spacing:.36em;color:#22d3ee;text-transform:uppercase;font-weight:600}}
h1{{font-size:74px;font-weight:800;letter-spacing:-.02em;margin-top:18px}}
.sub{{font-size:30px;color:#94a3b8;margin-top:16px}}
#wall{{position:absolute;inset:0;display:grid;grid-template-columns:repeat(12,1fr);
 gap:6px;padding:24px;opacity:.20;filter:saturate(.5)}}
#wall img{{width:100%;height:104px;object-fit:cover;border-radius:3px}}
.pair{{display:none;flex-direction:column;align-items:center}}
.pair.on{{display:flex}}
.thumbs{{display:flex;gap:60px;transition:gap .9s cubic-bezier(.6,0,.2,1)}}
.thumbs.merge{{gap:0}}
figure{{text-align:center}}
figure img{{width:330px;height:250px;object-fit:cover;border-radius:10px;
 border:2px solid #1e293b}}
.dup img{{border-color:#8b5cf6}}
figcaption{{margin-top:12px;font-size:21px;color:#cbd5e1}}
figcaption span{{color:#64748b;font-size:18px}}
.dup figcaption span{{color:#8b5cf6}}
.verdict{{margin-top:30px;font-size:30px;color:#34d399;font-weight:600;opacity:0;
 transition:opacity .5s;text-align:center}}
.verdict.on{{opacity:1}}
.verdict em{{display:block;color:#94a3b8;font-size:22px;font-style:normal;margin-top:8px}}
.big{{font-size:150px;font-weight:800;letter-spacing:-.03em}}
.arrow{{font-size:70px;color:#22d3ee;margin:0 46px}}
.row{{display:flex;align-items:center}}
.lbl{{font-size:22px;letter-spacing:.14em;text-transform:uppercase;color:#64748b;
 text-align:center;margin-top:10px}}
.note{{margin-top:44px;font-size:28px;color:#34d399}}
.card{{border:1px solid #1e293b;border-left:5px solid #f59e0b;background:#0d1219;
 padding:38px 46px;border-radius:12px;max-width:1080px}}
.card .q{{font-size:38px;color:#f1f5f9;font-weight:600}}
.card .a{{font-size:30px;color:#f59e0b;margin-top:20px;font-family:ui-monospace,Menlo,monospace}}
.card .w{{font-size:22px;color:#64748b;margin-top:20px}}
</style>
<div id="wall">{wall}</div>

<div class="stage" id="s1"><div class="kick">One gallery drop</div>
<h1>462 photos, no lot numbers</h1>
<div class="sub">304 captioned &middot; 158 with no caption at all</div></div>

<div class="stage" id="s2">{pairs}</div>

<div class="stage" id="s3"><div class="row">
 <div><div class="big">462</div><div class="lbl">photos in</div></div>
 <div class="arrow">&rarr;</div>
 <div><div class="big" style="color:#34d399">359</div><div class="lbl">lots out</div></div>
</div><div class="note">103 duplicate camera angles chained onto the lot they belong to</div></div>

<div class="stage" id="s4"><div class="kick">Same run, July 11 gallery</div>
<div class="row" style="margin-top:34px">
 <div><div class="big">452</div><div class="lbl">photos in</div></div>
 <div class="arrow">&rarr;</div>
 <div><div class="big" style="color:#34d399">357</div><div class="lbl">lots out</div></div>
</div><div class="note">95 duplicates merged &mdash; 95 absentee bids never placed twice</div></div>

<div class="stage" id="s5"><div class="card">
 <div class="q">Unmarked pottery. No comparable sale found.</div>
 <div class="a">"NO EXTERNAL COMP &mdash; human pricing required"</div>
 <div class="w">The lot is surfaced for a person to price. It is never guessed at.</div>
</div></div>

<script>
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const show=id=>document.getElementById(id).classList.add('on');
const hide=id=>document.getElementById(id).classList.remove('on');
(async()=>{{
  await sleep(400); show('s1'); await sleep(8200); hide('s1'); await sleep(700);
  show('s2');
  for(const p of document.querySelectorAll('.pair')){{
    p.classList.add('on');
    await sleep(1500);
    p.querySelector('.thumbs').classList.add('merge');
    await sleep(800);
    p.querySelector('.verdict').classList.add('on');
    await sleep(2500);
    p.classList.remove('on');
  }}
  hide('s2'); await sleep(700);
  show('s3'); await sleep(11500); hide('s3'); await sleep(700);
  show('s4'); await sleep(11500); hide('s4'); await sleep(700);
  show('s5'); await sleep(11000);
  document.title='done';
}})();
</script>"""
pathlib.Path("/tmp/beat2.html").write_text(page)
print(f"/tmp/beat2.html ({len(d['pairs'])} real merge pairs)")
