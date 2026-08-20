// Beat 1 footage: the raw 462-photo gallery drop, scrolled top to bottom.
import { chromium } from 'playwright';
import { readdirSync, renameSync, statSync } from 'fs';

// The live gallery serves 403 to automated clients (see src/intake/__init__.py),
// so Beat 1 renders the cached drop from the manifest the pipeline actually ingests.
const URL = process.env.BTF_GALLERY || 'file:///tmp/gallery_local.html';
const DIR = 'media/raw';

const b = await chromium.launch({ channel: 'chrome' });
const ctx = await b.newContext({
  viewport: { width: 1600, height: 900 },
  recordVideo: { dir: DIR, size: { width: 1600, height: 900 } },
});
const p = await ctx.newPage();
await p.goto(URL, { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(2000);                    // let thumbnails paint

const count = await p.evaluate(() => document.images.length);
console.log('images:', count);

await p.waitForTimeout(3000);                    // hold on the top of the wall
// accelerating scroll: slow at first, then the overwhelm
await p.evaluate(() => new Promise(res => {
  const end = document.body.scrollHeight - innerHeight, t0 = performance.now(), dur = 55000;
  (function step(now) {
    const k = Math.min(1, (now - t0) / dur);
    scrollTo(0, end * (k * k * (3 - 2 * k)));    // smoothstep
    k < 1 ? requestAnimationFrame(step) : res();
  })(performance.now());
}));
await p.waitForTimeout(4000);                    // hold on the bottom of the wall

await ctx.close();
await b.close();
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
renameSync(`${DIR}/${webm}`, `${DIR}/gallery.webm`);
console.log('media/raw/gallery.webm');
