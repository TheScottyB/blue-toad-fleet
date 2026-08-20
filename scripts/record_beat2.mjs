// Beat 2 footage: intake -> lots, rendered from the real Aug-22 manifest.
import { chromium } from 'playwright';
import { readdirSync, renameSync, statSync } from 'fs';

const DIR = 'media/raw';
const b = await chromium.launch({ channel: 'chrome' });
const ctx = await b.newContext({
  viewport: { width: 1600, height: 900 },
  colorScheme: 'dark',
  recordVideo: { dir: DIR, size: { width: 1600, height: 900 } },
});
const p = await ctx.newPage();
await p.goto('file:///tmp/beat2.html');
// NOTE: arg 2 is the polling argument, not options -- passing {timeout} there
// is silently ignored and the 30s default applies.
await p.waitForFunction(() => document.title === 'done', null, { timeout: 180000 });
await p.waitForTimeout(1500);
await ctx.close();
await b.close();

const OUTPUTS = new Set(['walkthrough.webm', 'gallery.webm', 'terminal.webm', 'beat2.webm']);
const webm = readdirSync(DIR)
  .filter(f => f.endsWith('.webm') && !OUTPUTS.has(f))
  .map(f => ({ f, t: statSync(`${DIR}/${f}`).mtimeMs }))
  .sort((a, b) => a.t - b.t)
  .pop()?.f;
if (!webm) throw new Error('no new recording found in ' + DIR);
renameSync(`${DIR}/${webm}`, `${DIR}/beat2.webm`);
console.log('media/raw/beat2.webm');
