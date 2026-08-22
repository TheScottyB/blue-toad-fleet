// Shared Playwright recording utilities. Each run gets its own directory and
// publishes only the WebM attached to the page created by that run.
import { createHash, randomUUID } from 'crypto';
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
} from 'fs';
import { tmpdir } from 'os';
import { basename, dirname, isAbsolute, join, resolve } from 'path';
import { fileURLToPath, pathToFileURL } from 'url';
import { chromium } from 'playwright';

export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

export function projectPath(value) {
  return isAbsolute(value) ? resolve(value) : resolve(REPO_ROOT, value);
}

export function fileUrl(value) {
  return pathToFileURL(projectPath(value)).href;
}

export function readJsonObject(value, label = 'JSON file') {
  const path = projectPath(value);
  let payload;
  try {
    payload = JSON.parse(readFileSync(path, 'utf8'));
  } catch (error) {
    throw new Error(`invalid ${label} at ${path}: ${error.message}`);
  }
  if (!payload || Array.isArray(payload) || typeof payload !== 'object') {
    throw new Error(`${label} must contain a JSON object: ${path}`);
  }
  return payload;
}

export function manifestArgument(argv = process.argv.slice(2)) {
  const index = argv.indexOf('--manifest');
  return index === -1 ? 'media/video_manifest.json' : argv[index + 1];
}

export function requireKeys(payload, keys, label) {
  const missing = keys.filter(key => !(key in payload));
  if (missing.length) throw new Error(`${label} is missing: ${missing.join(', ')}`);
}

export function readVerifiedFacts(manifest) {
  requireKeys(manifest, ['facts', 'sources'], 'video manifest');
  const facts = readJsonObject(manifest.facts, 'submission facts');
  requireKeys(
    facts,
    ['schema_version', 'cycle', 'money', 'tests', 'runtime', 'source_sha256'],
    'submission facts',
  );
  if (![1, 2].includes(facts.schema_version)) {
    throw new Error(`unsupported submission facts schema_version: ${facts.schema_version}`);
  }
  const stale = [];
  for (const [name, value] of Object.entries(manifest.sources)) {
    const digest = createHash('sha256').update(readFileSync(projectPath(value))).digest('hex');
    if (facts.source_sha256[name] !== digest) stale.push(name);
  }
  if (stale.length) throw new Error(`submission facts are stale for: ${stale.sort().join(', ')}`);
  return facts;
}

function publishRecording(source, destinationValue) {
  const destination = projectPath(destinationValue);
  mkdirSync(dirname(destination), { recursive: true });
  const partial = join(
    dirname(destination),
    `.${basename(destination)}.${process.pid}.${randomUUID()}.partial.webm`,
  );
  try {
    copyFileSync(source, partial);
    if (statSync(partial).size === 0) throw new Error('Playwright produced an empty video');
    renameSync(partial, destination);
  } catch (error) {
    rmSync(partial, { force: true });
    throw error;
  }
  return destination;
}

export async function recordPage({ output, contextOptions = {}, action }) {
  const recordingDirectory = mkdtempSync(join(tmpdir(), 'blue-toad-video-'));
  const browser = await chromium.launch({ channel: 'chrome' });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    colorScheme: 'dark',
    ...contextOptions,
    recordVideo: { dir: recordingDirectory, size: { width: 1600, height: 900 } },
  });
  const page = await context.newPage();
  const video = page.video();
  let actionError = null;
  try {
    await action(page);
  } catch (error) {
    actionError = error;
  } finally {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }
  try {
    if (actionError) throw actionError;
    if (!video) throw new Error('Playwright did not attach a video to the page');
    const source = await video.path();
    return publishRecording(source, output);
  } finally {
    rmSync(recordingDirectory, { recursive: true, force: true });
  }
}

export async function checkedGoto(page, url, options = {}) {
  const { expectedMarkers = [], ...gotoOptions } = options;
  const response = await page.goto(url, gotoOptions);
  if (response && !response.ok()) {
    throw new Error(`page returned HTTP ${response.status()}: ${url}`);
  }
  const finalUrl = page.url();
  const pageState = await page.evaluate(() => {
    const text = `${document.title}\n${document.body?.innerText || ''}`.toLowerCase();
    return {
      challenge: ['captcha', 'verify you are human', 'sign in to continue', 'access denied']
        .find(marker => text.includes(marker)) || null,
      text,
      title: document.title,
    };
  });
  if (pageState.challenge) {
    throw new Error(`challenge page detected (${pageState.challenge}): ${finalUrl}`);
  }
  const missing = expectedMarkers.filter(marker => !pageState.text.includes(marker.toLowerCase()));
  if (missing.length) throw new Error(`expected page marker is missing: ${missing.join(', ')}`);
  return response;
}
