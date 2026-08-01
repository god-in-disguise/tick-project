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
await page.locator(".tick-wordmark").first().waitFor();
await page.locator(".landing-live-stage").waitFor();
assert.equal(await page.locator(".landing-signal-row > span").count(), 3);
assert.match(
  await page.locator(".landing-product").innerText(),
  /From movement to a position in seconds\./
);
assert.equal(await page.locator(".landing-state-rail > span").count(), 4);
await page.waitForTimeout(1_000);
const landing = page.locator(".install-landing");
const landingSize = await landing.evaluate((element) => ({
  height: element.clientHeight,
  contentHeight: element.scrollHeight
}));
assert.ok(landingSize.contentHeight > landingSize.height, "Landing page has no scrollable product content");
await page.locator(".landing-learn-more").click();
await page.waitForTimeout(500);
assert.ok(await landing.evaluate((element) => element.scrollTop > 0), "Landing product link did not scroll");
await landing.evaluate((element) => {
  element.style.scrollBehavior = "auto";
  element.scrollTop = 0;
});
await page.waitForFunction(() => {
  const element = document.querySelector(".install-landing");
  return element instanceof HTMLElement && element.scrollTop <= 1;
});
const landingTabs = page.locator(".landing-market-tabs button");
for (let index = 1; index < await landingTabs.count(); index += 1) {
  const tab = landingTabs.nth(index);
  const symbol = (await tab.locator("strong").innerText()).trim();
  const startedAt = Date.now();
  await tab.click();
  const canvas = page.locator(`canvas[aria-label="${symbol} live price chart"]`);
  await canvas.waitFor({ state: "attached" });
  assert.ok(Date.now() - startedAt < 500, `${symbol} landing chart waited for another request`);
  assert.equal(await canvas.getAttribute("aria-hidden"), "false");
  assert.equal(
    await page.locator(".landing-live-stage canvas[aria-hidden='false']").count(),
    1,
    `${symbol} was blended with another landing chart`
  );
  assert.ok(await canvas.evaluate(hasVisibleCanvasPixels), `${symbol} landing chart is blank`);
}
await page.screenshot({ path: "/tmp/tick-landing.png", fullPage: true });

const desktopContext = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
  isMobile: false,
  hasTouch: false
});
const desktopPage = await desktopContext.newPage();
await desktopPage.goto("http://127.0.0.1:5173/", { waitUntil: "domcontentloaded" });
await desktopPage.locator(".desktop-handoff").waitFor();
await desktopPage.locator(".landing-live-identity > span").first().waitFor({ timeout: 10_000 });
assert.match(await desktopPage.locator(".desktop-handoff").innerText(), /CONTINUE ON IPHONE/);
assert.equal(await desktopPage.getByRole("button", { name: "Add TICK to iPhone" }).count(), 0);
await desktopPage.screenshot({ path: "/tmp/tick-desktop.png", fullPage: true });
await desktopContext.close();

await page.goto("http://127.0.0.1:5173/?app=1", { waitUntil: "domcontentloaded" });
await authenticate(page);
await page.locator(".trade-view").waitFor({ timeout: 20_000 });
const gestureGuide = page.locator(".gesture-guide");
await gestureGuide.waitFor();
assert.match(await gestureGuide.innerText(), /Swipe up\s+Go long/);
assert.match(await gestureGuide.innerText(), /Swipe left\s+Next market/);
await gestureGuide.getByRole("button", { name: "GOT IT" }).click();
assert.equal(await gestureGuide.count(), 0);
assert.equal(
  await page.evaluate(() => Object.keys(localStorage).some((key) => (
    key.startsWith("tick.gesture-guide.v1.")
    && localStorage.getItem(key) === "dismissed"
  ))),
  true
);
let wakeFailureInjected = false;
const wakeFailurePattern = /\/api\/markets\?[^#]*includeTape=true/;
const wakeFailureRoute = async (route) => {
  if (!wakeFailureInjected) {
    wakeFailureInjected = true;
    await route.abort("connectionreset");
    return;
  }
  await route.continue();
};
let liveStateAttempts = 0;
const liveStateFailurePattern = /\/api\/events$/;
const liveStateFailureRoute = async (route) => {
  liveStateAttempts += 1;
  if (liveStateAttempts === 1) {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "temporary stream interruption" })
    });
    return;
  }
  await route.continue();
};
await page.route(wakeFailurePattern, wakeFailureRoute);
await page.route(liveStateFailurePattern, liveStateFailureRoute);
await page.reload({ waitUntil: "domcontentloaded" });
await page.locator(".trade-view").waitFor({ timeout: 20_000 });
await page.waitForTimeout(1_250);
assert.equal(wakeFailureInjected, true);
assert.ok(liveStateAttempts >= 2);
assert.equal(await page.locator(".error-toast").count(), 0);
await page.unroute(wakeFailurePattern, wakeFailureRoute);
await page.unroute(liveStateFailurePattern, liveStateFailureRoute);
errors.splice(0, errors.length);
assert.equal(await page.locator(".gesture-guide").count(), 0);
await page.waitForTimeout(1_000);
await page.locator(".market-context").waitFor();
await page.locator(".tape-heat").waitFor();
await page.screenshot({ path: "/tmp/tick-trade.png", fullPage: true });
const tradeView = page.locator(".trade-view");
const tradeBox = await tradeView.boundingBox();
assert.ok(tradeBox, "Trade view has no gesture bounds");
const gestureStart = {
  x: tradeBox.x + tradeBox.width * 0.5,
  y: tradeBox.y + tradeBox.height * 0.52
};
const fixedChartStage = page.locator(".trade-scene > .chart-stage");
const chartBeforeSwipe = await fixedChartStage.boundingBox();
assert.ok(chartBeforeSwipe, "Chart has no gesture bounds");
await page.mouse.move(gestureStart.x, gestureStart.y);
await page.mouse.down();
await page.mouse.move(gestureStart.x, gestureStart.y - 64, { steps: 5 });
const pullAction = page.locator(".swipe-action-layer.swipe-action-up");
await pullAction.waitFor();
assert.match(await pullAction.innerText(), /PULL TO\s+(LONG|ADD FUNDS)/);
await page.screenshot({ path: "/tmp/tick-swipe-arm.png" });
assert.equal(
  await tradeView.evaluate((element) => element.style.getPropertyValue("--swipe-y")),
  "0px",
  "Vertical gesture moved the chart"
);
assert.notEqual(
  await tradeView.evaluate((element) => element.style.getPropertyValue("--swipe-progress")),
  "0",
  "Vertical gesture did not update its action progress"
);
const chartDuringSwipe = await fixedChartStage.boundingBox();
assert.ok(chartDuringSwipe);
assert.equal(chartDuringSwipe.y, chartBeforeSwipe.y, "Chart moved vertically during a trade gesture");
assert.equal(await fixedChartStage.evaluate((element) => getComputedStyle(element).transform), "none");
assert.equal(await page.evaluate(() => window.scrollY), 0, "Trade gesture scrolled the page");
await page.mouse.up();
await page.waitForTimeout(320);
assert.equal(await page.locator(".swipe-action-content").count(), 0);
await page.mouse.move(gestureStart.x, gestureStart.y);
await page.mouse.down();
await page.mouse.move(gestureStart.x, gestureStart.y - 120, { steps: 7 });
await page.locator(".swipe-action-layer.is-armed").waitFor();
assert.match(
  await page.locator(".swipe-action-layer.is-armed").innerText(),
  /RELEASE TO\s+(LONG|ADD FUNDS)/
);
await page.mouse.move(gestureStart.x, gestureStart.y - 100, { steps: 3 });
assert.equal(
  await page.locator(".swipe-action-layer.is-armed").count(),
  1,
  "A small reversal should not chatter across the vertical arm threshold"
);
let accidentalTradeRequests = 0;
const accidentalTradePattern = /\/api\/trade\/(quote|open)$/;
const accidentalTradeRoute = async (route) => {
  accidentalTradeRequests += 1;
  await route.abort("blockedbyclient");
};
await page.route(accidentalTradePattern, accidentalTradeRoute);
await page.mouse.up();
await page.waitForTimeout(320);
assert.equal(await page.locator(".swipe-action-content").count(), 0);
assert.equal(accidentalTradeRequests, 0, "A canceled vertical pull submitted a trade request");
assert.equal(
  await page.getByRole("heading", { name: "Deposit USDC" }).count(),
  0,
  "A canceled vertical pull opened the funding sheet"
);
await page.unroute(accidentalTradePattern, accidentalTradeRoute);

const originalMarket = await page.locator(".trade-scene .market-name-row strong").innerText();
await page.mouse.move(gestureStart.x, gestureStart.y);
await page.mouse.down();
await page.mouse.move(gestureStart.x - 24, gestureStart.y, { steps: 5 });
await page.locator(".market-swipe-preview.is-active").waitFor();
await page.screenshot({ path: "/tmp/tick-swipe-market.png" });
assert.ok(
  Number.parseFloat(await tradeView.evaluate(
    (element) => element.style.getPropertyValue("--swipe-x")
  )) < 0,
  "Horizontal market scene did not follow the pointer"
);
await page.mouse.up();
await page.waitForTimeout(380);
assert.equal(
  await page.locator(".trade-scene .market-name-row strong").innerText(),
  originalMarket,
  "Canceled horizontal gesture changed market"
);
const nextMarket = await page.locator(".market-swipe-preview").nth(1).locator(".market-name-row strong").innerText();
await page.mouse.move(gestureStart.x, gestureStart.y);
await page.mouse.down();
await page.mouse.move(gestureStart.x - 150, gestureStart.y, { steps: 8 });
await page.mouse.up();
await page.locator(".trade-scene .market-name-row strong", { hasText: nextMarket }).waitFor();
await page.waitForFunction(() => !document.querySelector(".market-swipe-preview.is-active"));
assert.equal(await page.locator(".market-swipe-preview.is-active").count(), 0);
const balanceButton = page.getByRole("button", { name: /Available balance/ });
await balanceButton.click();
await page.getByRole("heading", { name: "Deposit USDC" }).waitFor();
await page.getByRole("button", { name: "Close wallet" }).click();
await page.getByRole("button", { name: "TICK" }).click();
await page.locator(".trade-view").waitFor();
const liveCanvas = page.locator('.trade-scene canvas[aria-label$="live price chart"]');
const contextButton = page.getByRole("button", { name: "Zoom out chart" });
await contextButton.waitFor();
await page.waitForFunction(() => {
  const button = document.querySelector('button[aria-label="Zoom out chart"]');
  return button instanceof HTMLButtonElement && !button.disabled;
});
const contextTransitionStartedAt = Date.now();
await contextButton.click();
const contextCanvas = page.locator('canvas[aria-label$="one hour context chart"]');
await page.getByRole("button", { name: "Opening one hour chart" }).waitFor();
await page.getByRole("button", { name: "Zoom in chart" }).waitFor({ timeout: 3_000 });
assert.ok(
  Date.now() - contextTransitionStartedAt < 1_800,
  "One-hour chart transition exceeded the 1.2 second animation budget"
);
await page.locator(".hour-range-rail").waitFor();
await page.waitForTimeout(250);
assert.equal(await contextCanvas.getAttribute("aria-hidden"), "false");
assert.ok(await contextCanvas.evaluate(hasVisibleCanvasPixels), "One-hour context chart is blank");
assert.match(await page.locator(".context-caption").innerText(), /1H CONTEXT/);
await page.screenshot({ path: "/tmp/tick-context.png", fullPage: true });
await page.getByRole("button", { name: "Zoom in chart" }).click();
await page.getByRole("button", { name: "Returning to live chart" }).waitFor();
await page.getByRole("button", { name: "Zoom out chart" }).waitFor();
assert.equal(await liveCanvas.getAttribute("aria-hidden"), "false");
const chartStage = page.locator(".trade-scene .chart-stage");
await chartStage.dblclick({ position: { x: 180, y: 280 } });
await page.getByRole("button", { name: "Opening one hour chart" }).waitFor();
await page.getByRole("button", { name: "Zoom in chart" }).waitFor({ timeout: 3_000 });
assert.equal(await contextCanvas.getAttribute("aria-hidden"), "false");
await chartStage.dblclick({ position: { x: 180, y: 280 } });
await page.getByRole("button", { name: "Returning to live chart" }).waitFor();
await page.getByRole("button", { name: "Zoom out chart" }).waitFor();
assert.equal(await liveCanvas.getAttribute("aria-hidden"), "false");

await page.getByRole("button", { name: "Pulse" }).click();
await page.locator(".hot-market-list").waitFor();
await page.locator(".pulse-feature").waitFor();
const featuredLine = page.locator(".pulse-feature-chart .pulse-feature-line");
assert.ok((await featuredLine.getAttribute("d"))?.startsWith("M "), "Featured tape has no real path");
assert.equal(await page.locator(".pulse-feature").count(), 1);
const switchTarget = page.locator(".market-row").nth(1);
const switchSymbol = await switchTarget.locator(".market-identity strong").innerText();
const switchStartedAt = Date.now();
await switchTarget.click();
await page.locator(".market-name-row strong", { hasText: switchSymbol }).waitFor();
assert.ok(Date.now() - switchStartedAt < 1_000, "Market switch waited for a chart request");
await page.locator(`.trade-scene canvas[aria-label="${switchSymbol} live price chart"]`).waitFor();

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
await page.getByRole("button", { name: "Refresh balance" }).click();
await page.getByRole("button", { name: "Refresh balance" }).waitFor({ state: "attached" });
await page.screenshot({ path: "/tmp/tick-profile.png", fullPage: true });
await page.getByRole("button", { name: "Deposit" }).click();
await page.getByRole("heading", { name: "Deposit USDC" }).waitFor();
const depositAddress = page.locator(".wallet-address-full > span");
assert.match(await depositAddress.innerText(), /^0x[0-9a-fA-F]{40}$/);
await page.getByRole("button", { name: "Copy deposit address" }).click();
await page.getByRole("button", { name: "Address copied" }).waitFor();
await page.getByRole("button", { name: "Close wallet" }).click();
const presetSummary = page.locator(".preset-summary");
assert.match(await presetSummary.innerText(), /LOSS LIMIT\s+Off/i);
await presetSummary.click();
await page.locator(".preset-sheet").waitFor();
await page.waitForTimeout(250);
const fixedAmount = page.getByRole("button", { name: "$10", exact: true }).first();
const minimumAmount = page.getByRole("button", { name: "MIN", exact: true });
const customAmount = page.getByRole("button", { name: "CUSTOM", exact: true });
await minimumAmount.click();
assert.ok((await minimumAmount.getAttribute("class"))?.includes("active"));
await customAmount.click();
assert.ok((await customAmount.getAttribute("class"))?.includes("active"));
const customAmountInput = page.getByRole("spinbutton", { name: "Custom amount" });
await customAmountInput.fill("12.34");
assert.equal(await customAmountInput.inputValue(), "12.34");
await fixedAmount.click();
assert.ok((await fixedAmount.getAttribute("class"))?.includes("active"));
const leverageGroup = page.getByRole("group", { name: "Leverage" });
const leverage100 = leverageGroup.getByRole("button", { name: "100x" });
const leverage500 = leverageGroup.getByRole("button", { name: "500x" });
await leverage100.click();
assert.equal(await leverage100.getAttribute("aria-pressed"), "true");
await leverage500.click();
assert.equal(await leverage500.getAttribute("aria-pressed"), "true");
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
  if (await devicePage.locator(".gesture-guide").isVisible()) {
    await devicePage.getByRole("button", { name: "GOT IT" }).click();
  }
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
  const expectedBottomGap = Math.max(9, device.safeBottom - 10);
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
