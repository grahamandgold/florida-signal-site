const { test, expect } = require("@playwright/test");

function capturePageErrors(page) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

const publicDesks = [
  "/fort-lauderdale/",
  "/fort-lauderdale/briefs/",
  "/fort-lauderdale/neighborhoods/",
  "/fort-lauderdale/broward-record/",
  "/fort-lauderdale/graphics/",
  "/fort-lauderdale/storm/",
  "/fort-lauderdale/meetings/",
  "/fort-lauderdale/method/",
  "/fort-lauderdale/brand/"
];

for (const route of publicDesks) {
  test(`${route} renders without an uncaught browser error`, async ({ page }) => {
    const errors = capturePageErrors(page);
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response && response.ok(), `${route} returned ${response && response.status()}`).toBeTruthy();
    await expect(page.locator("h1").first()).toBeVisible();
    await page.waitForTimeout(1_000);
    expect(errors, errors.join("\n")).toEqual([]);
  });
}

test("non-map desks initialize without Leaflet", async ({ page }) => {
  const errors = capturePageErrors(page);
  const routes = [
    "/fort-lauderdale/method/",
    "/fort-lauderdale/broward-record/"
  ];

  for (const route of routes) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    const freshness = page.locator("[data-updated]").first();
    await expect(freshness).not.toContainText("Connecting to the record", { timeout: 30_000 });
  }

  expect(errors, errors.join("\n")).toEqual([]);
});

test("briefs desk settles to an explicit editorial-wire state", async ({ page }) => {
  const errors = capturePageErrors(page);
  await page.goto("/fort-lauderdale/briefs/", { waitUntil: "domcontentloaded" });

  await expect(page.locator("#stories-status")).not.toContainText("Connecting", { timeout: 20_000 });
  await expect(page.locator("#stories-grid")).not.toContainText("Checking the approved public wire", { timeout: 20_000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("headline counts disclose exact and estimated quality", async ({ page }) => {
  const errors = capturePageErrors(page);
  await page.goto("/fort-lauderdale/", { waitUntil: "domcontentloaded" });

  const permitCount = page.locator('[data-stat="permits"]').first();
  await expect(permitCount).not.toHaveText("—", { timeout: 30_000 });
  await expect(permitCount).toHaveAttribute("data-count-quality", "exact");
  await expect(permitCount).not.toContainText("≈");

  await page.goto("/fort-lauderdale/broward-record/", { waitUntil: "domcontentloaded" });
  const sunbizCount = page.locator('[data-stat="sunbiz"]').first();
  await expect(sunbizCount).not.toHaveText("—", { timeout: 30_000 });
  await expect(sunbizCount).toHaveAttribute("data-count-quality", "estimated");
  await expect(sunbizCount).toContainText("≈");
  await expect(page.getByText("Sunbiz-linked · estimate")).toBeVisible();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("method desk visibly separates preliminary and verified Clerk clocks", async ({ page }) => {
  await page.route("**/api/data-health", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        sources: [
          { id: "broward", label: "Broward verified instruments", status: "delayed", verification: "verified", event_through: "2026-08-05", system_time: "2026-08-10T18:11:44Z", cadence: "daily", detail: "authoritative SFTP" },
          { id: "clerk-preliminary", label: "Broward preliminary recordings", status: "current", verification: "preliminary", event_through: "2026-08-10", system_time: "2026-08-11T00:56:06Z", cadence: "four times daily", detail: "reconciled later" }
        ]
      })
    });
  });
  await page.goto("/fort-lauderdale/method/", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("Broward verified instruments")).toBeVisible();
  await expect(page.getByText("Broward preliminary recordings")).toBeVisible();
  await expect(page.locator(".source-health__evidence--verified")).toHaveText("verified");
  await expect(page.locator(".source-health__evidence--preliminary")).toHaveText("preliminary");

  await page.goto("/fort-lauderdale/graphics/", { waitUntil: "domcontentloaded" });
  const dataRoomHealth = page.locator("#source-health");
  await expect(dataRoomHealth).toBeVisible();
  await expect(dataRoomHealth.locator("summary strong")).toContainText("1 current · 1 delayed");
  await dataRoomHealth.locator("summary").click();
  await expect(dataRoomHealth.getByText("Broward verified instruments")).toBeVisible();
  await expect(dataRoomHealth.getByText("Broward preliminary recordings")).toBeVisible();
});

test("Data Room never turns failed live queries into zero counts", async ({ page }) => {
  await page.route("https://jrjewmzkyluxdywyusrw.supabase.co/rest/v1/**", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ message: "test outage" }) });
  });
  await page.route("**/api/data-health", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ sources: [] }) });
  });
  await page.route("**/api/meetings", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ updated_at: "2026-08-30T12:00:00Z", calendar_url: "https://example.test/calendar", meetings: [] }) });
  });
  await page.route("**/api/storms", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ activeStorms: [] }) });
  });
  await page.goto("/fort-lauderdale/graphics/", { waitUntil: "domcontentloaded" });

  await expect(page.locator("#data-room-application-count")).toHaveText("—");
  await expect(page.locator("#data-room-map-count")).toHaveText("—");
  await expect(page.locator("#data-room-map-window")).toContainText("no zero count inferred");
  await expect(page.locator("#application-pulse")).toContainText("APPLICATIONS UNAVAILABLE");
  await expect(page.locator("#place-lens .graphic-card__top")).toContainText("UNAVAILABLE");
  await expect(page.locator("#trades-pulse .graphic-card__top")).toContainText("UNAVAILABLE");
  await expect(page.locator("#high-value")).toContainText("VALUE UNAVAILABLE");
  await expect(page.locator("#storm-window")).toContainText("LOCAL FILINGS UNAVAILABLE");
  await expect(page.locator("#records-desk .graphic-card__top")).toContainText("UNAVAILABLE");
  await expect(page.locator("#meetings-watch")).toContainText("NO MEETINGS PUBLISHED");
  await expect(page.locator("#meetings-watch .graphic-card__top")).toContainText("OFFICIAL CALENDAR");
  await expect(page.locator("#source-health summary strong")).toHaveText("Health manifest unavailable");
});

test("Data Room preserves its last good map while a later permit refresh fails", async ({ page }) => {
  let permitOutage = false;
  let supabaseDelay = 60;
  let meetingDelay = 0;
  const permit = {
    permit_number: "BLD-TEST-1", address: "100 E LAS OLAS BLVD", permit_type: "Building",
    permit_category: "Building", description: "Roof improvement", valuation: 250000,
    valuation_usd_clean: 250000, applied_date: "2026-08-29", issued_date: null,
    last_seen_at: "2026-08-30T12:00:00Z", lat: 26.119, lon: -80.13,
    region: "Fort Lauderdale", contractor_name: "TEST CONTRACTOR", applicant_name: "TEST APPLICANT",
    owner_name: "TEST OWNER", status: "Submitted", work_type: "Roof", is_commercial: true
  };
  await page.route("https://jrjewmzkyluxdywyusrw.supabase.co/rest/v1/**", async (route) => {
    if (supabaseDelay) await new Promise((resolve) => setTimeout(resolve, supabaseDelay));
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/dashboard_cache")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([{ updated_at: "2026-08-30T12:00:00Z", payload: { stats: { permits_total: 1, p_geo: 1, p_parcel: 1, broward_docs: 1, owner_chg: 0, flip: 0, eff_owner: 1, eff_value: 1, broward_fresh: "2026-08-29" }, ptypes: [], valdist: [], contractors: [] } }]) });
      return;
    }
    const select = url.searchParams.get("select") || "";
    if (permitOutage && select.includes("address")) {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ message: "test permit outage" }) });
      return;
    }
    if (select === "permit_number") {
      await route.fulfill({ status: 200, headers: { "Content-Range": "0-0/1" }, contentType: "application/json", body: "[]" });
      return;
    }
    if (select === "applied_date") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([{ applied_date: permit.applied_date }]) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([permit]) });
  });
  await page.route("**/gisdata/MapServer/61/query**", async (route) => {
    await route.fulfill({ contentType: "application/geo+json", body: JSON.stringify({ type: "FeatureCollection", features: [] }) });
  });
  await page.route("**/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query**", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ features: [] }) });
  });
  await page.route("**/api/meetings", async (route) => {
    if (meetingDelay) await new Promise((resolve) => setTimeout(resolve, meetingDelay));
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ updated_at: "2026-08-30T12:00:00Z", meetings: [{ category: "government", date: "2026-09-01", title: "City Commission", location: "City Hall", source: "Legistar", agenda_available: true, agenda_url: "https://example.test/agenda" }] }) });
  });
  await page.route("**/api/storms", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ activeStorms: [] }) });
  });
  await page.route("**/api/data-health", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ sources: [] }) });
  });

  await page.goto("/fort-lauderdale/graphics/", { waitUntil: "domcontentloaded" });
  const lastGoodPane = page.locator("#data-room-map .leaflet-pane").first();
  await expect(lastGoodPane).toHaveCount(1, { timeout: 20_000 });
  await lastGoodPane.evaluate((node) => { node.dataset.lastGoodMap = "retained"; });
  await expect(page.locator("#place-lens .graphic-card__top")).not.toContainText("UNAVAILABLE");
  await expect(page.locator("#meetings-watch .graphic-card__top")).toContainText("OFFICIAL CALENDAR");

  permitOutage = true;
  supabaseDelay = 0;
  meetingDelay = 60;
  await page.locator("#data-room-refresh").click();
  await expect(page.locator("#data-room-refresh")).toBeEnabled({ timeout: 20_000 });
  await expect(page.locator("#data-room-map")).toHaveAttribute("data-source-state", "unavailable");
  await expect(page.locator('#data-room-map .leaflet-pane[data-last-good-map="retained"]')).toHaveCount(1);
  await expect(page.locator("#place-lens .graphic-card__top")).toContainText("UNAVAILABLE");
  await expect(page.locator("#trades-pulse .graphic-card__top")).toContainText("UNAVAILABLE");
  await expect(page.locator("#records-desk .graphic-card__top")).toContainText("VERIFIED SNAPSHOT");
  await expect(page.locator("#meetings-watch .graphic-card__top")).toContainText("OFFICIAL CALENDAR");
});
