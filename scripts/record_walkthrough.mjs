// Beat 3: deterministic live-console recording with manifest-declared steps.
import { mkdirSync, writeFileSync } from 'fs';
import { dirname } from 'path';
import {
  checkedGoto,
  manifestArgument,
  projectPath,
  readJsonObject,
  recordPage,
  requireKeys,
} from './video_recording.mjs';

const manifest = readJsonObject(manifestArgument(), 'video manifest');
const config = manifest.recordings?.walkthrough;
requireKeys(
  config || {},
  ['url_env', 'default_url', 'output', 'markers', 'steps'],
  'walkthrough recording',
);
if (!Array.isArray(config.steps) || !config.steps.length) {
  throw new Error('walkthrough recording must declare at least one step');
}
const url = process.env[config.url_env] || config.default_url;
const markers = [];

const output = await recordPage({
  output: config.output,
  action: async page => {
    await checkedGoto(page, url, {
      waitUntil: 'networkidle', timeout: 120000, expectedMarkers: ['Blue Toad Fleet'],
    });
    await page.waitForTimeout(1200);
    const started = Date.now();
    const mark = label => markers.push({ label, t: (Date.now() - started) / 1000 });
    const anchorY = (text, offset = 40) => page.evaluate(([needle, adjustment]) => {
      const hits = [...document.querySelectorAll('body *')]
        .filter(element => element.textContent?.toLowerCase().includes(needle.toLowerCase()));
      if (!hits.length) return null;
      let node = hits[hits.length - 1];
      while (node && node.getBoundingClientRect().width < 400) node = node.parentElement;
      return Math.max(0, node.getBoundingClientRect().top + window.scrollY - adjustment);
    }, [text, offset]);
    const glide = (target, duration) => page.evaluate(([y, milliseconds]) => new Promise(resolve => {
      const start = window.scrollY;
      const delta = y - start;
      const startedAt = performance.now();
      const ease = value => value < 0.5
        ? 4 * value ** 3
        : 1 - (-2 * value + 2) ** 3 / 2;
      (function step(now) {
        const progress = Math.min(1, (now - startedAt) / milliseconds);
        window.scrollTo(0, start + delta * ease(progress));
        progress < 1 ? requestAnimationFrame(step) : resolve();
      })(performance.now());
    }), [target, duration]);

    for (const step of config.steps) {
      requireKeys(step, ['label', 'anchor', 'glide_ms', 'hold_ms'], 'walkthrough step');
      if (step.anchor) {
        const y = await anchorY(step.anchor, Number(step.offset || 40));
        if (y === null) throw new Error(`required walkthrough anchor is missing: ${step.anchor}`);
        await glide(y, Number(step.glide_ms));
      }
      mark(step.label);
      await page.waitForTimeout(Number(step.hold_ms));
    }
    mark('end');
  },
});

const markerPath = projectPath(config.markers);
mkdirSync(dirname(markerPath), { recursive: true });
writeFileSync(markerPath, `${JSON.stringify(markers, null, 2)}\n`);
console.log(output);
console.log(JSON.stringify(markers));
