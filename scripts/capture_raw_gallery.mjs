import { chromium } from 'playwright';
import { execSync } from 'child_process';
import { existsSync } from 'fs';

async function capture() {
  if (!existsSync('/tmp/gallery_local.html')) {
    console.log('Generating /tmp/gallery_local.html...');
    execSync('python3 scripts/build_local_gallery.py', { stdio: 'inherit' });
  }

  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
  const url = process.env.BTF_GALLERY || 'file:///tmp/gallery_local.html';

  console.log(`Navigating to ${url}...`);
  await p.goto(url, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(3000); // allow photo grid to load

  const outPath = 'docs/screenshots/00-raw-auction-gallery.png';
  await p.screenshot({ path: outPath, fullPage: false });
  console.log(`[✓] Raw AuctionZip gallery screenshot saved: ${outPath}`);

  await b.close();
}

capture().catch(console.error);

