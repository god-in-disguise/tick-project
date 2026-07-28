import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true
});
const page = await browser.newPage({
  viewport: { width: 430, height: 932 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true
});
const errors = [];
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});
page.on("pageerror", (error) => errors.push(error.message));

await page.goto("http://127.0.0.1:5173/", { waitUntil: "networkidle" });
await page.locator(".install-landing").waitFor();
assert.match(await page.locator("h1").innerText(), /Catch what is moving now/);
await page.screenshot({ path: "/tmp/tick-landing.png", fullPage: true });

await page.goto("http://127.0.0.1:5173/?app=1", { waitUntil: "domcontentloaded" });
await page.locator(".trade-view").waitFor({ timeout: 20_000 });
await page.waitForTimeout(1_000);
await page.screenshot({ path: "/tmp/tick-trade.png", fullPage: true });

await page.getByRole("button", { name: "Me" }).click();
await page.locator(".profile-page").waitFor();
await page.screenshot({ path: "/tmp/tick-profile.png", fullPage: true });

const overflow = await page.evaluate(() => ({
  x: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  y: document.documentElement.scrollHeight - document.documentElement.clientHeight
}));
assert.equal(overflow.x, 0);
assert.equal(overflow.y, 0);
assert.deepEqual(errors, []);

await browser.close();
console.log("PWA smoke passed");
