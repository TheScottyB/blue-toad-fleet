import { mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, statSync } from 'fs';
import { dirname, join } from 'path';
import { tmpdir } from 'os';
import { chromium } from 'playwright';
import { checkedGoto, projectPath } from './video_recording.mjs';

const url = process.env.BTF_URL || 'https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app';
const shots = [
  ['01-gate-console', null, 24],
  ['02-walk-membership', 'Walk membership', 48],
  ['03-curator-challenge', "Curator's read", 48],
  ['04-memory-and-questions', 'Answered from memory', 48],
  ['05-the-sheet', 'The sheet', 48],
  ['06-skip-reasoning', 'not on this envelope', 48],
];
const browser = await chromium.launch({ channel: 'chrome' });
const runDirectory = mkdtempSync(join(tmpdir(), 'blue-toad-shots-'));
const completed = [];
try {
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  });
  await checkedGoto(page, url, {
    waitUntil: 'networkidle', timeout: 120000, expectedMarkers: ['Blue Toad Fleet'],
  });
  for (const [name, anchor, offset] of shots) {
    if (anchor) {
      const y = await page.evaluate(([text, adjustment]) => {
        const fold = value => value.toLowerCase().replace(/[\u2018\u2019\u201A\u201B]/g, "'");
        const needle = fold(text);
        const heading = [...document.querySelectorAll('h1,h2,h3,h4,.pitch-hd,.stage-kicker')]
          .find(element => fold(element.textContent || '').includes(needle));
        let node = heading || [...document.querySelectorAll('body *')].find(element => {
          const own = fold(element.textContent || '');
          if (!own.includes(needle)) return false;
          return ![...element.children].some(child => fold(child.textContent || '').includes(needle));
        });
        if (!node) return null;
        while (node && node.getBoundingClientRect().width < 400) node = node.parentElement;
        return Math.max(0, node.getBoundingClientRect().top + window.scrollY - adjustment);
      }, [anchor, offset]);
      if (y === null) throw new Error(`required screenshot anchor is missing: ${anchor}`);
      await page.evaluate(value => scrollTo(0, value), y);
      await page.waitForTimeout(400);
    }
    const destination = projectPath(`docs/screenshots/${name}.png`);
    const partial = join(runDirectory, `${name}.png`);
    mkdirSync(dirname(destination), { recursive: true });
    await page.screenshot({ path: partial });
    const bytes = readFileSync(partial);
    if (statSync(partial).size < 100 || !bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) {
      throw new Error(`invalid screenshot output: ${name}`);
    }
    completed.push([partial, destination]);
  }
  for (const [partial, destination] of completed) {
    renameSync(partial, destination);
    console.log(`wrote ${destination}`);
  }
} finally {
  rmSync(runDirectory, { recursive: true, force: true });
  await browser.close();
}
