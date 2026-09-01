const { test, expect } = require("@playwright/test");

const dataWireBase = String(process.env.DATA_WIRE_BASE_URL || "").replace(/\/$/, "");

test.describe("private Florida Signal Newsroom", () => {
  test.skip(!dataWireBase, "Set DATA_WIRE_BASE_URL to verify the running private desk");

  test("Early Radar control keeps one NOW and fails closed on missing live health", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${dataWireBase}/`);
    const control = page.locator("#project-control");
    await expect(control.getByRole("heading", { name: "Project state" })).toBeVisible({ timeout: 15_000 });
    await expect(control).toContainText("NOW · one active task");
    await expect(control).toContainText("NEXT · frozen until NOW closes");
    await expect(control).toContainText("Production pipeline health");
    await expect(control).toContainText("UNKNOWN means no current health contract answered");
    await expect(control).toContainText("Preliminary Development Meeting Request (PDMR)");
    await expect(control).toContainText("Stage reconciled · not admitted");
    await expect(control).toContainText("File-only canary passed · not connected");
    await expect(control).toContainText("93-day proven lead");
    await expect(control).toContainText("RUNTIME DRIFT / NEEDS SEPARATE RECONCILIATION");
    await expect(control.locator(".project-health__row")).toHaveCount(13);
    const headerLayout = await control.locator(".project-control__head").evaluate(node => {
      const bounds = node.getBoundingClientRect();
      const intro = node.firstElementChild.getBoundingClientRect();
      const mode = node.querySelector(".project-control__mode").getBoundingClientRect();
      return {
        height: bounds.height,
        introWidth: intro.width,
        inside: [intro, mode].every(rect => rect.left >= bounds.left && rect.right <= bounds.right + 1),
      };
    });
    expect(headerLayout.height).toBeLessThan(420);
    expect(headerLayout.introWidth).toBeGreaterThan(250);
    expect(headerLayout.inside).toBe(true);
    expect(await page.evaluate(() => document.body.scrollWidth)).toBe(390);
  });

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
    await expect(page.getByRole("button", { name: "Save to Brief bank" })).toBeVisible();
    await expect(page.locator(".dw-pipeline__job").first()).toBeVisible();
    await expect(page.locator('[data-status="APPROVED"]')).toBeHidden();
    expect(await page.evaluate(() => document.body.scrollWidth)).toBe(390);
  });

  test("Live Desk leads with early decisions and treats permits as execution", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${dataWireBase}/`);
    await expect(page.getByRole("heading", { name: "Live Desk" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Latest items to confirm" })).toBeVisible();
    await expect(page.getByText("Packet present · completeness not assessed")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Follow the project before the permit" })).toBeVisible();
    // The first private source read after the desk has been idle can be a cold
    // file-system pass. Keep the placeholder visible, but allow the five
    // independently clocked lanes enough time to replace it.
    await expect(page.locator(".sequence-row")).toHaveCount(5, { timeout: 15_000 });
    await expect(page.locator(".sequence-row").first()).toContainText("Preliminary Development Meeting Request (PDMR) + agenda packets");
    await expect(page.locator(".sequence-row").last()).toContainText("Applications, permits + inspections");
    await expect(page.getByRole("heading", { name: "Signal Machine pipeline" })).toBeVisible();
    await expect(page.getByText("Who is responsible for what")).toBeVisible();
    await expect(page.locator('#weight-form input[type="range"]')).toHaveCount(5);
    await expect(page.locator('#weight-form input[type="range"]').first()).toHaveAttribute('min', '1');
    await expect(page.locator('#weight-form input[type="range"]').first()).toHaveAttribute('max', '2');
    await expect(page.locator('#weight-form input[type="range"]:disabled')).toHaveCount(4);
    await expect(page.locator('#weight-form input[type="range"]').last()).toBeEnabled();
    await expect(page.getByRole("button", { name: /current.*shadow-scored/i })).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("#agenda-window")).toContainText("not scored");
    await expect(page.locator("#lead-story h2")).not.toContainText(/follows/i, { timeout: 15_000 });
    await expect(page.locator("#lead-story .eyebrow")).toContainText("Newest raw Candidate pattern", { timeout: 15_000 });
    await expect(page.locator("#lead-story")).toContainText("extracted assertions", { timeout: 15_000 });
    await expect(page.getByText(/shadow only: permits \/ execution and preliminary development meeting request \(PDMR\) candidate ranking/i)).toBeVisible();
    await expect(page.getByText(/cross-source expansion is staged, not implied/i)).toBeVisible();
    const decisionTop = await page.getByRole("heading", { name: "Latest items to confirm" }).evaluate(node => node.getBoundingClientRect().top + window.scrollY);
    const protocolTop = await page.getByRole("heading", { name: "Signal Machine pipeline" }).evaluate(node => node.getBoundingClientRect().top + window.scrollY);
    expect(decisionTop).toBeLessThan(protocolTop);
    await page.getByRole("button", { name: /shadow-scored/i }).click();
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

    await page.getByRole("button", { name: /shadow-scored/i }).click();
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
    await page.evaluate(() => window.scrollTo(0, 900));
    await expect(page.locator(".dw-shell")).toBeVisible();
    expect(await page.locator(".dw-shell").evaluate(node => Math.round(node.getBoundingClientRect().top))).toBe(0);
  });

  test("PDMR labels production mirror, pending schedule proof, or snapshot fallback truthfully", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${dataWireBase}/data.html`);
    const pdmrStatus = page.locator('[data-source-status="pdmr"]');
    await expect(pdmrStatus).toContainText(
      /(current|delayed|stale).*automated|unverified.*(schedule pending proof|snapshot)/i,
      { timeout: 15_000 },
    );
    await expect(page.locator("#table-select")).toHaveValue("pdmr_intent");
    await expect(page.locator("#count-note")).toContainText(
      /public PDMR records · portal through .* · source checked /i,
      { timeout: 15_000 },
    );
    const pdmrRow = page.locator("#data-table tbody tr[data-i]").first();
    await expect(pdmrRow).toContainText(/UDP-PDMR-/i, { timeout: 15_000 });
    await pdmrRow.focus();
    await pdmrRow.press("Enter");
    await expect(page.getByRole("dialog", { name: /PDMR · UDP-PDMR-/i })).toBeVisible();
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
        await expect(page.getByRole("heading", { name: "Working discovery sequence" })).toBeVisible();
        await expect(page.locator(".source-group").first()).toContainText("Preliminary Development Meeting Request (PDMR)");
        await expect(page.locator(".source-group").nth(1)).toContainText("Sewer + utility capacity");
        await expect(page.locator(".source-group").nth(1)).toContainText("Research only");
        await expect(page.locator(".source-group").nth(1)).toContainText("generic TMP records are downstream/mixed and explicitly excluded");
        await expect(page.locator(".source-group").nth(1)).toContainText("Shadow observed · not connected");
        await expect(page.locator(".source-group").nth(1)).toContainText("two manual observations each saved receipts for 1,100 official rows");
        await expect(page.locator(".source-group").nth(1)).toContainText("No natural timer, stage, database mirror or detector is connected");
        await expect(page.locator('[data-source-status="pdmr"]')).toContainText(/(current|delayed|stale).*automated|unverified.*(schedule pending proof|snapshot)/i, { timeout: 15_000 });
        await expect(page.locator("#table-select")).toHaveValue("pdmr_intent");
        await expect(page.locator("#count-note")).toContainText(/public PDMR records · portal through .* · source checked /i, { timeout: 15_000 });
        const pdmrRow = page.locator("#data-table tbody tr[data-i]").first();
        await expect(pdmrRow).toContainText(/UDP-PDMR-/i, { timeout: 15_000 });
        await pdmrRow.focus();
        await pdmrRow.press("Enter");
        await expect(page.getByRole("dialog", { name: /PDMR · UDP-PDMR-/i })).toBeVisible();
        await page.locator("#drawer-close").click();
        await expect(page.locator("#drawer")).toBeHidden();
        await expect(pdmrRow).toBeFocused();
        await expect(page.locator('.source-option[data-source-table="broward_clerk_preliminary"]')).toBeVisible();
        await expect(page.locator('.source-option[data-source-table="permits"]')).toBeVisible();
        await page.locator("#source-health summary").click();
        const preliminaryHealth = page.locator('[data-feed="broward_clerk_preliminary"]');
        await expect(preliminaryHealth.locator(".clock--collected i")).toHaveText("terminal health receipt");
        await expect(preliminaryHealth.locator(".collected")).not.toHaveText(/not recorded|loading/i, { timeout: 30_000 });
        await expect(preliminaryHealth.locator(".badge")).toContainText(/PRELIMINARY · (CURRENT \/ RETRYING|CHECKED \/ NO NEW ROWS)|PRELIMINARY \/ NOT YET VERIFIED|SOURCE DELAY · 1 BUSINESS DAY/, { timeout: 30_000 });
        await expect(preliminaryHealth.locator(".note")).toContainText(/Latest run (source_wait|empty|ok); attempted through \d{4}-\d{2}-\d{2}/, { timeout: 30_000 });
        await expect(preliminaryHealth.locator(".note")).not.toContainText(/source_not_authoritative_yet|empty_unverified_date/);
        await expect(page.locator("#library-summary")).toContainText(/connected · .*empty · .*unavailable/i, { timeout: 15_000 });
        await expect(page.locator("#library-summary")).toContainText("5 planned/not connected");
        await expect(page.locator('.source-option[data-source-table="sunbiz_entities"] .source-option__status')).toContainText(/(current|connected) · automated/i, { timeout: 15_000 });
        await expect(page.locator('.source-option[data-source-table="accela_details"] .source-option__status')).toContainText(/connected · automated · health unknown/i, { timeout: 15_000 });
        await expect(page.locator('.source-option[data-source-table="gis_enrichment"] .source-option__status')).toContainText(/connected · automated · health unknown/i, { timeout: 15_000 });
        await page.locator('.source-option[data-source-table="sunbiz_entities"]').click();
        await expect(page.locator("#count-note")).toContainText("private resolver row", { timeout: 15_000 });
        await expect(page.locator("#data-table tbody tr[data-i]").first()).toBeVisible();
        const libraryTop = await page.locator(".library").evaluate(node => node.getBoundingClientRect().top);
        const tableTop = await page.locator("#explorer").evaluate(node => node.getBoundingClientRect().top);
        expect(libraryTop).toBeLessThan(tableTop);
      }
      if (path === "/agenda.html") {
        await expect(page.getByRole("heading", { name: "What’s coming up" })).toBeVisible();
        await expect(page.locator(".meeting-card").first()).toContainText("City of Fort Lauderdale", { timeout: 15_000 });
        await expect(page.locator(".meeting-card").first()).toContainText(/\d{1,2}:\d{2}\s*(AM|PM)/i);
        await expect(page.getByRole("heading", { name: "Past meeting decisions and packet evidence" })).toBeVisible();
        await expect(page.locator(".agenda-item").first()).toContainText("City of Fort Lauderdale");
        await expect(page.locator(".agenda-item").first()).toContainText("Raw public record · not scored · not a Signal");
        await expect(page.locator(".agenda-item").first().getByRole("link", { name: /official agenda PDF/i })).toBeVisible();
        await expect(page.getByLabel("Government body")).toBeVisible();
        await expect(page.getByLabel("Search agenda items")).toBeVisible();
        const bankButton = page.getByRole("button", { name: /Save to Brief bank|Saved/i }).first();
        await expect(bankButton).toBeVisible();
        await bankButton.click();
        await expect(page.getByRole("dialog", { name: /Save to Brief bank|Change Brief edition slot/i })).toBeVisible();
        await expect(page.getByLabel("Edition day")).toBeVisible();
        await page.getByLabel("Edition day").selectOption("friday");
        await expect(page.getByLabel(/Exact edition date/i)).not.toHaveValue("");
        await page.getByRole("button", { name: "Cancel" }).click();
      }
      if (path === "/index.html") {
        await expect(page.getByRole("heading", { name: "Brief bank" })).toBeVisible();
        await expect(page.getByRole("button", { name: "Wed" })).toBeVisible();
        await expect(page.getByText("AI consistency check: not connected.")).toBeVisible();
        await expect(page.getByText("Not connected. No sending path exists in this build.")).toBeVisible();
        await expect(page.getByText("Send · not connected")).toBeVisible();
        await expect(page.getByText(/Claim-slot check \(self-attested\)/).first()).toBeVisible();
        await expect(page.getByText(/Claims check \(editor attestation\)/).first()).toBeVisible();
        await expect(page.getByText("01A · Brief writing profile")).toBeVisible();
        await expect(page.getByLabel("Style guide")).toHaveValue("ap_florida_signal");
        await expect(page.locator('input[name="ethics_rules"]:checked')).toHaveCount(7);
      }
      expect(await page.evaluate(() => document.body.scrollWidth), `${path} page width`).toBe(390);
    }
  });
});
