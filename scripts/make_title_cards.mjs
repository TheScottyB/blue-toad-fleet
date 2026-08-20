import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CSS = `
*{margin:0;padding:0;box-sizing:border-box}
body{width:1920px;height:1080px;font-family:-apple-system,"SF Pro Display","Helvetica Neue",sans-serif;
 -webkit-font-smoothing:antialiased}
.full{width:1920px;height:1080px;background:#080b11;display:flex;flex-direction:column;
 align-items:center;justify-content:center;position:relative;overflow:hidden}
.glow{position:absolute;width:1400px;height:1400px;border-radius:50%;
 background:radial-gradient(circle,rgba(34,211,238,.13) 0%,rgba(139,92,246,.09) 38%,transparent 66%)}
.rings{position:absolute;width:900px;height:900px;border-radius:50%;
 border:1px solid rgba(34,211,238,.13);box-shadow:0 0 0 120px rgba(34,211,238,.04) inset}
.rings:after{content:"";position:absolute;inset:150px;border-radius:50%;border:1px solid rgba(139,92,246,.13)}
.kick{font-size:24px;letter-spacing:.42em;color:#22d3ee;text-transform:uppercase;font-weight:600;z-index:2}
h1{font-size:112px;font-weight:800;color:#f1f5f9;letter-spacing:-.025em;margin:26px 0 0;z-index:2}
.sub{font-size:38px;color:#94a3b8;margin-top:24px;font-weight:400;z-index:2;text-align:center;line-height:1.45}
.rule{width:132px;height:4px;margin-top:44px;z-index:2;border-radius:2px;
 background:linear-gradient(90deg,#22d3ee,#8b5cf6)}
.facts{display:flex;gap:64px;margin-top:64px;z-index:2}
.fact{text-align:center}
.fact b{display:block;font-size:52px;color:#34d399;font-weight:700}
.fact span{font-size:22px;color:#64748b;letter-spacing:.11em;text-transform:uppercase}
.url{font-size:30px;color:#22d3ee;margin-top:56px;z-index:2;font-family:ui-monospace,Menlo,monospace}
/* lower third */
.lt{width:1920px;height:1080px;background:transparent;position:relative}
.bar{position:absolute;left:104px;bottom:96px;padding:30px 46px 32px;border-left:5px solid #22d3ee;
 background:linear-gradient(90deg,rgba(6,9,14,.985) 0%,rgba(6,9,14,.975) 62%,rgba(6,9,14,.90) 84%,rgba(6,9,14,0) 100%);
 box-shadow:0 24px 70px rgba(0,0,0,.65);
 border-radius:0 10px 10px 0;min-width:1180px;padding-right:220px}
.bar .k{font-size:19px;letter-spacing:.34em;color:#22d3ee;text-transform:uppercase;font-weight:600}
.bar .h{font-size:52px;color:#f1f5f9;font-weight:700;margin-top:12px;letter-spacing:-.015em}
.bar .s{font-size:27px;color:#94a3b8;margin-top:10px}
`;

const open = `<div class="full"><div class="glow"></div><div class="rings"></div>
<div class="kick">All Things Agentic · 2026</div><h1>Blue Toad Fleet</h1>
<div class="sub">An autonomous agent that walks the auction floor,<br>prices every lot, and bids inside your budget.</div>
<div class="rule"></div></div>`;

const close = `<div class="full"><div class="glow"></div>
<div class="kick">Live on Google Cloud Run</div><h1>Blue Toad Fleet</h1>
<div class="facts">
 <div class="fact"><b>359</b><span>lots appraised</span></div>
 <div class="fact"><b>12</b><span>bids allocated</span></div>
 <div class="fact"><b>160</b><span>tests · &lt;0.1s</span></div>
</div>
<div class="url">blue-toad-fleet-u5gvrqwvua-uc.a.run.app</div>
<div class="rule"></div></div>`;

const lt = (k, h, s) => `<div class="lt"><div class="bar">
<div class="k">${k}</div><div class="h">${h}</div><div class="s">${s}</div></div></div>`;

const CARDS = {
  'open': [open, false],
  'close': [close, false],
  'lt-hero':     [lt('Gate Console', 'One screen, one decision pass', '462 photos ingested · 359 lots appraised'), true],
  'lt-topology': [lt('Spatial Room Graph', 'It knows where each lot sits', 'Lots mapped to the physical pole-barn showroom'), true],
  'lt-curator':  [lt('Negotiation Strategy', 'Alpha picks and a wildcard bet', 'Ranked by margin, capped by a $600 budget'), true],
  'lt-memory':   [lt('Cross-Cycle Memory', "Three questions it didn't ask", 'Already answered by what you taught it last cycle'), true],
  'lt-sheet':    [lt('The Sheet', 'Auto-send under $35 · approve the rest', 'Every bid carries the reasoning behind it'), true],
  'lt-skips':    [lt('Disciplined Skips', '347 lots rejected, each with a reason', 'Fit below threshold — no bid, no noise'), true],
};

const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
for (const [name, [html, alpha]] of Object.entries(CARDS)) {
  await p.setContent(`<style>${CSS}</style>${html}`);
  await p.waitForTimeout(150);
  await p.screenshot({ path: `media/cards/${name}.png`, omitBackground: alpha });
  console.log('ok', name);
}
await b.close();
