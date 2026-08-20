import { chromium } from '/Users/scottybe/.npm/_npx/31e32ef8478fbf80/node_modules/playwright/index.mjs';

async function capture() {
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
  const url = 'https://www.auctionzip.com/cgi-bin/photopanel.cgi?listingid=4160518&feed=129&gid=0&category=0&zip=&kwd=';

  console.log(`Navigating to ${url}...`);
  try {
    await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await p.waitForTimeout(6000); // allow photo grid to load
  } catch (e) {
    console.log('Navigation notice:', e.message);
  }

  const outPath = 'docs/screenshots/00-raw-auction-gallery.png';
  await p.screenshot({ path: outPath, fullPage: false });
  console.log(`[✓] Raw AuctionZip gallery screenshot saved: ${outPath}`);

  await b.close();
}

capture().catch(console.error);
