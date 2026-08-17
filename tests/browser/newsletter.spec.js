const { test, expect } = require("@playwright/test");

test.describe("Florida Signal Brief front door", () => {
  test("keeps the complete logo and ZIP signup visible on a narrow phone", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await page.goto("/");

    const headerLogo = page.locator(".launch-brand--header img");
    await expect(headerLogo).toBeVisible();
    await expect(headerLogo).toHaveAttribute("src", "/brand/florida-signal-logo-avatar-kit-2026-08-16/production-hires-v2/fs-lockup-horizontal-transparent-2510.png");
    await expect(headerLogo).toHaveAttribute("srcset", /horizontal-transparent-2510\.png 2510w.+horizontal-transparent-5020\.png 5020w/);
    await expect(page.getByLabel("ZIP code").first()).toBeVisible();
    await expect(page.getByLabel("ZIP code").first()).toHaveAttribute("placeholder", "ZIP code (e.g. 33301)");
  });

  test("keeps the complete conversion action in the first phone viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    await expect(page.getByRole("heading", { level: 1 })).toContainText("across Broward");
    await expect(page.getByRole("button", { name: "Get the Brief" }).first()).toBeVisible();
    await expect(page.getByText("Delivered Mondays at 7 a.m. ET. More timely alerts as the desk expands.")).toBeVisible();

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
    await page.getByLabel("ZIP code").first().fill("33301");
    await page.getByRole("button", { name: "Get the Brief" }).first().click();

    await expect(page.getByText("You’re in. Watch for the next brief.")).toBeVisible();
    expect(posted.email).toBe("reader@example.com");
    expect(posted.source).toBe("florida-signal-brief-launch");
    expect(posted.zip).toBe("33301");
  });

  test("sends privacy-minimized landing and signup analytics", async ({ page }) => {
    const analytics = [];
    await page.route("**/api/events", async (route) => {
      analytics.push(route.request().postDataJSON());
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ok: true }) });
    });
    await page.route("**/api/subscribe", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, existing: false }) });
    });

    await page.goto("/");
    await expect.poll(() => analytics.some((event) => event.event === "page_view")).toBe(true);
    await page.getByLabel("Email address").first().fill("reader@example.com");
    await page.getByLabel("ZIP code").first().fill("33301");
    await page.getByRole("button", { name: "Get the Brief" }).first().click();
    await expect.poll(() => analytics.some((event) => event.event === "newsletter_conversion")).toBe(true);

    expect(analytics.map((event) => event.event)).toEqual(expect.arrayContaining(["page_view", "newsletter_submit", "newsletter_conversion"]));
    expect(JSON.stringify(analytics)).not.toContain("reader@example.com");
    expect(JSON.stringify(analytics)).not.toContain("33301");
  });

  test("exposes the skip link and a logical keyboard entry point", async ({ page }) => {
    await page.goto("/");
    const skipLink = page.getByRole("link", { name: "Skip to content" });
    await page.keyboard.press("Tab");
    await expect(skipLink).toBeFocused();
    await expect(skipLink).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#main$/);
  });

  test("has two signup points and keeps the landing page focused", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    await expect(page.locator("[data-launch-signup]")).toHaveCount(2);
    await expect(page.getByRole("link", { name: "Explore the research site" })).toHaveCount(0);
    const headerLogo = page.locator(".launch-brand--header img");
    await expect(headerLogo).toBeVisible();
    await expect(headerLogo).toHaveAttribute("src", "/brand/florida-signal-logo-avatar-kit-2026-08-16/production-hires-v2/fs-lockup-horizontal-transparent-2510.png");
    await expect(headerLogo).toHaveAttribute("srcset", /horizontal-transparent-2510\.png 2510w.+horizontal-transparent-5020\.png 5020w/);
    await expect(page.locator(".launch-byline")).toHaveText("Built by a veteran journalist. AI-assisted; journalist-approved.");
    const footerLogo = page.locator(".launch-brand--footer img");
    await expect(footerLogo).toBeVisible();
    await expect(footerLogo).toHaveAttribute("src", "/brand/florida-signal-logo-avatar-kit-2026-08-16/production-hires-v2/fs-lockup-compact-transparent-2510.png");
    await expect(footerLogo).toHaveAttribute("srcset", /compact-transparent-2510\.png 2510w.+compact-transparent-5020\.png 5020w/);
    await expect(footerLogo).toHaveAttribute("width", "2510");
    await expect(footerLogo).toHaveAttribute("height", "556");
    await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href", "/assets/favicon-32.png");
    await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute("href", "/assets/apple-touch-icon.png");
    await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/site.webmanifest");
    await expect(page.locator(".launch-source-strip")).toContainText("130K+");
    await expect(page.locator(".launch-source-strip")).toContainText("2.4M+");
    await expect(page.locator(".launch-source-note")).toContainText("records are leads");
    await expect(page.locator(".launch-signal-sample")).toContainText("What changed");
    await expect(page.locator(".launch-signal-sample")).toContainText("Why it matters");
    await expect(page.locator(".launch-signal-sample")).toContainText("What happens next");
    await expect(page.locator(".launch-signal-sample")).toContainText("The receipt");
    await expect(page.locator(".launch-footer")).toContainText("Published by Graham & Gold, LLC");
    await expect(page.getByRole("link", { name: "Privacy" }).first()).toHaveAttribute("href", "/privacy/");
    await expect(page.locator("body")).not.toContainText("Sunday Signal");
  });

  test("offers accessible social and native share controls with privacy-minimized analytics", async ({ page }) => {
    const analytics = [];
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "share", {
        configurable: true,
        value: async (payload) => { window.__floridaSignalSharePayload = payload; },
      });
    });
    await page.route("**/api/events", async (route) => {
      analytics.push(route.request().postDataJSON());
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ok: true }) });
    });
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Know someone who should see what’s changing?" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Share Florida Signal on LinkedIn" })).toHaveAttribute("href", /linkedin\.com\/sharing\/share-offsite/);
    await expect(page.getByRole("link", { name: "Share Florida Signal on Facebook" })).toHaveAttribute("href", /facebook\.com\/sharer/);
    await expect(page.getByRole("link", { name: "Share Florida Signal on X" })).toHaveAttribute("href", /twitter\.com\/intent\/tweet/);
    await expect(page.getByRole("link", { name: "Share Florida Signal by email" })).toHaveAttribute("href", /^mailto:/);

    await page.getByRole("button", { name: "Share Florida Signal" }).click();
    const sharePayload = await page.evaluate(() => window.__floridaSignalSharePayload);
    expect(sharePayload).toEqual({
      title: "Florida Signal Brief",
      text: "Know what’s changing across Broward before the headline. Get the Florida Signal Brief.",
      url: "https://thefloridasignal.com/",
    });
    await expect.poll(() => analytics.some((event) => event.event === "share_click" && event.properties.method === "native")).toBe(true);
    expect(JSON.stringify(analytics)).not.toContain("reader@example.com");
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
    await expect(page.getByRole("heading", { name: "Privacy-minimized analytics" })).toBeVisible();
    await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href", "/assets/favicon-32.png");
    await expect(page.locator(".launch-brand--header img")).toHaveAttribute("src", "/brand/florida-signal-logo-avatar-kit-2026-08-16/production-hires-v2/fs-lockup-horizontal-transparent-2510.png");
    await expect(page.getByRole("link", { name: "Return to the Florida Signal Brief" })).toHaveAttribute("href", "/");
  });
});
