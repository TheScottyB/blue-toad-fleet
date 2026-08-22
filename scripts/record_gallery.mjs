// Beat 1: record the manifest-backed local gallery from an isolated Playwright run.
import {
  checkedGoto,
  fileUrl,
  manifestArgument,
  readJsonObject,
  recordPage,
  requireKeys,
} from './video_recording.mjs';

const manifest = readJsonObject(manifestArgument(), 'video manifest');
requireKeys(manifest, ['recordings', 'sources'], 'video manifest');
const config = manifest.recordings.gallery;
requireKeys(
  config,
  ['page', 'output', 'duration_seconds', 'top_hold_seconds', 'bottom_hold_seconds'],
  'gallery recording',
);
const source = readJsonObject(manifest.sources.gallery_manifest, 'gallery manifest');
const expectedImages = source.photos?.length;
if (!Number.isInteger(expectedImages) || expectedImages <= 0) {
  throw new Error('gallery manifest has no photos');
}

const output = await recordPage({
  output: config.output,
  contextOptions: { colorScheme: 'light' },
  action: async page => {
    await checkedGoto(page, fileUrl(config.page), { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      count => [...document.images].filter(image => image.complete && image.naturalWidth > 0).length === count,
      expectedImages,
      { timeout: 120000 },
    );
    const actual = await page.evaluate(() => document.images.length);
    if (actual !== expectedImages) {
      throw new Error(`gallery page has ${actual}/${expectedImages} expected images`);
    }
    await page.waitForTimeout(Number(config.top_hold_seconds) * 1000);
    await page.evaluate(duration => new Promise(resolve => {
      const end = document.body.scrollHeight - innerHeight;
      const started = performance.now();
      (function step(now) {
        const progress = Math.min(1, (now - started) / duration);
        scrollTo(0, end * (progress * progress * (3 - 2 * progress)));
        progress < 1 ? requestAnimationFrame(step) : resolve();
      })(performance.now());
    }), Number(config.duration_seconds) * 1000);
    await page.waitForTimeout(Number(config.bottom_hold_seconds) * 1000);
  },
});
console.log(output);
