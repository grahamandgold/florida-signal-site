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
});
