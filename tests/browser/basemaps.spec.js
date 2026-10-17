const { test, expect } = require("@playwright/test");

// Exercise real Leaflet rendering without downloading provider tiles or changing
// public records. CARTO's key-required image is HTTP 200, not a tileerror.
async function mockMapSources(page) {
  const date = new Date().toISOString().slice(0, 10);
  const record = {
    permit_number: "MAP-TEST-1", address: "100 TEST STREET", applied_date: date,
    last_seen_at: date + "T12:00:00Z", lat: 26.129, lon: -80.144,
    permit_type: "Commercial", description: "Map regression fixture", valuation: 500000
  };
  await page.route("**/rest/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/dashboard_cache")
      ? [{ payload: { stats: { permits_total: 1, p_geo: 1 } }, updated_at: date }]
      : path.endsWith("/permits") ? [record] : [];
    await route.fulfill({ json: body, headers: { "content-range": "0-0/1" } });
  });
  await page.route("**/arcgis/rest/**", (route) => route.fulfill({ json: { type: "FeatureCollection", features: [] } }));
  await page.route("**/api/**", (route) => route.fulfill({ json: {
    sources: [], stories: [], meetings: [], items: [], configured: false,
    storm_watch: "off", rooms_watched: 0, packets_posted: 0, properties_cleared: 0
  } }));
  await page.route(/https:\/\/(?:[^/]*basemaps\.cartocdn\.com|tile\.openstreetmap\.org)\//, (route) => {
    const carto = new URL(route.request().url()).hostname.endsWith("cartocdn.com");
    return route.fulfill({ contentType: "image/svg+xml", body:
      '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#eee"/><text x="10" y="100">' +
      (carto ? "API KEY REQUIRED" : "Test basemap tile") + '</text></svg>'
    });
  });
}

const cases = [
  { name: "homepage filing spotlight", route: "/fort-lauderdale/", map: "#signal-spotlight-map" },
  { name: "Data Room", route: "/fort-lauderdale/graphics/", map: "#data-room-map" },
  { name: "agenda reconnaissance", route: "/fort-lauderdale/meetings/", map: "#agenda-recon-map" },
  { name: "mobile field view", route: "/fort-lauderdale/", map: "#mobile-field-map", mobile: true }
];

for (const scenario of cases) {
  test(`${scenario.name} renders a usable keyless basemap with attribution`, async ({ page }) => {
    if (scenario.mobile) await page.setViewportSize({ width: 390, height: 844 });
    await mockMapSources(page);
    await page.goto(scenario.route, { waitUntil: "domcontentloaded" });
    if (scenario.mobile) await page.locator("[data-mobile-field-toggle]").click();
    const map = page.locator(scenario.map);
    await expect(map.locator(".leaflet-tile-loaded").first()).toBeAttached({ timeout: 15000 });
    const tiles = await map.locator(".leaflet-tile").evaluateAll((images) => images.map((image) => image.src));
    expect(tiles.length).toBeGreaterThan(0);
    for (const tile of tiles) {
      const url = new URL(tile);
      expect(url.origin).toBe("https://tile.openstreetmap.org");
      expect(url.pathname).toMatch(/^\/\d+\/\d+\/\d+\.png$/);
      expect(Number(url.pathname.split("/")[1])).toBeLessThanOrEqual(19);
    }
    await expect(map.locator('.leaflet-control-attribution a[href="https://www.openstreetmap.org/copyright"]')).toBeVisible();
    await expect(map.locator(".leaflet-control-attribution")).toContainText("contributors");
  });
}
