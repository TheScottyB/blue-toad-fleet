// Deterministic screen recording of the live Gate Console.
// Emits media/raw/beats.json so the ffmpeg pass knows where each title card goes.
import { chromium } from 'playwright';
import { writeFileSync, readdirSync, renameSync, statSync } from 'fs';

const URL = process.env.BTF_URL || 'https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app';
const DIR = 'media/raw';

const b = await chromium.launch({ channel: 'chrome' });
const ctx = await b.newContext({
  viewport: { width: 1600, height: 900 },
  colorScheme: 'dark',
  recordVideo: { dir: DIR, size: { width: 1600, height: 900 } },
});
const p = await ctx.newPage();
await p.goto(URL, { waitUntil: 'networkidle' });
await p.waitForTimeout(1200); // let the recorder settle before t=0

const t0 = Date.now();
const beats = [];
const mark = (label) => beats.push({ label, t: (Date.now() - t0) / 1000 });

const anchorY = (text, off = 40) =>
  p.evaluate(([t, o]) => {
    const hits = [...document.querySelectorAll('body *')]
      .filter(e => e.textContent && e.textContent.toLowerCase().includes(t.toLowerCase()));
    if (!hits.length) return null;
    let n = hits[hits.length - 1];
    while (n && n.getBoundingClientRect().width < 400) n = n.parentElement;
    return Math.max(0, n.getBoundingClientRect().top + window.scrollY - o);
  }, [text, off]);

// eased scroll so the footage reads as deliberate, not jumpy
const glide = (y, ms) =>
  p.evaluate(([target, dur]) => new Promise(res => {
    const start = window.scrollY, delta = target - start, t0 = performance.now();
    const ease = x => x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2;
    (function step(now) {
      const k = Math.min(1, (now - t0) / dur);
      window.scrollTo(0, start + delta * ease(k));
      k < 1 ? requestAnimationFrame(step) : res();
    })(performance.now());
  }), [y, ms]);

const BEATS = [
  ['hero',      null,                          0,    4200],
  ['topology',  'POLE BARN SHOWROOM TOPOLOGY',  1600, 5200],
  ['curator',   "Curator's Negotiation",        1300, 5000],
  ['memory',    'ANSWERED FROM MEMORY',         1300, 5200],
  ['sheet',     'BT-001',                       1600, 6000],
  ['bids',      'BT-021',                       3000, 3500],
  ['skips',     'BT-003',                       1800, 4200],
];

for (const [label, anchor, glideMs, hold] of BEATS) {
  if (anchor) {
    const y = await anchorY(anchor, label === 'sheet' ? 150 : 40);
    if (y === null) { console.log('MISS', label); continue; }
    await glide(y, glideMs);
  }
  mark(label);
  await p.waitForTimeout(hold);
}
mark('end');

await ctx.close();
await b.close();

// Exclude the named outputs: playwright writes hex-named files, and
// 'walkthrough.webm' sorts AFTER hex, so a naive sort().pop() renames the
// previous run onto itself and silently discards the new recording.
const OUTPUTS = new Set(['walkthrough.webm', 'gallery.webm']);
// Sort by mtime, not by name: playwright's filenames are random hex, so a
// lexicographic sort picks an arbitrary file -- often a leftover from an
// earlier run -- and the fresh recording is silently thrown away.
const webm = readdirSync(DIR)
  .filter(f => f.endsWith('.webm') && !OUTPUTS.has(f))
  .map(f => ({ f, t: statSync(`${DIR}/${f}`).mtimeMs }))
  .sort((a, b) => a.t - b.t)
  .pop()?.f;
if (!webm) throw new Error('no new recording found in ' + DIR);
renameSync(`${DIR}/${webm}`, `${DIR}/walkthrough.webm`);
writeFileSync(`${DIR}/beats.json`, JSON.stringify(beats, null, 2));
console.log(JSON.stringify(beats));
