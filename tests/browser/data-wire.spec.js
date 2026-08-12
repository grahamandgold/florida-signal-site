const { test, expect } = require("@playwright/test");

const dataWireBase = String(process.env.DATA_WIRE_BASE_URL || "").replace(/\/$/, "");

test.describe("private Data Wire", () => {
  test.skip(!dataWireBase, "Set DATA_WIRE_BASE_URL to verify the running private desk");

  test("candidate investigation kit and live pipeline remain usable on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${dataWireBase}/review.html`);
    await expect(page.getByRole("heading", { name: "Could this be a story?" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Street View" })).toHaveAttribute("href", /map_action=pano/);
    await expect(page.getByRole("link", { name: "Satellite / aerial" })).toHaveAttribute("href", /basemap=satellite/);
    await expect(page.getByRole("link", { name: "Latest news coverage" })).toHaveAttribute("href", /news\.google\.com/);
    await expect(page.getByRole("link", { name: "Search the open web" })).toHaveAttribute("href", /google\.com\/search/);
    await expect(page.getByRole("link", { name: "Search Sunbiz" })).toHaveAttribute("href", /search\.sunbiz\.org/);
    await expect(page.locator(".dw-pipeline__job").first()).toBeVisible();
    await expect(page.locator('[data-status="APPROVED"]')).toBeHidden();
    expect(await page.evaluate(() => document.body.scrollWidth)).toBe(390);
  });

  test("Live Desk leads with early decisions and treats permits as execution", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${dataWireBase}/`);
    await expect(page.getByRole("heading", { name: "Follow the project before the permit." })).toBeVisible();
    // The first private source read after the desk has been idle can be a cold
    // file-system pass. Keep the placeholder visible, but allow the five
    // independently clocked lanes enough time to replace it.
    await expect(page.locator(".radar__lane")).toHaveCount(5, { timeout: 15_000 });
    await expect(page.locator(".radar__lane").first()).toContainText("Zoning, planning + agenda packets");
    await expect(page.locator(".radar__lane").last()).toContainText("Applications, permits + inspections");
    await expect(page.getByRole("heading", { name: "What developers should read before the permit." })).toBeVisible();
    await expect(page.locator(".agenda-item").first()).toContainText("Why developers may care");
    await expect(page.locator("#agenda-watch-summary")).toContainText("public attachments");
    await expect(page.locator("#agenda-watch-summary")).toContainText("events");
    expect(await page.evaluate(() => document.body.scrollWidth)).toBe(390);
  });
});
