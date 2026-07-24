// Unified national → city → district map E2E flows + screenshots.
const { test, expect } = require("@playwright/test");
const path = require("path");
const SHOTS = path.join(__dirname, "screenshots");

const APP = "/frontend/index.html";
// Navigation-logic tests use the synthetic scenario: it is network-free
// (no live Open-Meteo), so state/URL/breadcrumb/district behaviour is
// deterministic and fast regardless of live-API latency.
const DEMO = APP + "?scenario=heatwave";
async function boot(page, url = APP) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(url);
  await page.waitForFunction(() => window.__waves && window.__waves.ready, null, { timeout: 30000 });
  return errors;
}
const state = (page) => page.evaluate(() => window.__waves.getState());
const regionCount = (page) => page.evaluate(() => window.__waves.regions().length);
const mapCount = (page) => page.evaluate(() => window.__waves.mapCount());

async function selectKyiv(page) {
  await page.fill("#search", "Kyiv");
  await page.waitForSelector("#searchResults .row");
  await page.click("#searchResults .row");
  await page.waitForFunction(() => window.__waves.getState().city === "kyiv");
  await page.waitForFunction(() => window.__waves.regions().length >= 10, null, { timeout: 30000 });
}

test.beforeAll(async () => {
  const fs = require("fs");
  fs.mkdirSync(SHOTS, { recursive: true });
});

test("national view loads with a single map", async ({ page }) => {
  const errors = await boot(page);
  expect(await mapCount(page)).toBe(1);
  expect((await state(page)).level).toBe("national");
  await expect(page.locator("#crumbs")).toContainText("Ukraine");
  await page.waitForTimeout(2500); // let markers/basemap settle
  await page.screenshot({ path: path.join(SHOTS, "national-desktop.png") });
  expect(errors, "no page errors: " + errors.join("; ")).toEqual([]);
});

test("select Kyiv via search: same map, 10 districts, city context", async ({ page }) => {
  await boot(page);
  await selectKyiv(page);
  expect(await mapCount(page)).toBe(1);              // NOT a second map
  expect(await regionCount(page)).toBeGreaterThanOrEqual(10);
  await expect(page.locator("#panel-body h1")).toHaveText("Kyiv");
  await expect(page.locator("#crumbs")).toContainText("Kyiv");
  const s = await state(page);
  expect(s.city).toBe("kyiv");
  expect(page.url()).toContain("city=kyiv");
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(SHOTS, "kyiv-desktop.png") });
});

test("change date + layer updates districts without recreating map", async ({ page }) => {
  await boot(page);
  await selectKyiv(page);
  const before = await mapCount(page);
  // change date
  await page.$eval("#date", (el) => { el.value = "5"; el.dispatchEvent(new Event("input", { bubbles: true })); });
  await page.waitForTimeout(1500);
  expect(page.url()).toContain("date=");
  // change layer
  await page.click('#layers button[data-l="tx95_exceedance"]');
  await page.waitForFunction(() => window.__waves.getState().layer === "tx95_exceedance");
  expect(await mapCount(page)).toBe(before);         // same single map
  expect(await regionCount(page)).toBeGreaterThanOrEqual(10);
});

test("select a district: shared panel shows detail + personal-risk CTA", async ({ page }) => {
  await boot(page);
  await selectKyiv(page);
  await page.click("#ranklist .row");                // selecting via ranking == selecting the region
  await page.waitForFunction(() => window.__waves.getState().region !== null);
  await expect(page.locator("#detail")).toBeVisible();
  await expect(page.locator("#detail")).toContainText("District heat hazard");
  expect((await state(page)).level).toBe("district");
  await expect(page.locator("#crumbs")).toContainText("Kyiv");
  expect(page.url()).toContain("region=");
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(SHOTS, "district-desktop.png") });

  // personal risk from district
  await page.click("#detail button.btn");
  await expect(page.locator("#overlay")).toBeVisible();
  await expect(page.locator("#sheet")).toContainText("district-level estimate");
  await page.click('#sheet button.btn:has-text("See my explained risk")');
  await expect(page.locator("#sheet")).toContainText("Environmental context");
});

test("breadcrumb back to Ukraine restores national view", async ({ page }) => {
  await boot(page, DEMO);
  await selectKyiv(page);
  await page.click('#crumbs a:has-text("Ukraine")');
  await page.waitForFunction(() => window.__waves.getState().level === "national");
  expect(page.url()).not.toContain("city=kyiv");
  expect(await mapCount(page)).toBe(1);
});

test("browser back/forward navigates city state", async ({ page }) => {
  await boot(page, DEMO);
  await selectKyiv(page);
  expect((await state(page)).city).toBe("kyiv");
  await page.goBack();
  await page.waitForFunction(() => window.__waves.getState().city === null);
  await page.goForward();
  await page.waitForFunction(() => window.__waves.getState().city === "kyiv");
});

test("deep district link opens district directly", async ({ page }) => {
  // discover a real region id first
  await boot(page);
  await selectKyiv(page);
  const rid = await page.evaluate(() => window.__waves.regions()[0].id);
  await boot(page, `${APP}?city=kyiv&region=${rid}&date=${await page.evaluate(()=>window.__waves.getState().date)}&layer=hazard`);
  await page.waitForFunction(() => window.__waves.getState().region !== null, null, { timeout: 30000 });
  await expect(page.locator("#detail")).toBeVisible();
  const s = await state(page);
  expect(s.city).toBe("kyiv");
  expect(s.region).toBe(rid);
});

test("synthetic heatwave scenario recolors and shows banner", async ({ page }) => {
  await boot(page);
  await page.check("#demo");
  await page.waitForFunction(() => window.__waves.getState().scenario === "heatwave");
  await expect(page.locator("#banner")).toContainText("SYNTHETIC");
  await selectKyiv(page);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SHOTS, "heatwave-desktop.png") });
});

test("mobile: bottom sheet + Kyiv + personal result", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await boot(page, DEMO);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SHOTS, "kyiv-mobile-national.png") });
  await selectKyiv(page);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SHOTS, "kyiv-mobile.png") });
  await page.click("#ranklist .row");
  await page.waitForFunction(() => window.__waves.getState().region !== null);
  await page.click("#detail button.btn");
  await expect(page.locator("#overlay")).toBeVisible();
  await page.click('#sheet button.btn:has-text("See my explained risk")');
  await expect(page.locator("#sheet")).toContainText("Environmental context");
  await page.screenshot({ path: path.join(SHOTS, "personal-result-mobile.png") });
});

test("API failure degrades without crashing", async ({ page }) => {
  await page.route("**/api/data-status", (r) => r.abort());
  const errors = await boot(page);
  await expect(page.locator("#src")).toContainText(/unreachable|Backend/i);
  expect(await mapCount(page)).toBe(1);
});
