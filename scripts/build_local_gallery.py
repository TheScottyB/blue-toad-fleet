#!/usr/bin/env python3
"""Render the cached Aug-22 drop as a local gallery page for Beat 1 footage.

The live gallery serves 403 to automated clients (see src/intake/__init__.py),
so the video uses the same cached photos the pipeline ingests.
Writes /tmp/gallery_local.html; record it with scripts/record_gallery.mjs.
"""
import json, os

m = json.load(open('data/aug22_gallery_4160518/manifest.json'))
photos = m['photos']
uncaptioned = sum(1 for p in photos if not p.get('has_caption'))

cells = []
for p in photos:
    src = os.path.abspath(p['local_path'])
    cap = p.get('caption') or ''
    cells.append(
        f'<figure><img loading="eager" src="file://{src}">'
        f'<figcaption class="{"cap" if cap else "nocap"}">{cap or "&nbsp;"}</figcaption></figure>')

html = f'''<meta charset="utf-8"><title>Blue Toad Auctions - Aug 22 drop</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#fff;font-family:Georgia,"Times New Roman",serif}}
.hdr{{padding:18px 26px;border-bottom:2px solid #c00}}
.hdr b{{color:#c00;font-size:22px}} .hdr span{{color:#333;font-size:15px;margin-left:14px}}
.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;padding:20px 26px}}
figure{{margin:0}}
img{{width:100%;height:190px;object-fit:cover;border:1px solid #6a86c8;display:block;background:#eee}}
figcaption{{text-align:center;font-weight:bold;font-size:14px;padding:6px 2px 0;line-height:1.25;min-height:34px}}
.nocap{{color:#bbb}}
</style>
<div class="hdr"><b>Click Photos to Enlarge</b><span>[ View Auction listing ]</span>
<span>Photos Per Page: All &nbsp;|&nbsp; {len(photos)} photos &nbsp;&middot;&nbsp; {uncaptioned} with no caption at all</span></div>
<div class="grid">{"".join(cells)}</div>'''

open('/tmp/gallery_local.html', 'w').write(html)
print(f'/tmp/gallery_local.html  ({len(photos)} photos, {uncaptioned} uncaptioned)')

