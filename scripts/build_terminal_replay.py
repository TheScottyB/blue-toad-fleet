#!/usr/bin/env python3
"""Render the captured gcloud/pytest session as a 1080p terminal page.

Output is REAL command output captured by the caller into /tmp/term.json; this
only replays it. Writes /tmp/terminal.html for scripts/record_terminal.mjs.
"""
import html, json, pathlib

steps = json.loads(pathlib.Path("/tmp/term.json").read_text())

blocks = []
for i, s in enumerate(steps):
    # Raw text: the typing loop appends with textContent, so escaping here
    # would type the entity itself ("&#x27;") one character at a time.
    cmd = s["cmd"].replace("\\\n", "\n  ").replace("</script>", "<\\/script>")
    out = html.escape(s["out"])
    blocks.append(
        f'<div class="step" data-i="{i}">'
        f'<div class="cmd"><span class="p">rg@richmond</span>'
        f'<span class="c">:~/blue-toad-fleet$</span> <span class="t"></span>'
        f'<span class="cur">▋</span></div>'
        f'<pre class="out">{out}</pre>'
        f'<script type="text/plain" class="src">{cmd}</script></div>')

page = f"""<meta charset="utf-8"><title>proof</title><style>
*{{box-sizing:border-box;margin:0}}
body{{width:1600px;height:900px;background:#080b11;padding:52px 60px;
 font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:19px;line-height:1.65;
 color:#cbd5e1;overflow:hidden}}
.step{{display:none;margin-bottom:20px}} .step.on{{display:block}}
.p{{color:#34d399}} .c{{color:#64748b}} .t{{color:#f1f5f9}}
.cmd{{white-space:pre-wrap}}
.cur{{color:#22d3ee;animation:b 1s steps(2) infinite}}
@keyframes b{{50%{{opacity:0}}}}
.out{{color:#94a3b8;white-space:pre-wrap;margin-top:4px}}
.out:empty{{display:none}}
</style>
{''.join(blocks)}
<script>
const steps=[...document.querySelectorAll('.step')];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{{
  await sleep(900);
  for(const s of steps){{
    s.classList.add('on');
    const src=s.querySelector('.src').textContent;
    const t=s.querySelector('.t'), out=s.querySelector('.out');
    const keep=out.textContent; out.textContent='';
    for(const ch of src){{ t.textContent+=ch; await sleep(26); }}
    await sleep(420);
    s.querySelector('.cur').style.display='none';
    out.textContent=keep;
    await sleep(2700);
    if(document.body.scrollHeight>900) steps[steps.indexOf(s)-2]?.classList.remove('on');
  }}
  document.title='done';
}})();
</script>"""
pathlib.Path("/tmp/terminal.html").write_text(page)
print(f"/tmp/terminal.html ({len(steps)} steps)")
