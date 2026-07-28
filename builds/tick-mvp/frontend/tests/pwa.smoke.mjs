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

const iphonePortraitViewports = [
  { name: "iphone-11-pro", width: 375, height: 812, safeTop: 44 },
  { name: "iphone-11-pro-max", width: 414, height: 896, safeTop: 44 },
  { name: "iphone-12-14", width: 390, height: 844, safeTop: 47 },
  { name: "iphone-14-15-pro-max", width: 430, height: 932, safeTop: 59 },
  { name: "iphone-16-17-pro", width: 402, height: 874, safeTop: 62 },
  { name: "iphone-16-17-pro-max", width: 440, height: 956, safeTop: 62 }
];

for (const device of iphonePortraitViewports) {
  const context = await browser.newContext({
    viewport: { width: device.width, height: device.height },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true
  });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, "standalone", {
      configurable: true,
      value: true
    });
  });
  const devicePage = await context.newPage();
  await devicePage.goto("http://127.0.0.1:5173/", { waitUntil: "domcontentloaded" });
  await devicePage.locator(".trade-view").waitFor({ timeout: 20_000 });
  await devicePage.addStyleTag({
    content: `:root { --safe-area-top: ${device.safeTop}px !important; --safe-area-bottom: 34px !important; }`
  });
  const geometry = await devicePage.evaluate(() => {
    const nav = document.querySelector(".bottom-nav")?.getBoundingClientRect();
    const dock = document.querySelector(".execution-dock")?.getBoundingClientRect();
    return {
      viewportHeight: window.innerHeight,
      navTop: nav?.top ?? 0,
      navBottom: nav?.bottom ?? 0,
      dockBottom: dock?.bottom ?? 0,
      overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      overflowY: document.documentElement.scrollHeight - document.documentElement.clientHeight
    };
  });
  const bottomGap = geometry.viewportHeight - geometry.navBottom;
  assert.ok(bottomGap >= 20 && bottomGap <= 24, `${device.name}: bottom gap ${bottomGap}`);
  assert.ok(geometry.navTop >= geometry.dockBottom, `${device.name}: navigation overlaps execution dock`);
  assert.equal(geometry.overflowX, 0, `${device.name}: horizontal overflow`);
  assert.equal(geometry.overflowY, 0, `${device.name}: vertical overflow`);
  await context.close();
}

await browser.close();
console.log("PWA smoke passed");
