import { execFileSync } from 'child_process';
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, statSync } from 'fs';
import { dirname } from 'path';
import { chromium } from 'playwright';
import {
  checkedGoto,
  fileUrl,
  manifestArgument,
  projectPath,
  readJsonObject,
  requireKeys,
} from './video_recording.mjs';

const manifestPath = manifestArgument();
const manifest = readJsonObject(manifestPath, 'video manifest');
const gallery = manifest.recordings?.gallery;
requireKeys(gallery || {}, ['page'], 'gallery recording');
const source = readJsonObject(manifest.sources.gallery_manifest, 'gallery manifest');
const expectedImages = source.photos?.length;
if (!Number.isInteger(expectedImages) || expectedImages <= 0) {
  throw new Error('gallery manifest has no photos');
}

const configuredPython = process.env.BTF_PYTHON;
const venvPython = projectPath('.venv/bin/python');
const python = configuredPython || (existsSync(venvPython) ? venvPython : 'python3');
execFileSync(
  python,
  [projectPath('scripts/build_local_gallery.py'), '--manifest', projectPath(manifestPath)],
  { cwd: projectPath('.'), stdio: 'inherit' },
);

const destination = projectPath('docs/screenshots/00-raw-auction-gallery.png');
const partial = projectPath('docs/screenshots/.00-raw-auction-gallery.partial.png');
mkdirSync(dirname(destination), { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
  await checkedGoto(page, process.env.BTF_GALLERY || fileUrl(gallery.page), {
    waitUntil: 'domcontentloaded',
  });
  await page.waitForFunction(
    count => [...document.images].filter(image => image.complete && image.naturalWidth > 0).length === count,
    expectedImages,
    { timeout: 120000 },
  );
  const actual = await page.evaluate(() => document.images.length);
  if (actual !== expectedImages) throw new Error(`gallery has ${actual}/${expectedImages} images`);
  await page.screenshot({ path: partial, fullPage: false });
  const bytes = readFileSync(partial);
  if (statSync(partial).size < 100 || !bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) {
    throw new Error('raw gallery capture is not a valid PNG');
  }
  renameSync(partial, destination);
  console.log(`wrote ${destination}`);
} finally {
  rmSync(partial, { force: true });
  await browser.close();
}
