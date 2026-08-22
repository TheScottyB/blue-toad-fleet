// Beat 4: record the declared, previously captured proof session.
import {
  checkedGoto,
  fileUrl,
  manifestArgument,
  readJsonObject,
  recordPage,
  requireKeys,
} from './video_recording.mjs';

const manifest = readJsonObject(manifestArgument(), 'video manifest');
const config = manifest.recordings?.terminal;
requireKeys(config || {}, ['page', 'output', 'steps'], 'terminal recording');

const output = await recordPage({
  output: config.output,
  action: async page => {
    await checkedGoto(page, fileUrl(config.page), { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.title === 'done', null, { timeout: 180000 });
    await page.waitForTimeout(1500);
  },
});
console.log(output);
