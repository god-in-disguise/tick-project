import assert from "node:assert/strict";
import { chromium } from "playwright";

const inviteCode = process.env.TICK_SMOKE_INVITE_CODE;
assert.ok(inviteCode, "TICK_SMOKE_INVITE_CODE is required");

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

await page.goto("http://127.0.0.1:5173/", { waitUntil: "domcontentloaded" });
await page.locator(".install-landing").waitFor();
assert.match(await page.locator("h1").innerText(), /Catch what is moving now/);
await page.locator(".tick-wordmark").waitFor();
await page.locator(".landing-live-stage").waitFor();
await page.waitForTimeout(1_000);
const landingTabs = page.locator(".landing-market-tabs button");
for (let index = 1; index < await landingTabs.count(); index += 1) {
  const tab = landingTabs.nth(index);
  const symbol = (await tab.locator("strong").innerText()).trim();
  const startedAt = Date.now();
  await tab.click();
  const canvas = page.locator(`canvas[aria-label="${symbol} live price chart"]`);
  await canvas.waitFor();
  assert.ok(Date.now() - startedAt < 500, `${symbol} landing chart waited for another request`);
  assert.ok(await canvas.evaluate(hasVisibleCanvasPixels), `${symbol} landing chart is blank`);
}
await page.screenshot({ path: "/tmp/tick-landing.png", fullPage: true });

await page.goto("http://127.0.0.1:5173/?app=1", { waitUntil: "domcontentloaded" });
await authenticate(page);
await page.locator(".trade-view").waitFor({ timeout: 20_000 });
await page.waitForTimeout(1_000);
await page.locator(".market-context").waitFor();
await page.locator(".tape-heat").waitFor();
await page.screenshot({ path: "/tmp/tick-trade.png", fullPage: true });

await page.getByRole("button", { name: "Pulse" }).click();
await page.locator(".hot-market-list").waitFor();
const switchTarget = page.locator(".market-row").nth(1);
const switchSymbol = await switchTarget.locator(".market-identity strong").innerText();
const switchStartedAt = Date.now();
await switchTarget.click();
await page.locator(".market-name-row strong", { hasText: switchSymbol }).waitFor();
assert.ok(Date.now() - switchStartedAt < 1_000, "Market switch waited for a chart request");
await page.locator(`canvas[aria-label="${switchSymbol} live price chart"]`).waitFor();

await page.getByRole("button", { name: "Pulse" }).click();
await page.locator(".hot-market-list").waitFor();
assert.ok(await page.locator(".hot-market-list .tape-heat").count() > 0);
assert.equal(
  await page.locator(".page").evaluate((element) => element.scrollWidth - element.clientWidth),
  0,
  "Pulse has horizontal overflow"
);
await page.screenshot({ path: "/tmp/tick-pulse.png", fullPage: true });

await page.getByRole("button", { name: "Me" }).click();
await page.locator(".profile-page").waitFor();
assert.notEqual(await page.locator(".profile-page .page-header h1").innerText(), "Me");
assert.equal(await page.locator(".profile-page .page-header > svg").count(), 0);
await page.screenshot({ path: "/tmp/tick-profile.png", fullPage: true });
await page.getByRole("button", { name: "Deposit" }).click();
await page.getByRole("heading", { name: "Deposit USDC" }).waitFor();
const depositAddress = page.locator(".wallet-address-full > span");
assert.match(await depositAddress.innerText(), /^0x[0-9a-fA-F]{40}$/);
await page.getByRole("button", { name: "Copy deposit address" }).click();
await page.getByRole("button", { name: "Address copied" }).waitFor();
await page.getByRole("button", { name: "Close wallet" }).click();
await page.locator(".preset-summary").click();
await page.locator(".preset-sheet").waitFor();
await page.waitForTimeout(250);
const takeProfitGroup = page.getByRole("group", { name: "Take profit" });
const takeProfitOff = takeProfitGroup.getByRole("button", { name: "Off" });
const takeProfitTen = takeProfitGroup.getByRole("button", { name: "Take profit $10" });
await takeProfitGroup.scrollIntoViewIfNeeded();
const originalTakeProfit = await takeProfitTen.getAttribute("aria-pressed");
await takeProfitTen.click();
assert.equal(await takeProfitTen.getAttribute("aria-pressed"), "true");
await page.screenshot({ path: "/tmp/tick-preset.png" });
if (originalTakeProfit !== "true") await takeProfitOff.click();
await page.getByRole("button", { name: "Close preset" }).click();

const overflow = await page.evaluate(() => ({
  x: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  y: document.documentElement.scrollHeight - document.documentElement.clientHeight
}));
assert.equal(overflow.x, 0);
assert.equal(overflow.y, 0);
assert.deepEqual(errors, []);

const iphonePortraitViewports = [
  { name: "iphone-se", width: 375, height: 667, safeTop: 20, safeBottom: 0 },
  { name: "iphone-11-pro", width: 375, height: 812, safeTop: 44, safeBottom: 34 },
  { name: "iphone-11-pro-max", width: 414, height: 896, safeTop: 44, safeBottom: 34 },
  { name: "iphone-12-14", width: 390, height: 844, safeTop: 47, safeBottom: 34 },
  { name: "iphone-14-pro", width: 393, height: 852, safeTop: 59, safeBottom: 34 },
  { name: "iphone-14-15-pro-max", width: 430, height: 932, safeTop: 59, safeBottom: 34 },
  { name: "iphone-16-17-pro", width: 402, height: 874, safeTop: 62, safeBottom: 34 },
  { name: "iphone-16-17-pro-max", width: 440, height: 956, safeTop: 62, safeBottom: 34 }
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
  await authenticate(devicePage);
  await devicePage.locator(".trade-view").waitFor({ timeout: 20_000 });
  await devicePage.addStyleTag({
    content: `:root { --safe-area-top: ${device.safeTop}px !important; --safe-area-bottom: ${device.safeBottom}px !important; }`
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
  const expectedBottomGap = device.safeBottom + 8;
  assert.ok(
    Math.abs(bottomGap - expectedBottomGap) <= 2,
    `${device.name}: bottom gap ${bottomGap}, expected ${expectedBottomGap}`
  );
  assert.ok(geometry.navTop >= geometry.dockBottom, `${device.name}: navigation overlaps execution dock`);
  assert.equal(geometry.overflowX, 0, `${device.name}: horizontal overflow`);
  assert.equal(geometry.overflowY, 0, `${device.name}: vertical overflow`);
  if (device.name === "iphone-14-15-pro-max") {
    await devicePage.getByRole("button", { name: "Me" }).click();
    const profile = devicePage.locator(".profile-page");
    await profile.waitFor();
    await profile.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });
    const profileGeometry = await devicePage.evaluate(() => {
      const nav = document.querySelector(".bottom-nav")?.getBoundingClientRect();
      const lastSetting = document.querySelector(".account-facts > div:last-child")?.getBoundingClientRect();
      return {
        navTop: nav?.top ?? 0,
        lastSettingBottom: lastSetting?.bottom ?? 0
      };
    });
    assert.ok(
      profileGeometry.lastSettingBottom < profileGeometry.navTop,
      "Profile settings cannot scroll above navigation"
    );
    await devicePage.screenshot({ path: "/tmp/tick-iphone-pro-max.png" });
  }
  await context.close();
}

await browser.close();
console.log("PWA smoke passed");

async function authenticate(page) {
  await page.locator(".trade-view, .auth-gate").first().waitFor({ timeout: 20_000 });
  if (await page.locator(".auth-gate").isVisible()) {
    await page.getByPlaceholder("Invite code").fill(inviteCode);
    await page.getByRole("button", { name: "Enter TICK" }).click();
  }
}

function hasVisibleCanvasPixels(canvas) {
  const context = canvas.getContext("2d");
  if (!context || canvas.width < 2 || canvas.height < 2) return false;
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
  const first = [pixels[0], pixels[1], pixels[2], pixels[3]];
  for (let index = 4; index < pixels.length; index += 32) {
    if (
      pixels[index] !== first[0]
      || pixels[index + 1] !== first[1]
      || pixels[index + 2] !== first[2]
      || pixels[index + 3] !== first[3]
    ) {
      return true;
    }
  }
  return false;
}
