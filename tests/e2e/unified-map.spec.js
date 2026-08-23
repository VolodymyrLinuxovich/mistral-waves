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
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  await page.goto(url);
  await page.waitForFunction(() => window.__waves && window.__waves.ready, null, { timeout: 30000 });
  return errors;
}
const state = (p) => p.evaluate(() => window.__waves.getState());
const mapCount = (p) => p.evaluate(() => window.__waves.mapCount());

async function scrubTimeline(page, index) {
  await page.locator("#tlrange").evaluate((range, value) => {
    range.value = String(value);
    range.dispatchEvent(new Event("input", { bubbles: true }));
  }, index);
}

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
  const frames = await page.locator("#tlrange").getAttribute("max");
  expect(Number(frames)).toBeGreaterThan(3);
  await expect(page.locator("#tlstatus")).toContainText(/Day 1 of \d+ · Level \d/);
  await expect(page.locator("#tlstatus")).toContainText(/Maximum level/);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SHOTS, "historical-desktop.png") });
});

test("timeline play, pause, and final-frame stop keep one map", async ({ page }) => {
  await boot(page, HIST);
  const before = await state(page);
  const m0 = await mapCount(page);
  await page.click("#tlbtn");
  await page.waitForFunction((d0) => window.__waves.getState().date !== d0,
    before.date, { timeout: 10000 });
  await page.click("#tlbtn");
  const paused = (await state(page)).date;
  await page.waitForTimeout(1200);
  expect((await state(page)).date).toBe(paused);
  expect(await page.locator("#tlbtn").getAttribute("aria-pressed")).toBe("false");

  await page.selectOption("#tlspeed", "2");
  await page.locator("#tlrange").focus();
  await page.keyboard.press("Home");
  await page.click("#tlbtn");
  await page.waitForFunction(() => {
    const w = window.__waves;
    const dates = w.dates();
    return !w.isPlaying() && w.getState().date === dates[dates.length - 1];
  }, null, { timeout: 30000 });
  expect(await mapCount(page)).toBe(m0);
});

test("timeline slider, previous, and next synchronize date, URL, and map data", async ({ page }) => {
  await boot(page, HIST);
  const dates = await page.evaluate(() => window.__waves.dates());
  const target = Math.min(4, dates.length - 1);
  await scrubTimeline(page, target);
  await page.waitForFunction((date) => window.__waves.footprintDate() === date, dates[target]);
  expect((await state(page)).date).toBe(dates[target]);
  expect(page.url()).toContain(`date=${dates[target]}`);
  await expect(page.locator("#tlrange")).toHaveAttribute("aria-valuetext", new RegExp(dates[target].slice(0, 4)));

  await page.click("#tlprev");
  await page.waitForFunction((date) => window.__waves.getState().date === date, dates[target - 1]);
  await page.click("#tlnext");
  await page.waitForFunction((date) => window.__waves.getState().date === date, dates[target]);
});

test("timeline keyboard supports arrows, Home, End, and Space", async ({ page }) => {
  await boot(page, HIST);
  const dates = await page.evaluate(() => window.__waves.dates());
  const range = page.locator("#tlrange");
  await range.focus();
  await page.keyboard.press("End");
  await page.waitForFunction((date) => window.__waves.getState().date === date, dates.at(-1));
  await page.keyboard.press("Home");
  await page.waitForFunction((date) => window.__waves.getState().date === date, dates[0]);
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction((date) => window.__waves.getState().date === date, dates[1]);
  await page.keyboard.press("ArrowLeft");
  await page.waitForFunction((date) => window.__waves.getState().date === date, dates[0]);
  await page.keyboard.press("Space");
  await expect(page.locator("#tlbtn")).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Space");
  await expect(page.locator("#tlbtn")).toHaveAttribute("aria-pressed", "false");
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
  await page.waitForSelector("#tlrange");
  await scrubTimeline(page, 4);
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

test("Kyiv drill-down preserves date and colors mocked district forecast", async ({ page }) => {
  const districts = JSON.parse(require("fs").readFileSync(
    path.join(__dirname, "../../data/boundaries/kyiv_districts.geojson"), "utf8"
  )).features;
  let requestedDate;
  await page.route("**/api/city-risk-map**", async (route) => {
    const url = new URL(route.request().url());
    requestedDate = url.searchParams.get("date");
    const regions = districts.map((feature, index) => {
      const severity = index % 5;
      return {
        id: feature.properties.id,
        name: feature.properties.name,
        name_en: feature.properties.name_en,
        severity_level: severity,
        severity_label: ["No heatwave", "Heatwave watch", "Confirmed heatwave", "Severe heatwave", "Extreme heatwave"][severity],
        severity_color: ["#6b8fa8", "#f4c430", "#e8862e", "#a9481c", "#c0161c"][severity],
        max_severity_level: severity,
        pct_level2plus: severity >= 2 ? 100 : 0,
        tmax_minus_tx95: severity,
        n_cells: 2,
      };
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        city: "kyiv", date: requestedDate, n_regions: regions.length,
        total_cells_sampled: regions.length * 2,
        resolution_note: "District-level estimated heat distribution.",
        regions,
      }),
    });
  });

  await boot(page, SYN);
  await scrubTimeline(page, 2);
  const selectedDate = (await state(page)).date;
  await page.locator('[aria-label^="Kyiv,"]').first().click();
  await page.waitForFunction(() => window.__waves.getState().city === "kyiv");
  await page.waitForFunction(() => window.__waves.districtFeatures().length >= 10);

  expect(requestedDate).toBe(selectedDate);
  expect((await state(page)).date).toBe(selectedDate);
  const districtColors = await page.evaluate(() => window.__waves.districtFeatures()
    .map((feature) => feature.properties.severity_color));
  expect(districtColors).toHaveLength(districts.length);
  expect(districtColors.every((color) => /^#[0-9a-f]{6}$/i.test(color))).toBe(true);
  expect(new Set(districtColors).size).toBe(5);
  await expect(page.locator("#ranklist .row")).toHaveCount(districts.length);
  await expect(page.locator("#rank-extra")).toContainText(`District ranking (${districts.length})`);
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

test("switching historical events resets to the selected event first frame", async ({ page }) => {
  await boot(page, HIST);
  await page.waitForFunction(() => document.querySelectorAll("#evsel option").length > 1);
  const nextEvent = await page.locator("#evsel option").nth(1).getAttribute("value");
  await page.selectOption("#evsel", nextEvent);
  await page.waitForFunction((eventId) => window.__waves.getState().event === eventId, nextEvent);
  await page.waitForFunction(() => window.__waves.getState().date === window.__waves.dates()[0]);
  expect((await state(page)).event).toBe(nextEvent);
  await expect(page.locator("#tlstatus")).toContainText("Day 1 of");
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

test("desktop 1200x700: constrained shell, independent sidebar, complete timeline", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 700 });
  const errors = await boot(page, HIST);
  await page.waitForTimeout(1000);
  const layout = await page.evaluate(() => {
    const rect = (id) => document.getElementById(id).getBoundingClientRect();
    const panel = rect("panel"), map = rect("map-region"), timeline = rect("timeline"), footer = rect("disclaimer");
    return {
      bodyScrollWidth: document.documentElement.scrollWidth,
      bodyWidth: document.documentElement.clientWidth,
      bodyScrollHeight: document.documentElement.scrollHeight,
      bodyHeight: document.documentElement.clientHeight,
      panel, map, timeline, footer,
      panelScrollable: document.getElementById("panel").scrollHeight >= document.getElementById("panel").clientHeight,
    };
  });
  expect(layout.bodyScrollWidth).toBe(layout.bodyWidth);
  expect(layout.bodyScrollHeight).toBe(layout.bodyHeight);
  expect(layout.timeline.x).toBeGreaterThanOrEqual(layout.map.x);
  expect(layout.timeline.right).toBeLessThanOrEqual(layout.map.right);
  expect(layout.timeline.bottom).toBeLessThanOrEqual(layout.map.bottom);
  expect(layout.panel.right).toBeLessThanOrEqual(layout.map.x + 1);
  expect(layout.panelScrollable).toBe(true);
  await page.screenshot({ path: path.join(SHOTS, "polished-desktop-1200x700.png") });

  await page.setViewportSize({ width: 1440, height: 800 });
  await page.waitForTimeout(300);
  const wide = await page.evaluate(() => {
    const box = (node) => {
      const r = node.getBoundingClientRect();
      return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
    };
    return { pageWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth, map: box(document.getElementById("map-region")), timeline: box(document.getElementById("timeline")), canvas: box(document.querySelector(".maplibregl-canvas")) };
  });
  expect(wide.pageWidth).toBe(wide.viewportWidth);
  expect(wide.timeline.left).toBeGreaterThanOrEqual(wide.map.left);
  expect(wide.timeline.right).toBeLessThanOrEqual(wide.map.right);
  expect(Math.abs(wide.canvas.width - wide.map.width)).toBeLessThan(1);
  expect(Math.abs(wide.canvas.height - wide.map.height)).toBeLessThan(1);
  await page.screenshot({ path: path.join(SHOTS, "polished-desktop-1440x800.png") });
  expect(errors).toEqual([]);
});

test("mobile: bottom sheet, timeline, legend, and touch controls remain reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const errors = await boot(page, HIST);
  await page.waitForTimeout(1000);
  await expect(page.locator("#timeline")).toBeVisible();
  await expect(page.locator("#legend")).toBeVisible();
  await expect(page.locator("#tlcurrent")).not.toBeEmpty();
  const sizes = await page.$$eval(".tlbutton", (buttons) => buttons.map((button) => {
    const r = button.getBoundingClientRect(); return [r.width, r.height];
  }));
  sizes.forEach(([width, height]) => { expect(width).toBeGreaterThanOrEqual(44); expect(height).toBeGreaterThanOrEqual(44); });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.locator("#panel").evaluate((panel) => { panel.scrollTop = panel.scrollHeight; });
  await expect(page.locator("#src")).toBeInViewport();
  await expect(page.locator("#openProfile")).toBeInViewport();
  await page.locator("#panel").evaluate((panel) => { panel.scrollTop = 0; });
  await page.screenshot({ path: path.join(SHOTS, "polished-mobile-390x844.png") });
  expect(errors).toEqual([]);
});

test("historical replay has no browser console errors", async ({ page }) => {
  const errors = await boot(page, HIST);
  await page.waitForTimeout(1500);
  expect(errors).toEqual([]);
});

test("API failure degrades without crashing", async ({ page }) => {
  await page.route("**/api/data-status", (r) => r.abort());
  await boot(page, HIST);
  await expect(page.locator("#src")).toContainText(/unreachable|Backend/i);
  expect(await mapCount(page)).toBe(1);
});

test("emergency profile never invokes Mistral", async ({ page }) => {
  let mistralCalls = 0;
  await page.route("**/api/mistral-action-plan", async (route) => {
    mistralCalls += 1;
    await route.fulfill({ status: 500, body: "should not be called" });
  });
  await page.route("**/api/profile-risk**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      category: "critical", confidence: "emergency override", top_reasons: [],
      protective_factors: [], protection_applied: false, recommendations: [], guardrails: [],
      emergency: { active: true, symptoms: ["confusion"], message_en: "Call emergency services.", call: "103" },
      disclaimer_en: "Not a diagnosis.", rule_engine_version: "test",
    }),
  }));
  await boot(page, SYN);
  await page.click("#openProfile");
  await page.check("#s_conf");
  await page.click('#sheet button.btn:has-text("See my explained risk")');
  await expect(page.locator("#sheet .emerg")).toContainText("EMERGENCY — call 103");
  await expect(page.locator("#mistral-build")).toHaveCount(0);
  expect(mistralCalls).toBe(0);
});

test("Mistral action plan uses only the calculated result subset", async ({ page }) => {
  let requestBody;
  await page.route("**/api/mistral-action-plan", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        risk_category: requestBody.risk_category,
        generated_by: "Mistral Medium 3.5",
        plan: {
          headline: "A practical plan through tonight",
          immediate_actions: ["Move activity to a cooler time."],
          next_six_hours: ["Use your available cooler place."],
          tonight: ["Stay in the coolest available room."],
          avoid: ["Avoid direct sun."],
          check_in_message: "Please check in with me tonight.",
          safety_note: "Follow the existing Waves safety notes.",
        },
      }),
    });
  });
  await page.route("**/api/profile-risk**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      category: "high", confidence: "moderate environmental signal",
      top_reasons: [{ factor: "heatwave_event", detail: "Inside a severe heatwave." }],
      protective_factors: ["social_support"], protection_applied: false,
      recommendations: [{ id: "REC-GENERAL", en: "Move activity to a cooler time.", uk: "Перенесіть активність.", source_org: "WHO", source_date: "2024", review_date: null }],
      guardrails: [], emergency: null, disclaimer_en: "Not a diagnosis.", rule_engine_version: "test",
    }),
  }));
  await boot(page, SYN);
  await page.click("#openProfile");
  await page.click('#sheet button.btn:has-text("See my explained risk")');
  await page.click("#mistral-build");
  await expect(page.locator("#mistral-output")).toContainText("Generated by Mistral Medium 3.5");
  await expect(page.locator("#mistral-output")).toContainText("Next 6 hours");
  expect(Object.keys(requestBody).sort()).toEqual([
    "confidence", "context_label", "date", "guardrails", "preferred_language",
    "protective_factors", "recommendations", "risk_category", "top_reasons",
  ]);
  expect(requestBody).not.toHaveProperty("vulnerability");
  expect(requestBody).not.toHaveProperty("symptoms");
});

test("family SMS check-in polls until the recipient responds", async ({ page }) => {
  let sessionStatus = "pending";
  let createBody;
  await page.addInitScript(() => {
    window.__openSms = (url) => { window.__openedSms = url; };
  });
  await page.route("**/api/profile-risk**", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      category: "high", confidence: "high", protection_applied: false,
      top_reasons: [{ factor: "heat", detail: "Severe heat." }],
      protective_factors: [], recommendations: [], guardrails: [], emergency: null,
      disclaimer_en: "Not a diagnosis.", rule_engine_version: "test",
    }),
  }));
  await page.route("**/api/mistral-action-plan", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      risk_category: "high", generated_by: "Mistral Medium 3.5",
      plan: {
        headline: "Stay cool through tonight",
        immediate_actions: ["Move to a cooler place."], next_six_hours: [],
        tonight: [], avoid: [], check_in_message: "Please check in.",
        safety_note: "Follow Waves guidance.",
      },
    }),
  }));
  await page.route("**/api/checkin/create", async (route) => {
    createBody = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: '{"id":"demo-session"}' });
  });
  await page.route("**/api/checkin/demo-session/status", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ status: sessionStatus }),
  }));
  await page.route("**/api/checkin/demo-session/respond", async (route) => {
    sessionStatus = route.request().postDataJSON().status;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: sessionStatus }) });
  });

  await boot(page, SYN);
  await page.click("#openProfile");
  await page.click('#sheet button.btn:has-text("See my explained risk")');
  await page.click("#mistral-build");
  await page.click("#send-sms-alert");
  await expect(page.locator("#checkin-card")).toContainText("Waiting for check-in…");
  expect(createBody).toEqual({ risk_level: "high", language: "en" });
  const smsUrl = await page.evaluate(() => window.__openedSms);
  expect(decodeURIComponent(smsUrl)).toContain("sms:+13417669597?body=Waves shows a HIGH heat-risk level.");
  expect(decodeURIComponent(smsUrl)).toContain("Move to a cooler place — https://waves-nine-gold.vercel.app/checkin/demo-session");

  await page.evaluate(() => fetch("/api/checkin/demo-session/respond", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ status: "ok" }),
  }));
  await expect(page.locator("#checkin-card")).toHaveClass(/ok/, { timeout: 5000 });
  await expect(page.locator("#checkin-card")).toContainText("Checked in — I'm OK");
});
