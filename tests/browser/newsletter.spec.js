const { test, expect } = require("@playwright/test");

test.describe("Florida Signal Brief front door", () => {
  test("keeps the complete conversion action in the first phone viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    await expect(page.getByRole("heading", { level: 1 })).toContainText("across Broward");
    await expect(page.getByRole("button", { name: "Get the Brief" }).first()).toBeVisible();
    await expect(page.getByText("Free every Monday morning to start.")).toBeVisible();

    const layout = await page.evaluate(() => ({
      width: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
      signupBottom: document.querySelector(".launch-hero .launch-fine").getBoundingClientRect().bottom,
      brokenImages: [...document.images].filter((image) => !image.complete || !image.naturalWidth).length,
    }));
    expect(layout.width).toBe(layout.viewport);
    expect(layout.signupBottom).toBeLessThan(844);
    expect(layout.brokenImages).toBe(0);
  });

  test("submits the hero signup with the brief landing source", async ({ page }) => {
    let posted = null;
    await page.route("**/api/subscribe", async (route) => {
      posted = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, existing: false }),
      });
    });
    await page.goto("/");
    await page.getByLabel("Email address").first().fill("reader@example.com");
    await page.getByRole("button", { name: "Get the Brief" }).first().click();

    await expect(page.getByText("You’re in. Watch for the next brief.")).toBeVisible();
    expect(posted.email).toBe("reader@example.com");
    expect(posted.source).toBe("florida-signal-brief-launch");
    expect(posted.zip).toBe("");
  });

  test("has two signup points and preserves the research site", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    await expect(page.locator("[data-launch-signup]")).toHaveCount(2);
    await expect(page.getByRole("link", { name: "Explore the research site" })).toHaveAttribute("href", "/fort-lauderdale/");
    await expect(page.getByText("Development Intelligence").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Privacy" }).first()).toHaveAttribute("href", "/privacy/");
    await expect(page.locator("body")).not.toContainText("Sunday Signal");
  });

  test("keeps the former newsletter URL as an alias for the front door", async ({ page }) => {
    await page.goto("/newsletter/");
    expect(new URL(page.url()).pathname).toBe("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("before the headline");
  });

  test("publishes a plain-language subscriber privacy page", async ({ page }) => {
    await page.goto("/privacy/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Privacy, in plain English.");
    await expect(page.getByText("We do not sell your personal information.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Return to the Florida Signal Brief" })).toHaveAttribute("href", "/");
  });
});
