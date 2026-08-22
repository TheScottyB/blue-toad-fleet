// Beat 2: record the facts-driven intake/grouping animation.
import {
  checkedGoto,
  fileUrl,
  manifestArgument,
  readJsonObject,
  recordPage,
  requireKeys,
} from './video_recording.mjs';

const manifest = readJsonObject(manifestArgument(), 'video manifest');
const config = manifest.recordings?.beat2;
requireKeys(config || {}, ['page', 'output'], 'beat2 recording');

const output = await recordPage({
  output: config.output,
  action: async page => {
    await checkedGoto(page, fileUrl(config.page), { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.title === 'done', null, { timeout: 180000 });
    await page.waitForTimeout(1500);
  },
});
console.log(output);
