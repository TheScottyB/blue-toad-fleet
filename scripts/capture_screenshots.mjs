import { mkdirSync, renameSync, rmSync } from 'fs';
import { dirname } from 'path';
import { chromium } from 'playwright';
import { checkedGoto, projectPath } from './video_recording.mjs';

const url = process.env.BTF_URL || 'https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app';
const shots = [
  ['01-gate-console', null, 24],
  ['02-showroom-topology', 'POLE BARN SHOWROOM TOPOLOGY', 24],
  ['03-curator-challenge', "Curator's Negotiation", 24],
  ['04-memory-and-questions', 'ANSWERED FROM MEMORY', 24],
  ['05-the-sheet', 'BT-001', 150],
  ['06-skip-reasoning', 'BT-003', 80],
];
const browser = await chromium.launch({ channel: 'chrome' });
try {
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  });
  await checkedGoto(page, url, { waitUntil: 'networkidle', timeout: 120000 });
  for (const [name, anchor, offset] of shots) {
    if (anchor) {
      const y = await page.evaluate(([text, adjustment]) => {
        const hits = [...document.querySelectorAll('body *')]
          .filter(element => element.textContent?.toLowerCase().includes(text.toLowerCase()));
        if (!hits.length) return null;
        let node = hits[hits.length - 1];
        while (node && node.getBoundingClientRect().width < 400) node = node.parentElement;
        return Math.max(0, node.getBoundingClientRect().top + window.scrollY - adjustment);
      }, [anchor, offset]);
      if (y === null) throw new Error(`required screenshot anchor is missing: ${anchor}`);
      await page.evaluate(value => scrollTo(0, value), y);
      await page.waitForTimeout(400);
    }
    const destination = projectPath(`docs/screenshots/${name}.png`);
    const partial = projectPath(`docs/screenshots/.${name}.partial.png`);
    mkdirSync(dirname(destination), { recursive: true });
    try {
      await page.screenshot({ path: partial });
      renameSync(partial, destination);
      console.log(`wrote ${destination}`);
    } finally {
      rmSync(partial, { force: true });
    }
  }
} finally {
  await browser.close();
}
