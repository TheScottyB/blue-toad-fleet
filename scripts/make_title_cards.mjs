import { mkdirSync } from 'fs';
import { chromium } from 'playwright';
import {
  manifestArgument,
  projectPath,
  readJsonObject,
  readVerifiedFacts,
  requireKeys,
} from './video_recording.mjs';

const manifest = readJsonObject(manifestArgument(), 'video manifest');
const facts = readVerifiedFacts(manifest);
const { cycle, money, tests } = facts;
requireKeys(
  cycle,
  ['photos', 'groups', 'approved_bids', 'skipped', 'duplicate_or_non_lot_photos'],
  'cycle facts',
);
requireKeys(money, ['budget_cap', 'committed_max', 'committed_all_in'], 'money facts');
requireKeys(tests, ['collected', 'passed', 'skipped'], 'test facts');

const escapeHtml = value => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');
const dollars = value => `$${Number(value).toFixed(2)}`;

const CSS = `
*{margin:0;padding:0;box-sizing:border-box}
body{width:1920px;height:1080px;font-family:-apple-system,"SF Pro Display","Helvetica Neue",sans-serif;-webkit-font-smoothing:antialiased}
.full{width:1920px;height:1080px;background:#080b11;display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative;overflow:hidden}
.glow{position:absolute;width:1400px;height:1400px;border-radius:50%;background:radial-gradient(circle,rgba(34,211,238,.13) 0%,rgba(139,92,246,.09) 38%,transparent 66%)}
.rings{position:absolute;width:900px;height:900px;border-radius:50%;border:1px solid rgba(34,211,238,.13);box-shadow:0 0 0 120px rgba(34,211,238,.04) inset}
.rings:after{content:"";position:absolute;inset:150px;border-radius:50%;border:1px solid rgba(139,92,246,.13)}
.kick{font-size:24px;letter-spacing:.42em;color:#22d3ee;text-transform:uppercase;font-weight:600;z-index:2}
h1{font-size:112px;font-weight:800;color:#f1f5f9;letter-spacing:-.025em;margin:26px 0 0;z-index:2}
.sub{font-size:38px;color:#94a3b8;margin-top:24px;font-weight:400;z-index:2;text-align:center;line-height:1.45}
.rule{width:132px;height:4px;margin-top:44px;z-index:2;border-radius:2px;background:linear-gradient(90deg,#22d3ee,#8b5cf6)}
.facts{display:flex;gap:64px;margin-top:64px;z-index:2}.fact{text-align:center}.fact b{display:block;font-size:52px;color:#34d399;font-weight:700}.fact span{font-size:22px;color:#64748b;letter-spacing:.11em;text-transform:uppercase}
.url{font-size:30px;color:#22d3ee;margin-top:56px;z-index:2;font-family:ui-monospace,Menlo,monospace}
.lt{width:1920px;height:1080px;background:transparent;position:relative}.bar{position:absolute;left:104px;bottom:96px;padding:30px 220px 32px 46px;border-left:5px solid #22d3ee;background:linear-gradient(90deg,rgba(6,9,14,.985) 0%,rgba(6,9,14,.975) 62%,rgba(6,9,14,.90) 84%,rgba(6,9,14,0) 100%);box-shadow:0 24px 70px rgba(0,0,0,.65);border-radius:0 10px 10px 0;min-width:1180px}.bar .k{font-size:19px;letter-spacing:.34em;color:#22d3ee;text-transform:uppercase;font-weight:600}.bar .h{font-size:52px;color:#f1f5f9;font-weight:700;margin-top:12px;letter-spacing:-.015em}.bar .s{font-size:27px;color:#94a3b8;margin-top:10px}
`;

const open = `<div class="full"><div class="glow"></div><div class="rings"></div>
<div class="kick">All Things Agentic · 2026</div><h1>Blue Toad Fleet</h1>
<div class="sub">A sourcing assistant that triages gallery photos,<br>appraises selected lots, and drafts bounded absentee bids.</div><div class="rule"></div></div>`;
const close = `<div class="full"><div class="glow"></div><div class="kick">Verified submission snapshot</div><h1>Blue Toad Fleet</h1>
<div class="facts"><div class="fact"><b>${cycle.groups}</b><span>photo groups</span></div><div class="fact"><b>${cycle.approved_bids}</b><span>bids allocated</span></div><div class="fact"><b>${tests.passed}/${tests.collected}</b><span>tests passed</span></div></div>
<div class="url">${dollars(money.committed_max)} max · ${dollars(money.committed_all_in)} all-in</div><div class="rule"></div></div>`;
const lowerThird = (kick, heading, subheading) => `<div class="lt"><div class="bar"><div class="k">${escapeHtml(kick)}</div><div class="h">${escapeHtml(heading)}</div><div class="s">${escapeHtml(subheading)}</div></div></div>`;

const cards = {
  open: [open, false],
  close: [close, false],
  'lt-hero': [lowerThird('Gate Console', 'One screen, one decision pass', `${cycle.photos} photos · ${cycle.groups} grouped lots`), true],
  'lt-topology': [lowerThird('Photo grouping', 'Multiple views become one bid slot', `${cycle.duplicate_or_non_lot_photos} duplicate-angle or non-lot photos suppressed`), true],
  'lt-curator': [lowerThird('Negotiation Strategy', 'Ranked picks inside a hard cap', `${dollars(money.committed_max)} committed against a ${dollars(money.budget_cap)} budget`), true],
  'lt-memory': [lowerThird('Cross-cycle memory', 'Prior operator answers stay keyed', 'Policy memory is visible and reviewable at the gate'), true],
  'lt-sheet': [lowerThird('The Sheet', `${cycle.approved_bids} approved absentee bids`, `${dollars(money.committed_all_in)} including the absentee fee`), true],
  'lt-skips': [lowerThird('Disciplined skips', `${cycle.skipped} lots receive no bid`, 'Below threshold means no allocation'), true],
};

const cardsDirectory = projectPath('media/cards');
mkdirSync(cardsDirectory, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome' });
try {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  for (const [name, [markup, alpha]] of Object.entries(cards)) {
    await page.setContent(`<style>${CSS}</style>${markup}`);
    await page.waitForTimeout(150);
    await page.screenshot({ path: projectPath(`media/cards/${name}.png`), omitBackground: alpha });
    console.log(`wrote media/cards/${name}.png`);
  }
} finally {
  await browser.close();
}
