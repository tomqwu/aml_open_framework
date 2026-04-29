/**
 * Snapshot every scene at peak (after its in-scene animations land).
 * Scenes self-advance via the page's tick(); we just hold and capture.
 */
import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const HTML = 'file://' + path.join(__dirname, 'board-video.html');

// Capture seconds chosen so each scene is 1.5–2.5s past its own start
// (longest in-scene anim chain finishes ~2.2s after activation).
const CAPTURES = [
  { t: 3.0,  out: 'frame-1-cover.png' },
  { t: 9.5,  out: 'frame-2-rule.png' },
  { t: 18.0, out: 'frame-3-cost.png' },
  { t: 26.0, out: 'frame-4-quotes.png' },
  { t: 36.0, out: 'frame-5-thesis.png' },
  { t: 43.5, out: 'frame-6-changes.png' },
  { t: 52.5, out: 'frame-7-numbers.png' },
  { t: 59.0, out: 'frame-8-close.png' },
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const page = await ctx.newPage();
await page.goto(HTML, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.__ready === true, { timeout: 8000 });
const startedAt = Date.now();

for (const cap of CAPTURES) {
  const target = startedAt + cap.t * 1000;
  const wait = target - Date.now();
  if (wait > 0) await page.waitForTimeout(wait);
  await page.screenshot({ path: path.join(__dirname, cap.out), fullPage: false });
  console.log('→', cap.out, `at t=${cap.t}s`);
}

await browser.close();
