#!/usr/bin/env node
/* Export the live Graphic Desk into stamped social images and share pages.
 * Usage: node social/export_graphic_desk.cjs [base_url]
 * Requires Playwright. The local Florida Signal server must be running.
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const outputDir = path.join(root, "social", "graphic-desk");
const shareDir = path.join(root, "share");
const baseUrl = (process.argv[2] || "http://127.0.0.1:4173").replace(/\/$/, "");
const publicUrl = (process.env.FLORIDA_SIGNAL_PUBLIC_URL || "https://thefloridasignal.com").replace(/\/$/, "");
const cards = [
  ["application-pulse", "Permit application pulse"],
  ["place-lens", "Neighborhood + ZIP Place Lens"],
  ["trades-pulse", "Fort Lauderdale trades pulse"],
  ["high-value", "High-value filing queue"],
  ["value-universe", "Property value ladder"],
  ["operator-board", "Contractor operator board"],
  ["records-desk", "Broward records desk"],
  ["company-lens", "Sunbiz + ownership company lens"],
  ["storm-window", "Florida Signal storm window"],
  ["meetings-watch", "Public + industry meeting watch"]
];
const requestedSlugs = new Set(String(process.env.FLORIDA_SIGNAL_EXPORT_SLUGS || "").split(",").map((value) => value.trim()).filter(Boolean));
const exportCards = requestedSlugs.size ? cards.filter(([slug]) => requestedSlugs.has(slug)) : cards;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, function (character) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
  });
}

function shareDocument(slug, title) {
  const imageUrl = publicUrl + "/social/graphic-desk/" + slug + ".png";
  const destination = "../graphics.html?graphic=" + slug + "#" + slug;
  const description = "Source-labeled Florida development intelligence from Florida Signal.";
  return `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Florida Signal · ${escapeHtml(title)}</title>
<meta name="description" content="${escapeHtml(description)}">
<meta name="author" content="Graham &amp; Gold LLC"><meta name="publisher" content="Graham &amp; Gold LLC"><meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:type" content="article"><meta property="og:site_name" content="Florida Signal">
<meta property="og:title" content="Florida Signal · ${escapeHtml(title)}">
<meta property="og:description" content="${escapeHtml(description)}">
<meta property="og:image" content="${imageUrl}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="620">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="Florida Signal · ${escapeHtml(title)}"><meta name="twitter:image" content="${imageUrl}">
<meta http-equiv="refresh" content="0;url=${destination}">
<link rel="canonical" href="${publicUrl}/graphics.html?graphic=${slug}#${slug}">
<link rel="icon" type="image/png" sizes="32x32" href="../assets/favicon-32.png"><link rel="apple-touch-icon" sizes="180x180" href="../assets/apple-touch-icon.png">
</head><body><p><a href="${destination}">Open the cited Florida Signal graphic →</a></p></body></html>\n`;
}

(async function exportGraphicDesk() {
  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(shareDir, { recursive: true });
  const browser = await chromium.launch();
  for (const [slug, title] of exportCards) {
    const page = await browser.newPage({ viewport: { width: 1200, height: 820 }, deviceScaleFactor: 1 });
    await page.goto(baseUrl + "/graphics.html?embed=" + slug, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForTimeout(2200);
    const card = page.locator("#" + slug);
    await card.waitFor({ state: "visible", timeout: 30000 });
    await card.screenshot({ path: path.join(outputDir, slug + ".png") });
    await page.close();
    fs.writeFileSync(path.join(shareDir, slug + ".html"), shareDocument(slug, title), "utf8");
    console.log("exported " + slug);
  }
  await browser.close();
})().catch(function (error) {
  console.error(error);
  process.exitCode = 1;
});
