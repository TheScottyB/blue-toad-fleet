// Beat 1 footage: the raw 462-photo gallery drop, scrolled top to bottom.
import { chromium } from '/Users/scottybe/.npm/_npx/31e32ef8478fbf80/node_modules/playwright/index.mjs';
import { readdirSync, renameSync } from 'fs';

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
await p.waitForTimeout(5000);                    // let thumbnails paint

const count = await p.evaluate(() => document.images.length);
console.log('images:', count);

await p.waitForTimeout(2200);                    // hold on the top of the wall
// accelerating scroll: slow at first, then the overwhelm
await p.evaluate(() => new Promise(res => {
  const end = document.body.scrollHeight - innerHeight, t0 = performance.now(), dur = 20000;
  (function step(now) {
    const k = Math.min(1, (now - t0) / dur);
    scrollTo(0, end * (k * k * (3 - 2 * k)));    // smoothstep
    k < 1 ? requestAnimationFrame(step) : res();
  })(performance.now());
}));
await p.waitForTimeout(1800);

await ctx.close();
await b.close();
const webm = readdirSync(DIR).filter(f => f.endsWith('.webm') && f !== 'walkthrough.webm').sort().pop();
renameSync(`${DIR}/${webm}`, `${DIR}/gallery.webm`);
console.log('media/raw/gallery.webm');
