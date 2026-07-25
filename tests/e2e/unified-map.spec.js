// Unified map + heatwave engine E2E flows + screenshots.
// Historical & synthetic modes are network-free (precomputed / demo) so these
// flows are deterministic and fast regardless of live Open-Meteo latency.
const { test, expect } = require("@playwright/test");
const path = require("path");
const SHOTS = path.join(__dirname, "screenshots");
const APP = "/frontend/index.html";
const HIST = APP + "?mode=historical";
const SYN = APP + "?mode=synthetic";

async function boot(page, url = APP) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(url);
  await page.waitForFunction(() => window.__waves && window.__waves.ready, null, { timeout: 30000 });
  return errors;
}
const state = (p) => p.evaluate(() => window.__waves.getState());
const mapCount = (p) => p.evaluate(() => window.__waves.mapCount());

async function activateKyiv(page) {
  await page.fill("#search", "Kyiv");
  await page.waitForSelector("#searchResults .row");
  await page.click("#searchResults .row");
  await page.waitForFunction(() => window.__waves.getState().city === "kyiv");
  await page.waitForFunction(() => window.__waves.regions().length >= 10, null, { timeout: 30000 });
}

test.beforeAll(() => require("fs").mkdirSync(SHOTS, { recursive: true }));

test("severity legend shows five distinct levels", async ({ page }) => {
  const errors = await boot(page, HIST);
  await page.waitForFunction(() => document.querySelectorAll("#legend div").length >= 5);
  const labels = await page.$$eval("#legend div", (ds) => ds.map((d) => d.textContent));
  for (const name of ["No heatwave", "Heatwave watch", "Confirmed heatwave", "Severe heatwave", "Extreme heatwave"]) {
    expect(labels.join(" ")).toContain(name);
  }
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(SHOTS, "legend-historical.png") });
  expect(errors).toEqual([]);
});

test("historical replay: real ERA5 event, one map, timeline", async ({ page }) => {
  await boot(page, HIST);
  const s = await state(page);
  expect(s.mode).toBe("historical");
  expect(s.event).toMatch(/^era5-/);
  expect(await mapCount(page)).toBe(1);
  await expect(page.locator("#banner")).toContainText("HISTORICAL");
  await expect(page.locator("#headline")).toContainText("Observed heatwave");
  const cells = await page.$$eval(".tlcell", (c) => c.length);
  expect(cells).toBeGreaterThan(3);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SHOTS, "historical-desktop.png") });
});

test("timeline playback advances the date without recreating the map", async ({ page }) => {
  await boot(page, HIST);
  const before = await state(page);
  const m0 = await mapCount(page);
  await page.click("#tlbtn");                       // play
  await page.waitForFunction((d0) => window.__waves.getState().date !== d0,
    before.date, { timeout: 10000 });
  await page.click("#tlbtn");                       // pause
  expect(await mapCount(page)).toBe(m0);
});

test("synthetic mode is clearly labelled synthetic", async ({ page }) => {
  await boot(page, SYN);
  await expect(page.locator("#banner")).toContainText("SYNTHETIC");
  expect((await state(page)).mode).toBe("synthetic");
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(SHOTS, "synthetic-desktop.png") });
});

test("synthetic mode: confirmed footprint headline on a heatwave day", async ({ page }) => {
  await boot(page, SYN);
  // the synthetic heatwave peaks on days 3-6; step the timeline into it
  await page.waitForSelector(".tlcell");
  await page.$$eval(".tlcell", (cells) => cells[4] && cells[4].click());
  await page.waitForFunction(() => window.__waves.summary() && window.__waves.summary().status === "confirmed",
    null, { timeout: 30000 });
  await expect(page.locator("#headline")).toContainText(/confirmed heatwave footprint/i);
});

test("Kyiv districts: affected fractions + severity (synthetic, deterministic)", async ({ page }) => {
  await boot(page, SYN);
  await activateKyiv(page);
  expect(await mapCount(page)).toBe(1);
  await page.click("#ranklist .row");
  await page.waitForFunction(() => window.__waves.getState().region !== null);
  await expect(page.locator("#detail")).toContainText("sampled district cells");
  await expect(page.locator("#detail")).toContainText(/Max district level/i);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(SHOTS, "kyiv-district-synthetic.png") });
  // personal risk from district
  await page.click("#detail button.btn");
  await expect(page.locator("#overlay")).toBeVisible();
  await expect(page.locator("#sheet")).toContainText("district-level estimate");
  await page.click('#sheet button.btn:has-text("See my explained risk")');
  await expect(page.locator("#sheet")).toContainText("Environmental context");
});

test("mode selector switches live <-> historical, URL persists", async ({ page }) => {
  await boot(page, HIST);
  await page.click('#modes button[data-m="live"]');
  await page.waitForFunction(() => window.__waves.getState().mode === "live");
  expect(page.url()).not.toContain("mode=historical");
  await page.click('#modes button[data-m="historical"]');
  await page.waitForFunction(() => window.__waves.getState().mode === "historical");
  expect(page.url()).toContain("mode=historical");
});

test("live mode loads and reports an honest state", async ({ page }) => {
  await boot(page, APP);
  expect((await state(page)).mode).toBe("live");
  await page.waitForFunction(() => window.__waves.summary() !== null, null, { timeout: 45000 });
  const st = await page.evaluate(() => window.__waves.summary().status);
  expect(["no_event", "watch", "confirmed"]).toContain(st);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SHOTS, "live-desktop.png") });
});

test("browser back/forward across modes", async ({ page }) => {
  await boot(page, HIST);
  await activateKyiv(page).catch(() => {});   // may use live; tolerate
  const hadCity = (await state(page)).city;
  if (hadCity) {
    await page.goBack();
    await page.waitForFunction(() => window.__waves.getState().city === null, null, { timeout: 15000 });
  }
  expect(await mapCount(page)).toBe(1);
});

test("mobile: timeline + legend visible, historical replay", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await boot(page, HIST);
  await page.waitForTimeout(2000);
  await expect(page.locator("#timeline")).toBeVisible();
  await expect(page.locator("#legend")).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, "historical-mobile.png") });
});

test("API failure degrades without crashing", async ({ page }) => {
  await page.route("**/api/data-status", (r) => r.abort());
  await boot(page, HIST);
  await expect(page.locator("#src")).toContainText(/unreachable|Backend/i);
  expect(await mapCount(page)).toBe(1);
});
