const { test, expect } = require("@playwright/test");

const dataWireBase = String(process.env.DATA_WIRE_BASE_URL || "").replace(/\/$/, "");

test.describe("private Florida Signal Newsroom", () => {
  test.skip(!dataWireBase, "Set DATA_WIRE_BASE_URL to verify the running private desk");

  test("candidate investigation kit and live pipeline remain usable on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${dataWireBase}/review.html`);
    await expect(page.getByLabel("Florida Signal Newsroom — Live Desk home")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Triage" })).toBeVisible();
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
    await expect(page.getByRole("heading", { name: "Live Desk" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Follow the project before the permit" })).toBeVisible();
    // The first private source read after the desk has been idle can be a cold
    // file-system pass. Keep the placeholder visible, but allow the five
    // independently clocked lanes enough time to replace it.
    await expect(page.locator(".sequence-row")).toHaveCount(5, { timeout: 15_000 });
    await expect(page.locator(".sequence-row").first()).toContainText("Zoning, planning + agenda packets");
    await expect(page.locator(".sequence-row").last()).toContainText("Applications, permits + inspections");
    await page.getByRole("button", { name: /source lane/i }).click();
    await expect(page.getByRole("dialog", { name: "Newsroom source status" })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Newsroom source status" })).not.toContainText("1969");
    expect(await page.evaluate(() => document.body.scrollWidth)).toBe(390);
  });

  test("source labels and early-intelligence rows do not collide at a sidebar-width viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1110, height: 900 });
    await page.goto(`${dataWireBase}/`);
    await expect(page.locator(".sequence-row")).toHaveCount(5, { timeout: 15_000 });

    const sequenceLayout = await page.locator(".sequence-row").evaluateAll(rows => rows.map(row => {
      const bounds = row.getBoundingClientRect();
      const stage = row.querySelector(".sequence-row__stage").getBoundingClientRect();
      const title = row.querySelector("h3").getBoundingClientRect();
      return {
        inside: [...row.children].every(child => {
          const rect = child.getBoundingClientRect();
          return rect.left >= bounds.left - 1 && rect.right <= bounds.right + 1;
        }),
        columnsClear: stage.right <= title.left + 1,
      };
    }));
    expect(sequenceLayout.every(row => row.inside && row.columnsClear)).toBe(true);
    expect(await page.evaluate(() => document.body.scrollWidth)).toBe(1110);

    await page.getByRole("button", { name: /source lane/i }).click();
    const dialog = page.getByRole("dialog", { name: "Newsroom source status" });
    await expect(dialog).toBeVisible();
    const sourceLayout = await dialog.locator(".dw-source-row").evaluateAll(rows => rows.map(row => {
      const bounds = row.getBoundingClientRect();
      const stage = row.querySelector(".dw-source-stage").getBoundingClientRect();
      const copy = row.querySelector("div").getBoundingClientRect();
      const clock = row.querySelector(".dw-source-clock").getBoundingClientRect();
      return {
        inside: [stage, copy, clock].every(rect => rect.left >= bounds.left - 1 && rect.right <= bounds.right + 1),
        stageClear: stage.right <= copy.left + 1,
        clockClear: copy.right <= clock.left + 1,
      };
    }));
    expect(sourceLayout.every(row => row.inside && row.stageClear && row.clockClear)).toBe(true);
  });

  test("the canonical full-color emblem has a contrasting header field", async ({ page }) => {
    await page.setViewportSize({ width: 1110, height: 900 });
    await page.goto(`${dataWireBase}/`);
    const mark = page.locator('.dw-brand img[src="/mark-full-color.png"]');
    await expect(mark).toBeVisible();
    const treatment = await mark.evaluate(node => {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return { background: style.backgroundColor, width: rect.width, height: rect.height };
    });
    expect(treatment.background).not.toBe("rgba(0, 0, 0, 0)");
    expect(treatment.width).toBeGreaterThanOrEqual(44);
    expect(treatment.height).toBeGreaterThanOrEqual(44);
  });

  test("Newsroom pages keep distinct jobs and fit a 390px field viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const pages = [
      ["/agenda.html", /Agenda Watch/],
      ["/index.html", /Build the Brief.*Clear every claim/i],
      ["/data.html", /Search the record.*Then work the lead/i],
      ["/review.html", /Triage/],
    ];

    for (const [path, heading] of pages) {
      await page.goto(`${dataWireBase}${path}`);
      await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
      await expect(page.getByLabel("Florida Signal Newsroom — Live Desk home")).toHaveAttribute("href", "/");
      if (path === "/data.html") {
        await expect(page.getByRole("heading", { name: "Choose what you want to investigate" })).toBeVisible();
        await expect(page.locator('.source-option[data-source-table="broward_clerk_preliminary"]')).toBeVisible();
        await expect(page.locator('.source-option[data-source-table="permits"]')).toBeVisible();
        await expect(page.locator("#library-summary")).toContainText(/connected · .*empty · .*unavailable/i, { timeout: 15_000 });
        await expect(page.locator('.source-option[data-source-table="sunbiz_entities"] .source-option__status')).toHaveText("Connected", { timeout: 15_000 });
        await page.locator('.source-option[data-source-table="sunbiz_entities"]').click();
        await expect(page.locator("#count-note")).toContainText("private resolver row", { timeout: 15_000 });
        await expect(page.locator("#data-table tbody tr[data-i]").first()).toBeVisible();
        const libraryTop = await page.locator(".library").evaluate(node => node.getBoundingClientRect().top);
        const tableTop = await page.locator("#explorer").evaluate(node => node.getBoundingClientRect().top);
        expect(libraryTop).toBeLessThan(tableTop);
      }
      expect(await page.evaluate(() => document.body.scrollWidth), `${path} page width`).toBe(390);
    }
  });
});
