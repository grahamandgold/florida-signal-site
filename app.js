(function () {
  "use strict";

  const SUPABASE_URL = "https://jrjewmzkyluxdywyusrw.supabase.co";
  // Supabase publishable keys are designed for public clients. RLS remains the access boundary.
  const SUPABASE_KEY = "sb_publishable_dEyBjKE_vcTj3YYx4p6XvA_xnkVW3Wb";
  const NEIGHBORHOODS_URL = "https://gis.fortlauderdale.gov/arcgis/rest/services/GeneralPurpose/gisdata/MapServer/61/query?where=1%3D1&outFields=OFFICIALNAME&returnGeometry=true&f=geojson&outSR=4326";
  const CENSUS_ENVELOPE = "-80.36,25.91,-80.04,26.36";
  const CENSUS_LAYERS = {
    zip: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query", where: "1=1", fields: "ZCTA5,NAME", color: "#7654b5", label: "ZIP" },
    congress: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/0/query", where: "STATE='12'", fields: "NAME,BASENAME,CD119", color: "#1767ff", label: "U.S. House" },
    senate: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/1/query", where: "STATE='12'", fields: "NAME,BASENAME,SLDU", color: "#ff6d3a", label: "FL Senate" },
    house: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/2/query", where: "STATE='12'", fields: "NAME,BASENAME,SLDL", color: "#009f91", label: "FL House" },
    corridor: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4/query", where: "STATE='12' AND NAME IN ('Hollywood city','Pompano Beach city','Oakland Park city','Wilton Manors city','Plantation city','Cooper City city','Southwest Ranches town')", fields: "NAME,BASENAME,PLACE,STATE", color: "#a81920", label: "Broward corridor" }
  };
  const recordSelect = "permit_number,address,permit_type,permit_category,description,valuation_usd_clean,applied_date,issued_date,last_seen_at,lat,lon,region,contractor_name,applicant_name,owner_name,status,work_type,is_commercial";
  const numberFormat = new Intl.NumberFormat("en-US");
  const compactFormat = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
  const moneyFormat = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const now = new Date();
  const CURRENT_MONTH_START = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-01";
  const applicationWindowDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 13);
  const APPLICATION_WINDOW_START = applicationWindowDate.getFullYear() + "-" + String(applicationWindowDate.getMonth() + 1).padStart(2, "0") + "-" + String(applicationWindowDate.getDate()).padStart(2, "0");
  const state = { dashboard: null, records: [], featured: [], applicationDates: [], cms: { configured: false, connected: false, stories: [] }, storms: [], stormPayload: null, siteMode: { storm_watch: "off" }, meetings: [], neighborhoods: null, zipBoundaries: null, map: null, markerLayer: null, polygonLayer: null, searchMarker: null, searchResults: [], leadResults: [], spotlightMaps: {}, overlayLayers: {}, overlayVisibility: { points: true, neighborhoods: true }, lens: "all", leadLens: "new" };
  let stormTickerTimer = null;

  function el(selector, root) { return (root || document).querySelector(selector); }
  function els(selector, root) { return Array.from((root || document).querySelectorAll(selector)); }
  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>'"]/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char];
    });
  }
  function titleCase(value) {
    return String(value || "").toLowerCase().replace(/\b([a-z])/g, function (m) { return m.toUpperCase(); }).replace(/\b(Llc|Inc|Nw|Ne|Sw|Se)\b/g, function (m) { return m.toUpperCase(); });
  }
  function formatDate(value, options) {
    if (!value) return "Record date pending";
    const date = new Date(value.length === 10 ? value + "T12:00:00-04:00" : value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("en-US", options || { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }).format(date);
  }
  function formatNumber(value, compact) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "—";
    return compact ? compactFormat.format(num) : numberFormat.format(num);
  }
  function setStat(name, value) {
    els('[data-stat="' + name + '"]').forEach(function (node) { node.textContent = value; });
  }
  function recordDate(record) { return record.applied_date || record.issued_date || record.last_seen_at; }
  function recordHeadline(record) {
    const address = titleCase(String(record.address || "an address").replace(/\s+/g, " ").trim());
    const description = String(record.description || "").replace(/\s+/g, " ").trim();
    const generic = /^(online )?(walk-thru|structural permit|window and door permit|mechanical permit|plumbing permit|electrical permit)$/i;
    if (description && description.length >= 8 && !generic.test(description) && description.toLowerCase() !== String(record.address || "").toLowerCase()) {
      const clean = description.length > 85 ? description.slice(0, 82).replace(/\s+\S*$/, "") + "…" : description;
      return titleCase(clean) + " · " + address;
    }
    return titleCase(record.permit_type || "Permit") + " filed at " + address;
  }
  function isStormRecord(record) {
    return /(roof|reroof|re-roof|seawall|sea wall|impact|window|door|generator|drain|flood|elevation|shutter|waterproof|dock|marine)/i.test([record.permit_type, record.permit_category, record.description].join(" "));
  }
  function isAssociationRecord(record) {
    return /(homeowners association|homeowner association|condominium association|property owners association|\bhoa\b|\bcondo ass|\bassn\b)/i.test([record.owner_name, record.applicant_name, record.description].join(" "));
  }
  function recordUrl(record) { return "neighborhoods.html?permit=" + encodeURIComponent(record.permit_number || ""); }

  function recordPlace(record) {
    const matched = findNeighborhoodForRecord(record);
    if (matched && matched !== "Location not mapped" && matched !== "Outside matched City boundary") return matched;
    return record.region && !/fort lauderdale/i.test(record.region) ? titleCase(record.region) : "Fort Lauderdale";
  }

  function tagSlug(value) {
    return String(value || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }

  function uniqueTags(values) {
    return Array.from(new Set(values.filter(Boolean)));
  }

  function recordTaxonomy(record) {
    const text = [record.permit_type, record.permit_category, record.description, record.work_type].join(" ").toLowerCase();
    const tags = ["source:city-permit", "geography:" + tagSlug(recordPlace(record)), "audience:field-desk"];
    if (isStormRecord(record)) tags.push("topic:storm-readiness");
    if (isAssociationRecord(record)) tags.push("topic:association-condo");
    if (/(demo|demolition)/.test(text)) tags.push("topic:demolition");
    if (/(seawall|sea wall|dock|marine)/.test(text)) tags.push("topic:waterfront");
    if (/(roof|reroof|re-roof)/.test(text)) tags.push("topic:roofing");
    if (/(new construction|new building|addition|development)/.test(text)) tags.push("topic:development");
    if (record.is_commercial === true || /commercial/.test(text)) tags.push("asset:commercial");
    if (Number(record.valuation_usd_clean || 0) >= 250000) tags.push("urgency:high-value");
    if (!String(record.contractor_name || "").trim()) tags.push("qualification:operator-unlisted");
    return uniqueTags(tags);
  }

  function taxonomyAttribute(tags) {
    return escapeHtml(uniqueTags(tags || []).join(" "));
  }

  function taxonomyLine(tags, prefix) {
    const visible = uniqueTags(tags || []).filter(function (tag) { return /^(topic|urgency|asset):/.test(tag); }).slice(0, 3).map(function (tag) { return titleCase(tag.split(":").slice(1).join(" ").replace(/-/g, " ")); });
    return visible.length ? '<span class="taxonomy-line"><b>' + escapeHtml(prefix || "Filed under") + ' ·</b>' + escapeHtml(visible.join(" · ")) + '</span>' : "";
  }

  function placeSignature(record) {
    return '<span class="place-signature"><i aria-hidden="true"></i>' + escapeHtml(recordPlace(record)) + '</span>';
  }

  function shareRecordUrl(record) {
    return new URL(recordUrl(record), window.location.href).href;
  }

  function recordShareMarkup(record) {
    const url = shareRecordUrl(record);
    const title = "Florida Signal · " + recordPlace(record) + " · " + titleCase(String(record.address || record.permit_number || "development record").replace(/\s+/g, " "));
    const message = title + " — " + (record.permit_number || "public filing") + " " + url;
    const hasPoint = Number.isFinite(Number(record.lat)) && Number.isFinite(Number(record.lon));
    const point = hasPoint ? Number(record.lat) + "," + Number(record.lon) : encodeURIComponent(String(record.address || "Fort Lauderdale, FL"));
    const streetUrl = hasPoint ? "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=" + point : "https://www.google.com/maps/search/?api=1&query=" + point;
    const satelliteUrl = hasPoint ? "https://www.google.com/maps/@?api=1&map_action=map&center=" + point + "&zoom=19&basemap=satellite" : "https://www.google.com/maps/search/?api=1&query=" + point;
    return '<div class="record-share" aria-label="Share this Florida Signal record">' +
      '<a class="record-action record-action--street" href="' + escapeHtml(streetUrl) + '" target="_blank" rel="noreferrer" aria-label="Open nearby Street View">Street view</a>' +
      '<a class="record-action record-action--satellite" href="' + escapeHtml(satelliteUrl) + '" target="_blank" rel="noreferrer" aria-label="Open satellite map">Satellite</a>' +
      '<a class="record-action record-action--text" href="sms:?&body=' + encodeURIComponent(message) + '" aria-label="Text this record">Text</a>' +
      '<button class="record-action record-action--share" type="button" data-share-record data-share-url="' + escapeHtml(url) + '" data-share-title="' + escapeHtml(title) + '">Share</button>' +
      '<button class="record-action record-action--copy" type="button" data-copy-record data-share-url="' + escapeHtml(url) + '">Copy link</button></div>';
  }

  function bindRecordSharing(root) {
    els("[data-share-record]", root).forEach(function (button) {
      button.addEventListener("click", async function () {
        const url = button.getAttribute("data-share-url") || window.location.href;
        const title = button.getAttribute("data-share-title") || "Florida Signal record";
        if (navigator.share) {
          try { await navigator.share({ title: title, url: url }); return; }
          catch (error) { if (error && error.name === "AbortError") return; }
        }
        try { await navigator.clipboard.writeText(url); button.textContent = "Copied"; }
        catch (error) { window.prompt("Copy this Florida Signal record", url); }
      });
    });
    els("[data-copy-record]", root).forEach(function (button) {
      button.addEventListener("click", async function () {
        const url = button.getAttribute("data-share-url") || window.location.href;
        try { await navigator.clipboard.writeText(url); button.textContent = "Copied"; }
        catch (error) { window.prompt("Copy this Florida Signal record", url); }
      });
    });
  }

  async function supabase(path, params, options) {
    const url = new URL(SUPABASE_URL + "/rest/v1/" + path);
    Object.entries(params || {}).forEach(function (entry) { url.searchParams.set(entry[0], entry[1]); });
    const response = await fetch(url, Object.assign({
      headers: { apikey: SUPABASE_KEY, Accept: "application/json" }
    }, options || {}));
    if (!response.ok) throw new Error("Supabase request failed: " + response.status);
    return response;
  }

  async function fastCount(table, filters) {
    const response = await supabase(table, Object.assign({ select: "permit_number", limit: "1" }, filters || {}), {
      headers: { apikey: SUPABASE_KEY, Accept: "application/json", Prefer: "count=planned", Range: "0-0" }
    });
    const range = response.headers.get("content-range") || "";
    const match = range.match(/\/(\d+)$/);
    return match ? Number(match[1]) : null;
  }

  async function fetchApplicationDates() {
    const rows = [];
    for (let offset = 0; offset < 6000; offset += 1000) {
      const response = await supabase("permits", { select: "applied_date", applied_date: "gte." + APPLICATION_WINDOW_START, limit: "1000", offset: String(offset) });
      const batch = await response.json();
      rows.push.apply(rows, batch);
      if (batch.length < 1000) break;
    }
    return rows.map(function (row) { return row.applied_date; }).filter(Boolean);
  }

  async function loadPublicRecord() {
    const results = await Promise.allSettled([
      supabase("dashboard_cache", { select: "payload,updated_at", id: "eq.1" }).then(function (r) { return r.json(); }),
      fastCount("permits"),
      fastCount("permits", { lat: "not.is.null", lon: "not.is.null" }),
      fastCount("permits", { source_sunbiz: "not.is.null" }),
      supabase("permits", { select: recordSelect, applied_date: "gte." + CURRENT_MONTH_START, lat: "not.is.null", lon: "not.is.null", order: "applied_date.desc.nullslast,last_seen_at.desc.nullslast", limit: "700" }).then(function (r) { return r.json(); }),
      supabase("permits", { select: recordSelect, applied_date: "gte." + CURRENT_MONTH_START, valuation_usd_clean: "gte.100000", order: "applied_date.desc.nullslast,valuation_usd_clean.desc.nullslast", limit: "40" }).then(function (r) { return r.json(); }),
      fetchApplicationDates()
    ]);

    if (results[0].status === "fulfilled" && results[0].value[0]) state.dashboard = results[0].value[0];
    state.records = results[4].status === "fulfilled" ? results[4].value.sort(function (a, b) { return String(b.applied_date || "").localeCompare(String(a.applied_date || "")) || String(b.last_seen_at || "").localeCompare(String(a.last_seen_at || "")); }) : [];
    state.featured = results[5].status === "fulfilled" ? results[5].value.sort(function (a, b) { return String(b.applied_date || "").localeCompare(String(a.applied_date || "")) || Number(b.valuation_usd_clean || 0) - Number(a.valuation_usd_clean || 0); }) : [];
    state.applicationDates = results[6].status === "fulfilled" ? results[6].value : [];

    const stats = state.dashboard && state.dashboard.payload ? state.dashboard.payload.stats || {} : {};
    const permits = results[1].status === "fulfilled" ? results[1].value : stats.permits_total;
    // The query planner's filtered estimate is intentionally not used here; the
    // dashboard cache carries the last exact geocoded-row count and timestamp.
    const mapped = stats.p_geo || (results[2].status === "fulfilled" ? results[2].value : null);
    const sunbiz = results[3].status === "fulfilled" ? results[3].value : null;
    setStat("permits", formatNumber(permits));
    setStat("mapped", formatNumber(mapped));
    setStat("sunbiz", formatNumber(sunbiz));
    setStat("broward-docs", formatNumber(stats.broward_docs));
    setStat("workflow", formatNumber(stats.foia_events, true));
    setStat("owner-change", formatNumber(stats.owner_chg));
    setStat("flip", formatNumber(stats.flip));
    setStat("broward-fresh", stats.broward_fresh ? formatDate(stats.broward_fresh, { month: "short", day: "numeric", timeZone: "America/New_York" }) : "—");
    setStat("effective-owner", formatNumber(stats.eff_owner));
    setStat("effective-value", formatNumber(stats.eff_value));

    const permitTimestamp = state.records.map(function (record) { return record.last_seen_at; }).filter(Boolean).sort(function (a, b) { return new Date(b) - new Date(a); })[0];
    const applicationThrough = state.records.map(function (record) { return record.applied_date; }).filter(Boolean).sort().slice(-1)[0];
    const dashboardTimestamp = state.dashboard && state.dashboard.updated_at;
    const permitClock = permitTimestamp ? "Permit mirror synced " + formatDate(permitTimestamp, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET" : "Permit mirror unavailable";
    const applicationClock = applicationThrough ? "applications through " + formatDate(applicationThrough, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) : "application date pending";
    const dashboardClock = dashboardTimestamp ? "aggregate snapshot refreshed " + formatDate(dashboardTimestamp, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET" : "aggregate snapshot unavailable";
    const pageName = document.body.getAttribute("data-page") || "home";
    let freshness = permitClock + " · " + applicationClock;
    if (pageName === "broward") freshness = "Broward instruments through " + (stats.broward_fresh ? formatDate(stats.broward_fresh, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) : "date pending") + " · " + dashboardClock;
    else if (pageName === "graphics" || pageName === "method") freshness = permitClock + " · " + dashboardClock + " · cards name their event clocks";
    els("[data-updated]").forEach(function (node) { node.textContent = freshness; });
    const barTime = el("#live-bar-time");
    if (barTime) barTime.textContent = permitTimestamp ? "Permits synced " + formatDate(permitTimestamp, { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET" : "Source clock unavailable";

    if (state.records.length && (el("#signal-list") || el("#lead-list") || el("#graphic-desk"))) await Promise.allSettled([loadNeighborhoods()]);
    if (el("#graphic-desk")) await Promise.allSettled([loadZipBoundaries()]);
    renderSignals();
    renderInfographics();
    renderStormRecords();
    renderGraphicDesk();
    await initMaps();
    renderLeadDesk();
    initRecordSpotlights();
    const initialQuery = new URLSearchParams(window.location.search).get("q");
    if (initialQuery && el("#record-search")) await runRecordSearch(initialQuery);
  }

  async function loadCmsContent() {
    const status = el("#cms-status");
    try {
      const response = await fetch("/api/cms", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("CMS adapter unavailable");
      state.cms = await response.json();
      if (status) {
        if (!state.cms.configured) status.textContent = "Adapter installed; set FLORIDA_SIGNAL_CMS_URL to connect the duplicated Florida Desk.";
        else if (state.cms.connected) status.textContent = formatNumber((state.cms.stories || []).length) + " approved public items available through " + state.cms.source_endpoint + ".";
        else status.textContent = "CMS configured but no approved public endpoint answered; internal queues remain hidden.";
      }
      renderSignals();
      renderStoriesPage();
    } catch (error) {
      if (status) status.textContent = "Approved-content adapter unavailable; permit records remain the public fallback.";
      renderStoriesPage(error);
    }
  }

  function publicStoryUrl(story) {
    return "stories.html?story=" + encodeURIComponent(story.id || story.slug || "");
  }

  function renderStoriesPage(loadError) {
    const grid = el("#stories-grid");
    const reader = el("#story-reader");
    const status = el("#stories-status");
    if (!grid || !reader) return;
    const stories = state.cms && Array.isArray(state.cms.stories) ? state.cms.stories : [];
    if (loadError) {
      if (status) status.textContent = "The approved public wire is temporarily unavailable. No cached draft is being substituted.";
      grid.innerHTML = '<div class="stories-empty"><p class="eyebrow">Source gate closed</p><h2>No story is being inferred.</h2><p>The permit, meeting and map surfaces remain available while the editorial wire reconnects.</p><a class="button" href="neighborhoods.html">Open live field map →</a></div>';
      return;
    }
    if (!state.cms.configured) {
      if (status) status.textContent = "The public Stories home is ready; The Data Wire connection has not been configured on this server.";
      grid.innerHTML = '<div class="stories-empty"><p class="eyebrow">Desk ready · no synthetic seed</p><h2>The first story will arrive through the source gate.</h2><p>This page starts honestly empty. Drafts, agent notes and uncited summaries remain private until a human editor approves a source-linked WirePacket.</p><a class="button" href="method.html">Read the publishing standard →</a></div>';
      return;
    }
    if (status) status.textContent = stories.length ? formatNumber(stories.length) + " approved stor" + (stories.length === 1 ? "y" : "ies") + " on the public wire · market: Broward" : "The Data Wire is connected. No story has passed every publishing gate yet.";
    const selectedId = new URLSearchParams(window.location.search).get("story");
    const selected = selectedId ? stories.find(function (story) { return String(story.id) === selectedId || String(story.slug) === selectedId; }) : null;
    if (selected) {
      const tags = Array.isArray(selected.tags) ? selected.tags : [];
      const body = String(selected.body || selected.summary || "").split(/\n\s*\n/).filter(Boolean).map(function (paragraph) { return "<p>" + escapeHtml(paragraph) + "</p>"; }).join("");
      const sourceLinks = Array.isArray(selected.source_links) && selected.source_links.length ? selected.source_links : [selected.source_url];
      reader.hidden = false;
      reader.innerHTML = '<a class="story-reader__back" href="stories.html">← All approved stories</a>' +
        (selected.hero_image ? '<figure><img src="' + escapeHtml(selected.hero_image) + '" alt=""><figcaption>Florida Signal story image · source and licensing retained by the desk</figcaption></figure>' : '') +
        '<header>' + taxonomyLine(tags, "Filed under") + '<p class="story-reader__date">Event date ' + escapeHtml(formatDate(selected.event_date || selected.published_at, { month: "long", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + ' · approved ' + escapeHtml(formatDate(selected.published_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" })) + ' ET</p><h1>' + escapeHtml(selected.title) + '</h1><p class="story-reader__dek">' + escapeHtml(selected.summary || "") + '</p><span>By ' + escapeHtml(selected.byline || "Florida Signal Desk") + '</span></header><div class="story-reader__body">' + body + '</div><footer><strong>Sources</strong>' + sourceLinks.filter(Boolean).map(function (url, index) { return '<a href="' + escapeHtml(url) + '" target="_blank" rel="noreferrer">Open cited source ' + (index + 1) + ' ↗</a>'; }).join("") + '<small>Florida Signal separates event dates from pull, enrichment and publication times.</small></footer>';
      grid.hidden = true;
      document.title = selected.title + " — Florida Signal";
      return;
    }
    reader.hidden = true;
    grid.hidden = false;
    if (!stories.length) {
      grid.innerHTML = '<div class="stories-empty"><p class="eyebrow">Watching, not filling space</p><h2>No story has cleared the wire yet.</h2><p>The desk is connected. The site will publish the first article only after its source, claims, tags and human review pass.</p><a class="button" href="index.html#signals">See live public-record signals →</a></div>';
      return;
    }
    grid.innerHTML = stories.map(function (story, index) {
      const tags = Array.isArray(story.tags) ? story.tags : [];
      return '<article class="story-card ' + (index === 0 ? "story-card--lead" : "") + '">' +
        (story.hero_image ? '<a class="story-card__image" href="' + publicStoryUrl(story) + '"><img src="' + escapeHtml(story.hero_image) + '" alt=""></a>' : '<a class="story-card__mark" href="' + publicStoryUrl(story) + '" aria-label="Open ' + escapeHtml(story.title) + '"><img src="assets/mark-full-color.png" alt=""></a>') +
        '<div>' + taxonomyLine(tags, "Filed under") + '<p class="story-card__date">' + escapeHtml(formatDate(story.event_date || story.published_at, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + '</p><h2><a href="' + publicStoryUrl(story) + '">' + escapeHtml(story.title) + '</a></h2><p>' + escapeHtml(story.summary || "Approved Florida Desk report") + '</p><footer><span>' + escapeHtml(story.byline || "Florida Signal Desk") + '</span><a href="' + publicStoryUrl(story) + '">Read + sources →</a></footer></div></article>';
    }).join("");
  }

  function renderSignals() {
    const list = el("#signal-list");
    const ticker = el("#live-bar-story");
    const mobileTicker = el("#mobile-live-story");
    const cmsStories = state.cms && state.cms.connected && Array.isArray(state.cms.stories) ? state.cms.stories.slice(0, 4) : [];
    const liveHeadline = cmsStories[0] ? cmsStories[0].title : (state.records[0] ? recordHeadline(state.records[0]) : "The public feed is connecting…");
    if (ticker) ticker.textContent = liveHeadline;
    if (mobileTicker) mobileTicker.textContent = liveHeadline;
    if (document.body.classList.contains("storm-mode")) startStormTicker(state.storms[0] || null);
    if (!list) return;
    if (cmsStories.length) {
      list.innerHTML = cmsStories.map(function (story) {
        const summary = story.summary || story.source || "Approved public desk item";
        const storyTags = Array.isArray(story.tags) ? story.tags : ["topic:" + tagSlug(story.category || "desk-brief"), "source:florida-desk"];
        return '<a class="signal-row signal-row--cms" data-signal-tags="' + taxonomyAttribute(storyTags) + '" href="' + publicStoryUrl(story) + '">' +
          '<div class="signal-row__date">' + escapeHtml(formatDate(story.published_at, { month: "short", day: "numeric", timeZone: "America/New_York" })) + '</div>' +
          '<div>' + taxonomyLine(storyTags) + '<h3>' + escapeHtml(story.title) + '</h3><p class="signal-row__meta">' + escapeHtml(summary) + '</p></div>' +
          '<div class="signal-row__value"><strong>Approved</strong><span>' + escapeHtml(story.category || "desk brief") + '</span></div>' +
          '<span class="signal-row__arrow" aria-hidden="true">↗</span></a>';
      }).join("");
      const cmsNote = el("#signal-source-note");
      if (cmsNote) cmsNote.textContent = "Florida Desk · approved-only public feed · sources open with each item";
      return;
    }
    const candidates = state.featured.length ? state.featured.slice(0, 4) : state.records.slice(0, 4);
    if (!candidates.length) {
      list.innerHTML = '<div class="loading-row">The public feed is temporarily unavailable. No substitute data is being shown.</div>';
      return;
    }
    list.innerHTML = candidates.map(function (record) {
      const value = Number(record.valuation_usd_clean);
      const contractor = record.contractor_name ? titleCase(record.contractor_name) : "Contractor not yet listed";
      const tags = recordTaxonomy(record);
      return '<div class="signal-row-wrap" data-signal-tags="' + taxonomyAttribute(tags) + '"><a class="signal-row" href="' + recordUrl(record) + '">' +
        '<div class="signal-row__date">' + escapeHtml(formatDate(recordDate(record), { month: "short", day: "numeric", timeZone: "America/New_York" })) + '</div>' +
        '<div>' + placeSignature(record) + taxonomyLine(tags) + '<h3>' + escapeHtml(recordHeadline(record)) + '</h3><p class="signal-row__meta">' + escapeHtml(record.permit_number || "Record ID pending") + ' · ' + escapeHtml(contractor) + '</p></div>' +
        '<div class="signal-row__value"><strong>' + (Number.isFinite(value) && value > 0 ? escapeHtml(moneyFormat.format(value)) : "Filed") + '</strong><span>' + (Number.isFinite(value) && value > 0 ? "declared value" : "public record") + '</span></div>' +
        '<span class="signal-row__arrow" aria-hidden="true">→</span></a>' + recordShareMarkup(record) + '</div>';
    }).join("");
    bindRecordSharing(list);
    const note = el("#signal-source-note");
    if (note && candidates[0]) note.textContent = "Latest displayed application date " + formatDate(candidates[0].applied_date, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) + " · City of Fort Lauderdale";
  }

  function renderInfographics() {
    const payload = state.dashboard && state.dashboard.payload;
    const chart = el("#activity-chart");
    const totalNode = el("#activity-total");
    if (chart && state.applicationDates.length) {
      const counts = state.applicationDates.reduce(function (result, date) { result[date] = (result[date] || 0) + 1; return result; }, {});
      const activity = [];
      for (let index = 0; index < 14; index += 1) {
        const date = new Date(applicationWindowDate.getFullYear(), applicationWindowDate.getMonth(), applicationWindowDate.getDate() + index);
        const key = date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
        activity.push({ key: key, label: key.slice(5), count: counts[key] || 0 });
      }
      const maximum = Math.max.apply(null, activity.map(function (day) { return day.count; }).concat([1]));
      const total = activity.reduce(function (sum, day) { return sum + day.count; }, 0);
      if (totalNode) totalNode.textContent = formatNumber(total) + " permit applications filed";
      chart.innerHTML = activity.map(function (day) {
        const height = Math.max(day.count ? 3 : 0, Math.round((day.count / maximum) * 100));
        return '<div class="activity-day" title="' + escapeHtml(day.key) + ': ' + formatNumber(day.count) + ' Fort Lauderdale permit applications">' +
          '<div class="activity-day__bars"><i class="activity-day__bar activity-day__bar--intake activity-day__bar--single" style="--bar-height:' + height + '%"></i></div>' +
          '<span>' + escapeHtml(day.label) + '</span></div>';
      }).join("");
      const pipeline = payload && Array.isArray(payload.activity) ? payload.activity : [];
      const pulled = pipeline.reduce(function (sum, day) { return sum + Number(day.intake || 0); }, 0);
      const enriched = pipeline.reduce(function (sum, day) { return sum + Number(day.enriched || 0); }, 0);
      const source = el("#activity-source");
      if (source) source.textContent = "City of Fort Lauderdale permit records · grouped by applied_date · live query · pipeline processing is separate: " + formatNumber(pulled) + " pulled / " + formatNumber(enriched) + " enriched in the latest cache window";
    } else if (chart) {
      chart.innerHTML = '<p class="muted">Application-date activity is temporarily unavailable. Batch-ingestion dates are not being substituted.</p>';
      if (totalNode) totalNode.textContent = "Permit application-date feed unavailable";
    }

    const values = payload && Array.isArray(payload.valdist) ? payload.valdist : [];
    const valueBars = el("#value-bars");
    if (valueBars && values.length) {
      const maximum = Math.max.apply(null, values.map(function (bucket) { return Number(bucket.n || 0); }).concat([1]));
      valueBars.innerHTML = values.map(function (bucket, index) {
        const count = Number(bucket.n || 0);
        return '<div class="value-bar"><div class="value-bar__label"><strong>' + escapeHtml(bucket.b) + '</strong><span>' + formatNumber(count) + '</span></div><div class="value-bar__track"><i style="--bar-width:' + Math.round((count / maximum) * 100) + '%;--bar-index:' + index + '"></i></div></div>';
      }).join("");
    }

    const contractors = payload && Array.isArray(payload.contractors) ? payload.contractors : [];
    const operatorList = el("#operator-list");
    if (operatorList && contractors.length) {
      operatorList.innerHTML = contractors.slice(0, 6).map(function (operator, index) {
        return '<li><span>' + String(index + 1).padStart(2, "0") + '</span><strong>' + escapeHtml(titleCase(operator.c)) + '</strong><em>' + formatNumber(operator.n) + ' records</em></li>';
      }).join("");
    }
  }

  async function loadNeighborhoods() {
    if (state.neighborhoods) return state.neighborhoods;
    const response = await fetch(NEIGHBORHOODS_URL, { cache: "force-cache" });
    if (!response.ok) throw new Error("Neighborhood layer unavailable");
    state.neighborhoods = await response.json();
    return state.neighborhoods;
  }

  async function loadZipBoundaries() {
    if (state.zipBoundaries) return state.zipBoundaries;
    const response = await fetch(censusQueryUrl(CENSUS_LAYERS.zip), { cache: "force-cache" });
    if (!response.ok) throw new Error("ZIP layer unavailable");
    state.zipBoundaries = await response.json();
    return state.zipBoundaries;
  }

  function pointInRing(point, ring) {
    const x = point[0], y = point[1];
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      const intersect = ((yi > y) !== (yj > y)) && (x < ((xj - xi) * (y - yi)) / ((yj - yi) || 1e-12) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  function pointInFeature(point, feature) {
    const geometry = feature && feature.geometry;
    if (!geometry) return false;
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" ? geometry.coordinates : [];
    return polygons.some(function (polygon) {
      return polygon[0] && pointInRing(point, polygon[0]) && !polygon.slice(1).some(function (hole) { return pointInRing(point, hole); });
    });
  }

  function neighborhoodName(feature) {
    const raw = feature && feature.properties ? feature.properties.OFFICIALNAME || feature.properties.NAME || "Neighborhood" : "Neighborhood";
    return String(raw).replace(/\s+(Homeowners|Neighborhood|Civic|Improvement) Association.*$/i, "").replace(/,?\s+Inc\.?$/i, "").trim();
  }

  function neighborhoodCounts(features, records) {
    return features.map(function (feature) {
      const hits = records.filter(function (record) { return pointInFeature([Number(record.lon), Number(record.lat)], feature); });
      return { feature: feature, name: neighborhoodName(feature), records: hits, count: hits.length };
    }).filter(function (item) { return item.count > 0; }).sort(function (a, b) { return b.count - a.count || a.name.localeCompare(b.name); });
  }

  function mapPopup(record) {
    const value = Number(record.valuation_usd_clean);
    return placeSignature(record) + '<div class="popup-kicker">' + escapeHtml(record.permit_type || "Permit record") + '</div>' +
      '<div class="popup-title">' + escapeHtml(titleCase(String(record.address || "Address pending").replace(/\s+/g, " "))) + '</div>' +
      '<div class="popup-meta">' + escapeHtml(record.description || record.permit_number || "Public record") + (Number.isFinite(value) && value > 0 ? "<br><strong>" + escapeHtml(moneyFormat.format(value)) + " declared value</strong>" : "") + "</div>";
  }

  function markerColor(record) {
    const text = [record.permit_type, record.description].join(" ");
    if (/(demo|demolition)/i.test(text)) return "#ff6d3a";
    if (isStormRecord(record)) return "#1767ff";
    if (Number(record.valuation_usd_clean) >= 500000) return "#071b32";
    return "#009f91";
  }

  function drawMarkers(map, records) {
    if (state.markerLayer) state.markerLayer.remove();
    state.markerLayer = L.layerGroup().addTo(map);
    records.forEach(function (record) {
      if (!Number.isFinite(Number(record.lat)) || !Number.isFinite(Number(record.lon))) return;
      const marker = L.circleMarker([Number(record.lat), Number(record.lon)], {
        radius: Number(record.valuation_usd_clean) >= 500000 ? 7 : 5,
        color: "#ffffff",
        weight: 1.5,
        fillColor: markerColor(record),
        fillOpacity: .88
      }).bindPopup(mapPopup(record));
      marker.record = record;
      marker.addTo(state.markerLayer);
    });
    const count = el("#map-point-count");
    if (count) count.textContent = formatNumber(records.length);
    if (!state.overlayVisibility.points) state.markerLayer.remove();
  }

  function activeMapRecords() {
    return state.lens === "storm" ? state.records.filter(isStormRecord) : state.records;
  }

  function haversineKm(aLat, aLon, bLat, bLon) {
    const toRad = Math.PI / 180;
    const dLat = (bLat - aLat) * toRad;
    const dLon = (bLon - aLon) * toRad;
    const lat1 = aLat * toRad;
    const lat2 = bLat * toRad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  }

  function rebuildHeatLayer() {
    if (state.overlayLayers.heat) state.overlayLayers.heat.remove();
    if (!window.L || typeof L.heatLayer !== "function") return null;
    const points = activeMapRecords().filter(function (record) { return Number.isFinite(Number(record.lat)) && Number.isFinite(Number(record.lon)); }).map(function (record) { return [Number(record.lat), Number(record.lon), .62]; });
    state.overlayLayers.heat = L.heatLayer(points, { radius: 28, blur: 24, minOpacity: .34, maxZoom: 17, gradient: { .2: "#7ce8d3", .46: "#ffcf4a", .72: "#ff6d3a", 1: "#a81920" } });
    return state.overlayLayers.heat;
  }

  function censusQueryUrl(config) {
    const url = new URL(config.url);
    url.searchParams.set("where", config.where);
    if (config !== CENSUS_LAYERS.corridor) {
      url.searchParams.set("geometry", CENSUS_ENVELOPE);
      url.searchParams.set("geometryType", "esriGeometryEnvelope");
      url.searchParams.set("inSR", "4326");
      url.searchParams.set("spatialRel", "esriSpatialRelIntersects");
    }
    url.searchParams.set("outFields", config.fields);
    url.searchParams.set("returnGeometry", "true");
    url.searchParams.set("outSR", "4326");
    url.searchParams.set("f", "geojson");
    return url.toString();
  }

  function overlayFeatureLabel(kind, feature) {
    const properties = feature.properties || {};
    if (kind === "zip") return "ZIP " + (properties.ZCTA5 || properties.BASENAME || "area");
    if (kind === "corridor") return (properties.BASENAME || properties.NAME || "Broward municipality") + " · full permit connector queued";
    return properties.NAME || properties.BASENAME || CENSUS_LAYERS[kind].label;
  }

  async function buildBoundaryOverlay(kind) {
    if (state.overlayLayers[kind]) return state.overlayLayers[kind];
    const config = CENSUS_LAYERS[kind];
    const response = await fetch(censusQueryUrl(config), { cache: "force-cache" });
    if (!response.ok) throw new Error("Boundary layer unavailable");
    const geojson = await response.json();
    const layer = L.geoJSON(geojson, {
      style: function () { return { color: config.color, weight: kind === "corridor" ? 1.7 : 2, opacity: .82, dashArray: kind === "zip" ? "5 4" : null, fillColor: config.color, fillOpacity: kind === "corridor" ? .055 : .025 }; },
      onEachFeature: function (feature, featureLayer) { featureLayer.bindTooltip(overlayFeatureLabel(kind, feature), { sticky: true, direction: "top" }); }
    });
    if (kind === "corridor") {
      const stationLat = 26.1234754;
      const stationLon = -80.1461203;
      const nearby = state.records.filter(function (record) { return Number.isFinite(Number(record.lat)) && Number.isFinite(Number(record.lon)) && haversineKm(stationLat, stationLon, Number(record.lat), Number(record.lon)) <= 1.207; });
      const stationIcon = L.divIcon({ className: "", html: '<span class="corridor-pin" aria-hidden="true"></span>', iconSize: [17, 17], iconAnchor: [8, 8] });
      const station = L.marker([stationLat, stationLon], { icon: stationIcon }).bindPopup('<div class="popup-kicker">Broward corridor anchor</div><div class="popup-title">Brightline Fort Lauderdale</div><div class="popup-meta">101 NW 2 Avenue · ' + formatNumber(nearby.length) + ' applications in the current mapped sample within 0.75 mile.<br><strong>Station: Brightline · location: City GIS</strong></div>');
      const walkShed = L.circle([stationLat, stationLon], { radius: 1207, color: "#a81920", weight: 1.5, dashArray: "6 5", fillColor: "#ffcf4a", fillOpacity: .08 });
      state.overlayLayers[kind] = L.featureGroup([layer, walkShed, station]);
      return state.overlayLayers[kind];
    }
    state.overlayLayers[kind] = layer;
    return layer;
  }

  async function toggleMapOverlay(button) {
    if (!state.map) return;
    const kind = button.dataset.mapOverlay;
    const turnOn = !button.classList.contains("is-active");
    const status = el("#map-layer-status");
    button.classList.add("is-loading");
    try {
      let layer;
      if (kind === "points") layer = state.markerLayer;
      else if (kind === "neighborhoods") layer = state.polygonLayer;
      else if (kind === "heat") layer = state.overlayLayers.heat || rebuildHeatLayer();
      else layer = await buildBoundaryOverlay(kind);
      state.overlayVisibility[kind] = turnOn;
      if (layer) {
        if (turnOn) layer.addTo(state.map);
        else layer.remove();
      }
      button.classList.toggle("is-active", turnOn);
      if (turnOn && kind === "corridor" && layer && layer.getBounds) state.map.fitBounds(layer.getBounds(), { padding: [22, 22] });
      if (status) status.textContent = turnOn ? CENSUS_LAYERS[kind] ? CENSUS_LAYERS[kind].label + " layer on · official Census geography" : kind === "heat" ? "Heat layer: application density in the current mapped sample" : "Layer on" : "Layer off";
    } catch (error) {
      if (status) status.textContent = "That official layer is temporarily unavailable; no substitute boundary was used.";
    } finally {
      button.classList.remove("is-loading");
    }
  }

  function initMapOverlayTools() {
    els("[data-map-overlay]").forEach(function (button) { button.addEventListener("click", function () { toggleMapOverlay(button); }); });
    els("[data-open-map-overlay]").forEach(function (link) {
      link.addEventListener("click", function () {
        const button = el('[data-map-overlay="' + link.dataset.openMapOverlay + '"]');
        if (button && !button.classList.contains("is-active")) toggleMapOverlay(button);
      });
    });
  }

  function renderNeighborhoodLists(items, map) {
    const home = el("#neighborhood-list");
    const full = el("#full-neighborhood-list");
    function markup(limit) {
      return items.slice(0, limit).map(function (item, index) {
        return '<button class="neighborhood-item" type="button" data-neighborhood-index="' + index + '"><strong>' + escapeHtml(item.name) + '</strong><span>' + item.count + '</span></button>';
      }).join("");
    }
    if (home) home.innerHTML = markup(7) || '<p class="muted">No recent mapped filings matched the official boundary layer.</p>';
    if (full) full.innerHTML = markup(items.length) || '<p class="muted">No matched activity is available.</p>';
    els("[data-neighborhood-index]").forEach(function (button) {
      button.addEventListener("click", function () {
        const item = items[Number(button.dataset.neighborhoodIndex)];
        if (!item) return;
        const layer = L.geoJSON(item.feature);
        map.fitBounds(layer.getBounds(), { padding: [25, 25], maxZoom: 15 });
      });
    });
  }

  function renderNeighborhoodProfiles(items) {
    const profiles = el("#neighborhood-profiles");
    if (!profiles) return;
    if (!items.length) {
      profiles.innerHTML = '<p class="muted">No mapped records matched the official neighborhood layer in the current sample.</p>';
      return;
    }
    function fieldMap(item, index) {
      const geometry = item.feature && item.feature.geometry;
      const polygons = geometry && geometry.type === "Polygon" ? [geometry.coordinates] : geometry && geometry.type === "MultiPolygon" ? geometry.coordinates : [];
      const rings = polygons.map(function (polygon) { return polygon && polygon[0]; }).filter(function (ring) { return Array.isArray(ring) && ring.length > 2; });
      const coordinates = rings.reduce(function (all, ring) { return all.concat(ring); }, []);
      if (!coordinates.length) return "";
      const centerLat = coordinates.reduce(function (sum, point) { return sum + Number(point[1]); }, 0) / coordinates.length;
      const longitudeScale = Math.cos(centerLat * Math.PI / 180);
      const planar = coordinates.map(function (point) { return [Number(point[0]) * longitudeScale, Number(point[1])]; });
      const xs = planar.map(function (point) { return point[0]; });
      const ys = planar.map(function (point) { return point[1]; });
      const minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs), minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
      const width = 520, height = 360, pad = 34;
      const scale = Math.min((width - pad * 2) / Math.max(maxX - minX, .00001), (height - pad * 2) / Math.max(maxY - minY, .00001));
      const usedWidth = (maxX - minX) * scale, usedHeight = (maxY - minY) * scale;
      const offsetX = (width - usedWidth) / 2, offsetY = (height - usedHeight) / 2;
      function project(point) {
        return [offsetX + (Number(point[0]) * longitudeScale - minX) * scale, height - (offsetY + (Number(point[1]) - minY) * scale)];
      }
      const paths = rings.map(function (ring) {
        return ring.map(function (point, pointIndex) { const plotted = project(point); return (pointIndex ? "L" : "M") + plotted[0].toFixed(1) + " " + plotted[1].toFixed(1); }).join(" ") + " Z";
      }).join(" ");
      const dots = item.records.filter(function (record) { return Number.isFinite(Number(record.lat)) && Number.isFinite(Number(record.lon)); }).slice(0, 80).map(function (record, dotIndex) {
        const plotted = project([Number(record.lon), Number(record.lat)]);
        return '<circle class="neighborhood-profile__dot" cx="' + plotted[0].toFixed(1) + '" cy="' + plotted[1].toFixed(1) + '" r="' + (dotIndex < 8 ? "4.2" : "3.1") + '"></circle>';
      }).join("");
      const grid = [80, 160, 240, 320, 400, 480].map(function (x) { return '<path d="M' + x + ' 0V360"></path>'; }).join("") + [60, 120, 180, 240, 300].map(function (y) { return '<path d="M0 ' + y + 'H520"></path>'; }).join("");
      return '<div class="neighborhood-profile__map" aria-hidden="true"><svg viewBox="0 0 520 360" preserveAspectRatio="xMidYMid slice"><g class="neighborhood-profile__grid">' + grid + '</g><path class="neighborhood-profile__boundary" d="' + paths + '"></path><g>' + dots + '</g></svg><span class="neighborhood-profile__map-label"><i></i> Official boundary · live filings</span><strong class="neighborhood-profile__map-count">' + formatNumber(item.count) + '</strong></div>';
    }
    profiles.innerHTML = items.slice(0, 6).map(function (item, index) {
      const declared = item.records.reduce(function (sum, record) { return sum + Number(record.valuation_usd_clean || 0); }, 0);
      const operators = new Set(item.records.map(function (record) { return String(record.contractor_name || "").trim().toLowerCase(); }).filter(Boolean)).size;
      const storm = item.records.filter(isStormRecord).length;
      const dates = item.records.map(function (record) { return record.applied_date; }).filter(Boolean).sort();
      const dateSpan = dates.length ? formatDate(dates[0], { month: "short", day: "numeric" }) + "–" + formatDate(dates[dates.length - 1], { month: "short", day: "numeric", year: "numeric" }) : "Application dates pending";
      const tags = uniqueTags(["format:neighborhood-brief", "geography:" + tagSlug(item.name), "audience:field-desk"].concat(item.records.reduce(function (all, record) { return all.concat(recordTaxonomy(record)); }, [])));
      if (/(downtown|flagler village|progresso|poinsettia)/i.test(item.name)) tags.push("topic:corridor-transit");
      const template = tags.includes("topic:association-condo") ? "association" : tags.includes("topic:waterfront") ? "waterfront" : tags.includes("topic:storm-readiness") && storm >= 3 ? "storm" : tags.includes("topic:corridor-transit") ? "corridor" : tags.includes("urgency:high-value") ? "high-value" : "development";
      tags.push("template:" + template);
      return '<a class="neighborhood-profile neighborhood-profile--' + (index % 3) + ' neighborhood-profile--' + template + '" data-signal-tags="' + taxonomyAttribute(tags) + '" href="neighborhoods.html?area=' + encodeURIComponent(item.name) + '">' + fieldMap(item, index) + '<div class="neighborhood-profile__content">' +
        '<div><span class="neighborhood-profile__rank">0' + (index + 1) + ' · ' + escapeHtml(dateSpan) + '</span><h3>' + escapeHtml(item.name) + '</h3>' + taxonomyLine(tags, "Lens") + '</div>' +
        '<dl><div><dt>Mapped filings</dt><dd>' + formatNumber(item.count) + '</dd></div><div><dt>Declared value</dt><dd>' + (declared > 0 ? escapeHtml(moneyFormat.format(declared)) : 'Not listed') + '</dd></div><div><dt>Storm-relevant</dt><dd>' + formatNumber(storm) + '</dd></div><div><dt>Operators</dt><dd>' + formatNumber(operators) + '</dd></div></dl>' +
        '<span class="neighborhood-profile__link"><i aria-hidden="true"></i> Open field brief →</span></div></a>';
    }).join("");
  }

  function addMapBrand(map) {
    const signalControl = L.control({ position: "bottomleft" });
    signalControl.onAdd = function () {
      const badge = L.DomUtil.create("div", "map-signal-control");
      badge.setAttribute("aria-label", "Florida Signal Development Intelligence");
      badge.innerHTML = '<img src="assets/mark-square.png" alt=""><span><b>Florida Signal</b><small>Development intelligence</small></span>';
      L.DomEvent.disableClickPropagation(badge);
      return badge;
    };
    signalControl.addTo(map);
  }

  function renderSpyglass(name, items, options) {
    const settings = options || {};
    const node = el("#" + name + "-spotlight-map");
    if (!node || !window.L) return;
    const valid = items.filter(function (item) { return Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lon)); });
    if (state.spotlightMaps[name]) {
      state.spotlightMaps[name].remove();
      delete state.spotlightMaps[name];
    }
    if (!valid.length) {
      node.innerHTML = '<div class="spyglass__empty">No source-located points are available. No substitute pins are being drawn.</div>';
      return;
    }
    const map = L.map(node, { zoomControl: true, scrollWheelZoom: false, attributionControl: true, preferCanvas: true }).setView(settings.center || [26.129, -80.144], settings.zoom || 12);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", { maxZoom: 20, attribution: '&copy; OpenStreetMap &copy; CARTO' }).addTo(map);
    addMapBrand(map);
    const bounds = [];
    const titleNode = el("#" + name + "-spotlight-title");
    const metaNode = el("#" + name + "-spotlight-meta");
    const linkNode = el("#" + name + "-spotlight-link");
    function select(item) {
      if (titleNode) titleNode.textContent = item.title;
      if (metaNode) metaNode.textContent = item.meta;
      if (linkNode) {
        linkNode.href = item.url;
        linkNode.textContent = item.linkLabel || "Open this point on the full map →";
      }
    }
    valid.forEach(function (item, index) {
      const point = [Number(item.lat), Number(item.lon)];
      bounds.push(point);
      const marker = L.circleMarker(point, { radius: Math.min(12, 6 + Number(item.weight || 0)), color: "#fff", weight: 2, fillColor: item.color || settings.color || "#009f91", fillOpacity: .94 }).addTo(map);
      marker.bindPopup('<div class="popup-kicker">' + escapeHtml(settings.popupKicker || "Signal Spyglass") + '</div><div class="popup-title">' + escapeHtml(item.title) + '</div><div class="popup-meta">' + escapeHtml(item.meta) + '<br><a href="' + escapeHtml(item.url) + '">' + escapeHtml(item.linkLabel || "Open the connected map") + '</a></div>');
      marker.on("click", function () { select(item); });
      if (index === 0) select(item);
    });
    if (bounds.length === 1) map.setView(bounds[0], settings.singleZoom || 14);
    else map.fitBounds(bounds, { padding: [34, 34], maxZoom: settings.maxZoom || 14 });
    state.spotlightMaps[name] = map;
  }

  function recordSpotlightItem(record) {
    const tags = recordTaxonomy(record);
    return {
      lat: record.lat,
      lon: record.lon,
      title: recordHeadline(record),
      meta: recordPlace(record) + " · applied " + formatDate(record.applied_date, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) + " · " + (record.permit_number || "record ID pending"),
      url: recordUrl(record),
      linkLabel: "Open exact filing on the full map →",
      color: markerColor(record),
      weight: Number(record.valuation_usd_clean || 0) >= 500000 ? 2 : 0,
      tags: tags
    };
  }

  function initRecordSpotlights() {
    const signalRecords = (state.featured.length ? state.featured : state.records).slice(0, 8);
    renderSpyglass("signal", signalRecords.map(recordSpotlightItem), { color: "#009f91", popupKicker: "What Moved Spotlight" });
    const stormRecords = state.records.filter(isStormRecord);
    renderSpyglass("storm", stormRecords.map(recordSpotlightItem), { color: "#a81920", popupKicker: "Storm Readiness Spotlight", maxZoom: 13 });
  }

  function renderMeetingSpotlight(meetings) {
    const rooms = new Map();
    meetings.filter(function (meeting) { return Number.isFinite(Number(meeting.lat)) && Number.isFinite(Number(meeting.lon)); }).forEach(function (meeting) {
      const key = Number(meeting.lat).toFixed(6) + "," + Number(meeting.lon).toFixed(6);
      const existing = rooms.get(key);
      if (existing) {
        existing.count += 1;
        if (String(meeting.date) < String(existing.date)) Object.assign(existing, { date: meeting.date, time: meeting.time, title: meeting.title, url: meeting.agenda_url || meeting.details_url });
      } else rooms.set(key, { lat: meeting.lat, lon: meeting.lon, count: 1, date: meeting.date, time: meeting.time, title: meeting.title, location: meeting.location, url: meeting.agenda_url || meeting.details_url, coordinateSource: meeting.coordinate_source, category: meeting.category });
    });
    const items = Array.from(rooms.values()).map(function (room) {
      return { lat: room.lat, lon: room.lon, weight: Math.min(4, room.count), color: room.category === "industry" ? "#ff6d3a" : "#1767ff", title: room.location.split(" · ")[0], meta: room.count + " upcoming meeting" + (room.count === 1 ? "" : "s") + " here · next " + formatDate(room.date, { month: "short", day: "numeric", year: "numeric" }) + " at " + room.time + " · source-matched room address", url: room.url, linkLabel: "Open the official meeting source ↗" };
    });
    renderSpyglass("meeting", items, { color: "#ff6d3a", popupKicker: "Rooms Watched Spotlight", maxZoom: 12 });
  }

  async function buildMap(node) {
    const map = L.map(node, { zoomControl: true, scrollWheelZoom: false, preferCanvas: true }).setView([26.129, -80.144], 12);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap &copy; CARTO'
    }).addTo(map);
    addMapBrand(map);
    const geojson = await loadNeighborhoods();
    state.polygonLayer = L.geoJSON(geojson, {
      style: { color: "#00796f", weight: 1.1, opacity: .58, fillColor: "#76d4c0", fillOpacity: .055 },
      onEachFeature: function (feature, layer) {
        layer.bindTooltip(neighborhoodName(feature), { sticky: true, direction: "top", opacity: .95 });
        layer.on("click", function () { map.fitBounds(layer.getBounds(), { padding: [22, 22], maxZoom: 15 }); });
      }
    }).addTo(map);
    const records = state.lens === "storm" ? state.records.filter(isStormRecord) : state.records;
    drawMarkers(map, records);
    const items = neighborhoodCounts(geojson.features || [], records);
    renderNeighborhoodLists(items, map);
    renderNeighborhoodProfiles(items);
    const permitParam = new URLSearchParams(window.location.search).get("permit");
    if (permitParam) {
      const target = state.records.find(function (record) { return record.permit_number === permitParam; });
      if (target) {
        map.setView([Number(target.lat), Number(target.lon)], 17);
        state.markerLayer.eachLayer(function (layer) { if (layer.record && layer.record.permit_number === permitParam) layer.openPopup(); });
      }
    }
    const areaParam = new URLSearchParams(window.location.search).get("area");
    if (areaParam) {
      const targetArea = (geojson.features || []).find(function (feature) { return neighborhoodName(feature).toLowerCase() === areaParam.toLowerCase(); });
      if (targetArea) map.fitBounds(L.geoJSON(targetArea).getBounds(), { padding: [25, 25], maxZoom: 15 });
    }
    state.map = map;
    return map;
  }

  async function initMaps() {
    const node = el("#home-map") || el("#full-map");
    if (!node || !window.L || !state.records.length) return;
    try { await buildMap(node); }
    catch (error) {
      node.innerHTML = '<div class="loading-row">The official neighborhood layer is temporarily unavailable. No substitute map is being shown.</div>';
    }
  }

  function initLensSwitch() {
    if (new URLSearchParams(window.location.search).get("storm") === "ready") state.lens = "storm";
    els("[data-map-lens]").forEach(function (button) {
      button.classList.toggle("is-active", button.dataset.mapLens === state.lens);
      button.addEventListener("click", function () {
        state.lens = button.dataset.mapLens;
        els("[data-map-lens]").forEach(function (other) { other.classList.toggle("is-active", other === button); });
        if (!state.map || !state.neighborhoods) return;
        const records = state.lens === "storm" ? state.records.filter(isStormRecord) : state.records;
        drawMarkers(state.map, records);
        if (state.overlayVisibility.heat) {
          const heat = rebuildHeatLayer();
          if (heat) heat.addTo(state.map);
        }
        renderNeighborhoodLists(neighborhoodCounts(state.neighborhoods.features || [], records), state.map);
      });
    });
  }

  function findNeighborhoodForRecord(record) {
    if (!state.neighborhoods || !Number.isFinite(Number(record.lat)) || !Number.isFinite(Number(record.lon))) return "Location not mapped";
    const feature = (state.neighborhoods.features || []).find(function (candidate) { return pointInFeature([Number(record.lon), Number(record.lat)], candidate); });
    return feature ? neighborhoodName(feature) : "Outside matched City boundary";
  }

  function focusRecordOnMap(record) {
    if (!record || !state.map || !Number.isFinite(Number(record.lat)) || !Number.isFinite(Number(record.lon))) return;
    if (state.searchMarker) state.searchMarker.remove();
    state.searchMarker = L.circleMarker([Number(record.lat), Number(record.lon)], { radius: 10, color: "#071b32", weight: 3, fillColor: "#ffcf4a", fillOpacity: .95 }).addTo(state.map).bindPopup(mapPopup(record)).openPopup();
    state.map.setView([Number(record.lat), Number(record.lon)], 17);
    const mapNode = el("#full-map") || el("#home-map");
    if (mapNode) mapNode.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function renderLeadDesk() {
    const list = el("#lead-list");
    if (!list) return;
    const filters = {
      new: function (record) { return String(record.applied_date || "") >= APPLICATION_WINDOW_START; },
      unassigned: function (record) { return !String(record.contractor_name || "").trim(); },
      high: function (record) { return Number(record.valuation_usd_clean || 0) >= 250000; },
      storm: isStormRecord,
      association: isAssociationRecord
    };
    const filter = filters[state.leadLens] || filters.new;
    const candidates = state.records.filter(filter).sort(function (a, b) {
      return String(b.applied_date || "").localeCompare(String(a.applied_date || "")) || Number(b.valuation_usd_clean || 0) - Number(a.valuation_usd_clean || 0);
    }).slice(0, 8);
    state.leadResults = candidates;
    if (!candidates.length) {
      list.innerHTML = '<p class="muted">No qualifying records are present in the current mapped application sample.</p>';
      return;
    }
    list.innerHTML = candidates.map(function (record, index) {
      const value = Number(record.valuation_usd_clean || 0);
      const operator = record.contractor_name ? titleCase(record.contractor_name) : "Operator not listed";
      const tags = recordTaxonomy(record).concat(["format:lead-card", "qualification:" + state.leadLens]);
      return '<div class="lead-card-wrap" data-signal-tags="' + taxonomyAttribute(tags) + '"><button class="lead-card" type="button" data-lead-index="' + index + '">' +
        '<span class="lead-card__date">Applied ' + escapeHtml(formatDate(record.applied_date, { month: "short", day: "numeric", timeZone: "America/New_York" })) + '</span>' +
        '<h3>' + escapeHtml(titleCase(String(record.address || "Address pending").replace(/\s+/g, " "))) + '</h3>' +
        placeSignature(record) +
        taxonomyLine(tags, "Field lens") +
        (isAssociationRecord(record) && record.owner_name ? '<p class="lead-card__association">Association record · ' + escapeHtml(titleCase(record.owner_name)) + '</p>' : '') +
        '<dl><div><dt>Scope</dt><dd>' + escapeHtml(record.work_type ? titleCase(record.work_type.replace(/_/g, " ")) : record.permit_type || "Permit") + '</dd></div><div><dt>Value</dt><dd>' + (value > 0 ? escapeHtml(moneyFormat.format(value)) : "Not listed") + '</dd></div><div><dt>Operator</dt><dd>' + escapeHtml(operator) + '</dd></div><div><dt>Status</dt><dd>' + escapeHtml(record.status || "Filed") + '</dd></div></dl>' +
        '<span class="lead-card__id">' + escapeHtml(record.permit_number || "Permit ID pending") + '</span><span class="lead-card__map-cta"><i aria-hidden="true"></i>Open exact filing on map <b>→</b></span></button>' + recordShareMarkup(record) + '</div>';
    }).join("");
    bindRecordSharing(list);
    els("[data-lead-index]", list).forEach(function (button) {
      button.addEventListener("click", function () { focusRecordOnMap(state.leadResults[Number(button.dataset.leadIndex)]); });
    });
  }

  function initLeadDesk() {
    els("[data-lead-lens]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.leadLens = button.dataset.leadLens;
        els("[data-lead-lens]").forEach(function (other) { other.classList.toggle("is-active", other === button); });
        renderLeadDesk();
      });
    });
  }

  async function runRecordSearch(rawQuery) {
    const input = el("#record-search-input");
    const resultsNode = el("#record-search-results");
    if (!resultsNode) return;
    const query = String(rawQuery || "").trim();
    if (input) input.value = query;
    resultsNode.hidden = false;
    if (query.length < 2) {
      resultsNode.innerHTML = '<p class="record-search__status">Enter at least two characters to search the record.</p>';
      return;
    }
    resultsNode.innerHTML = '<p class="record-search__status"><span class="pulse" aria-hidden="true"></span> Searching the live permit record…</p>';
    const safe = query.replace(/[,()*%]/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);
    let matches = [];
    let fullSearch = true;
    try {
      const filter = "(address.ilike.*" + safe + "*,permit_number.ilike.*" + safe + "*,contractor_name.ilike.*" + safe + "*,permit_type.ilike.*" + safe + "*,description.ilike.*" + safe + "*)";
      const response = await supabase("permits", { select: recordSelect, or: filter, limit: "24" });
      matches = await response.json();
    } catch (error) {
      fullSearch = false;
      const needle = safe.toLowerCase();
      matches = state.records.filter(function (record) {
        return [record.address, record.permit_number, record.contractor_name, record.permit_type, record.description].join(" ").toLowerCase().includes(needle);
      }).slice(0, 24);
    }
    matches.sort(function (a, b) { return String(b.applied_date || "").localeCompare(String(a.applied_date || "")) || String(b.last_seen_at || "").localeCompare(String(a.last_seen_at || "")); });
    state.searchResults = matches;
    const status = matches.length ? (matches.length === 24 ? "Showing the first 24 matching records" : formatNumber(matches.length) + " matching record" + (matches.length === 1 ? "" : "s")) : "No matching public records found";
    const scope = fullSearch ? "live permit table" : "current map sample — full search temporarily unavailable";
    resultsNode.innerHTML = '<div class="record-search-results__head"><p><strong>' + escapeHtml(status) + '</strong><span>“' + escapeHtml(query) + '” · ' + escapeHtml(scope) + '</span></p><button type="button" data-close-search aria-label="Close search results">×</button></div>' +
      (matches.length ? '<div class="record-result-list">' + matches.map(function (record, index) {
        const value = Number(record.valuation_usd_clean || 0);
        const tags = recordTaxonomy(record).concat(["format:search-result"]);
        return '<div class="record-result-wrap" data-signal-tags="' + taxonomyAttribute(tags) + '"><button class="record-result" type="button" data-record-result="' + index + '"><span class="record-result__type">' + escapeHtml(record.permit_type || record.permit_category || "Permit") + '</span><strong>' + escapeHtml(titleCase(String(record.address || "Address pending").replace(/\s+/g, " "))) + '</strong>' + placeSignature(record) + taxonomyLine(tags, "Filed under") + '<span>' + escapeHtml(record.contractor_name ? titleCase(record.contractor_name) : "Contractor not listed") + '</span><em>' + (value > 0 ? escapeHtml(moneyFormat.format(value)) : "Value not listed") + ' · ' + escapeHtml(formatDate(recordDate(record), { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + '</em></button>' + recordShareMarkup(record) + '</div>';
      }).join("") + '</div>' : '<p class="record-search__empty">Try a street name, permit number, company, or work type such as roof, seawall or demolition.</p>');
    bindRecordSharing(resultsNode);
    const close = el("[data-close-search]", resultsNode);
    if (close) close.addEventListener("click", function () { resultsNode.hidden = true; });
    els("[data-record-result]", resultsNode).forEach(function (button) {
      button.addEventListener("click", function () {
        const record = state.searchResults[Number(button.dataset.recordResult)];
        focusRecordOnMap(record);
      });
    });
    const url = new URL(window.location.href);
    url.searchParams.set("q", query);
    window.history.replaceState({}, "", url);
  }

  function initRecordSearch() {
    const launcher = el("#field-search-launcher");
    if (launcher) launcher.addEventListener("submit", function (event) {
      event.preventDefault();
      const input = el('input[name="q"]', launcher);
      window.location.href = "neighborhoods.html?q=" + encodeURIComponent(input ? input.value.trim() : "");
    });
    const form = el("#record-search");
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const input = el('input[name="q"]', form);
      runRecordSearch(input ? input.value : "");
    });
    els("[data-quick-search]", form).forEach(function (button) {
      button.addEventListener("click", function () { runRecordSearch(button.dataset.quickSearch); });
    });
  }

  async function loadStorms() {
    const status = el("#storm-status");
    const updated = el("#storm-updated");
    if (!status && !updated && !el("#graphic-desk") && !el("#storm-operations")) return;
    try {
      let response = await fetch("/api/storms", { cache: "no-store" });
      if (!response.ok) response = await fetch("https://www.nhc.noaa.gov/CurrentStorms.json", { cache: "no-store" });
      if (!response.ok) throw new Error("NHC unavailable");
      const data = await response.json();
      const storms = (data.activeStorms || []).filter(function (storm) { return String(storm.id || "").toLowerCase().startsWith("al"); });
      state.storms = storms;
      state.stormPayload = data;
      if (status) status.textContent = storms.length ? storms.map(function (storm) { return storm.name + " · " + storm.classification + " " + storm.intensity + " kt"; }).join(" · ") : "No named Atlantic storms active";
      const responseState = el("#storm-response-state");
      if (responseState) responseState.textContent = storms.length ? formatNumber(storms.length) + " Atlantic system" + (storms.length === 1 ? "" : "s") : "Standby";
      const newest = storms[0];
      if (updated) updated.textContent = newest && newest.lastUpdate ? "NHC " + formatDate(newest.lastUpdate, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET" : "NHC live";
      renderStormOperations(data);
      renderGraphicDesk();
    } catch (error) {
      if (status) status.textContent = "Open the official NHC outlook";
      const responseState = el("#storm-response-state");
      if (responseState) responseState.textContent = "Source check needed";
      if (updated) updated.textContent = "Source link active";
      renderStormOperations(null);
      renderGraphicDesk();
    }
  }

  async function loadMeetings() {
    const date = el("[data-meeting-date]");
    const title = el("[data-meeting-title]");
    const meta = el("[data-meeting-meta]");
    const agenda = el("[data-meeting-agenda]");
    const video = el("[data-meeting-video]");
    const meetingList = el("#meeting-list");
    if ((!date || !title || !meta || !agenda || !video) && !meetingList && !el("#graphic-desk")) return;
    try {
      const response = await fetch("/api/meetings", { cache: "no-store" });
      if (!response.ok) throw new Error("Meeting calendar unavailable");
      const payload = await response.json();
      const meetings = Array.isArray(payload.meetings) ? payload.meetings : [];
      if (!meetings.length) throw new Error("No upcoming meetings published");
      state.meetings = meetings;
      if (date && title && meta && agenda && video) {
        let meetingIndex = 0;
        function renderMeeting() {
          const meeting = meetings[meetingIndex % meetings.length];
          const meetingDate = new Date(meeting.date + "T12:00:00");
          date.textContent = formatDate(meetingDate, { weekday: "short", month: "short", day: "numeric" }) + (meeting.time ? " · " + meeting.time : "");
          title.textContent = meeting.title;
          const remaining = Math.max(0, meetings.length - 1);
          meta.textContent = meeting.location + (remaining ? " · " + remaining + " more watched" : "");
          agenda.href = meeting.agenda_url || meeting.details_url || payload.calendar_url;
          agenda.textContent = (meeting.link_label || (meeting.agenda_available ? "Agenda" : "Official calendar")) + " ↗";
          if (meeting.watch_url) {
            video.href = meeting.watch_url;
            video.hidden = false;
          } else {
            video.hidden = true;
          }
          els("[data-mobile-meeting-title]").forEach(function (node) { node.textContent = meeting.title; });
          els("[data-mobile-meeting-date]").forEach(function (node) { node.textContent = date.textContent + " · " + meeting.location; });
          meetingIndex += 1;
        }
        renderMeeting();
        window.setInterval(renderMeeting, 12000);
      }
      renderMeetingPage(meetings, payload);
      renderGraphicDesk();
    } catch (error) {
      if (date && title && meta && agenda && video) {
        date.textContent = "Source check needed";
        title.textContent = "Open the official meeting calendar";
        meta.textContent = "No meeting is being inferred from stale data";
        agenda.href = "https://fortlauderdale.legistar.com/Calendar.aspx";
        agenda.textContent = "Official calendar ↗";
        video.hidden = true;
      }
      if (meetingList) meetingList.innerHTML = '<p class="meeting-empty">Meeting feed unavailable. <a href="https://fortlauderdale.legistar.com/Calendar.aspx" target="_blank" rel="noreferrer">Open the official calendar ↗</a></p>';
    }
  }

  function renderMeetingPage(meetings, payload) {
    const list = el("#meeting-list");
    if (!list) return;
    const count = el("#meeting-count");
    const updated = el("#meeting-feed-updated");
    if (count) count.textContent = formatNumber(meetings.length) + " upcoming meetings watched";
    if (updated) updated.textContent = "Official calendar checked " + formatDate(payload.updated_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET · 15-minute cache";

    function meetingType(meeting) {
      const value = meeting.title.toLowerCase();
      if (value.includes("development review")) return "development";
      if (meeting.category === "industry") return "industry";
      if (value.includes("commission") || value.includes("workshop")) return "commission";
      return "boards";
    }
    function render(filter) {
      const visible = filter === "all" ? meetings : meetings.filter(function (meeting) { return meetingType(meeting) === filter; });
      list.innerHTML = visible.map(function (meeting) {
        const meetingDate = new Date(meeting.date + "T12:00:00");
        const daysAway = Math.max(0, Math.ceil((meetingDate.getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000));
        const agendaLabel = (meeting.link_label || (meeting.agenda_available ? "Agenda" : "Agenda source")) + " ↗";
        const type = meetingType(meeting);
        const tags = ["format:meeting", "topic:" + type, "source:" + tagSlug(meeting.source), "geography:" + tagSlug(meeting.location || "broward"), meeting.agenda_available ? "urgency:agenda-posted" : "urgency:agenda-watch"];
        return '<article class="meeting-row" data-signal-tags="' + taxonomyAttribute(tags) + '">' +
          '<div class="meeting-row__date"><span>' + escapeHtml(formatDate(meetingDate, { weekday: "short" })) + '</span><strong>' + escapeHtml(formatDate(meetingDate, { day: "numeric" })) + '</strong><small>' + escapeHtml(formatDate(meetingDate, { month: "short" })) + ' · ' + escapeHtml(meeting.time || "Time pending") + '</small></div>' +
          '<div class="meeting-row__body"><p>' + escapeHtml(meeting.source) + ' · ' + escapeHtml(meeting.status || (daysAway ? "in " + daysAway + " days" : "today")) + (daysAway ? " · in " + daysAway + " days" : "") + '</p>' + taxonomyLine(tags, "Watch") + '<h2>' + escapeHtml(meeting.title) + '</h2><span>' + escapeHtml(meeting.location || "Location pending") + '</span></div>' +
          '<div class="meeting-row__actions"><a href="' + escapeHtml(meeting.agenda_url || meeting.details_url || payload.calendar_url) + '" target="_blank" rel="noreferrer">' + agendaLabel + '</a>' +
          (meeting.watch_url ? '<a class="meeting-row__watch" href="' + escapeHtml(meeting.watch_url) + '" target="_blank" rel="noreferrer"><span class="meeting-tv" aria-hidden="true"></span>Watch</a>' : '<span>Agenda watch</span>') +
          (meeting.ical_url ? '<a href="' + escapeHtml(meeting.ical_url) + '" target="_blank" rel="noreferrer">Add to calendar ↗</a>' : '') + '</div></article>';
      }).join("") || '<p class="meeting-empty">No published meetings match this view.</p>';
      renderMeetingSpotlight(visible);
    }
    els("[data-meeting-filter]").forEach(function (button) {
      button.addEventListener("click", function () {
        els("[data-meeting-filter]").forEach(function (candidate) { candidate.classList.toggle("is-active", candidate === button); });
        render(button.getAttribute("data-meeting-filter") || "all");
      });
    });
    render("all");
  }

  async function loadAgendaRecon() {
    const mapNode = el("#agenda-recon-map");
    const results = el("#agenda-recon-results");
    if (!mapNode || !results) return;
    try {
      const response = await fetch("/api/agenda-recon", { cache: "no-store" });
      if (!response.ok) throw new Error("Agenda recon unavailable");
      const payload = await response.json();
      const items = Array.isArray(payload.items) ? payload.items : [];
      const rooms = el("#recon-rooms");
      const packets = el("#recon-packets");
      const properties = el("#recon-properties");
      const status = el("#recon-map-status");
      if (rooms) rooms.textContent = formatNumber(payload.rooms_watched);
      if (packets) packets.textContent = formatNumber(payload.packets_posted);
      if (properties) properties.textContent = formatNumber(payload.properties_cleared);
      if (window.L) {
        const reconMap = L.map(mapNode, { zoomControl: true, scrollWheelZoom: false, attributionControl: true }).setView([26.129, -80.144], 12);
        L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", { maxZoom: 20, attribution: '&copy; OpenStreetMap &copy; CARTO' }).addTo(reconMap);
        addMapBrand(reconMap);
        const bounds = [];
        items.forEach(function (item) {
          const point = [Number(item.lat), Number(item.lon)];
          bounds.push(point);
          L.circleMarker(point, { radius: 8, color: "#071b32", weight: 2, fillColor: "#ffcf4a", fillOpacity: .95 }).addTo(reconMap).bindPopup('<strong>' + escapeHtml(item.property_address) + '</strong><br>' + escapeHtml(item.meeting_title) + ' · item ' + escapeHtml(item.item_number));
        });
        if (bounds.length) reconMap.fitBounds(bounds, { padding: [35, 35], maxZoom: 15 });
      }
      if (status) status.textContent = items.length ? formatNumber(items.length) + " source-cleared agenda propert" + (items.length === 1 ? "y" : "ies") : "No future property item has cleared the source gate yet";
      results.innerHTML = items.length ? items.map(function (item) {
        return '<article class="recon-result"><p>' + escapeHtml(item.meeting_date) + ' · item ' + escapeHtml(item.item_number) + '</p><h3>' + escapeHtml(item.property_address) + '</h3><span>' + escapeHtml(item.proposed_action || item.meeting_title) + '</span><div><a href="' + escapeHtml(item.source_url) + '" target="_blank" rel="noreferrer">Open cited packet ↗</a><a href="neighborhoods.html?q=' + encodeURIComponent(item.property_address) + '">Open field map →</a></div></article>';
      }).join("") : '<p class="meeting-empty"><strong>Watching, not guessing.</strong> No upcoming official packet currently contains a property item that has completed extraction, coordinate resolution and editorial clearance.</p>';
    } catch (error) {
      results.innerHTML = '<p class="meeting-empty">Agenda sweep is temporarily unavailable. No cached or inferred property pins are being substituted.</p>';
      const status = el("#recon-map-status");
      if (status) status.textContent = "Source check needed";
    }
  }

  function renderStormRecords() {
    const records = state.records.filter(isStormRecord);
    const count = el("#storm-permit-count");
    if (count) count.textContent = formatNumber(records.length);
    const preparation = state.records.filter(function (record) { return /(roof|impact|shutter|generator|seawall|sea wall|drain|flood|elevation|window|door)/i.test([record.permit_type, record.permit_category, record.description].join(" ")); });
    const recovery = state.records.filter(function (record) { return /(repair|restore|restoration|remediation|damage|roof|demolition|rebuild)/i.test([record.permit_type, record.permit_category, record.description].join(" ")); });
    const preCount = el("#storm-phase-pre");
    const recoveryCount = el("#storm-phase-recovery");
    if (preCount) preCount.textContent = formatNumber(preparation.length) + " records";
    if (recoveryCount) recoveryCount.textContent = formatNumber(recovery.length) + " records";
    const list = el("#storm-records");
    if (!list) return;
    list.innerHTML = records.slice(0, 7).map(function (record) {
      const tags = recordTaxonomy(record).concat(["format:storm-spotlight"]);
      return '<a class="storm-record" data-signal-tags="' + taxonomyAttribute(tags) + '" href="' + recordUrl(record) + '">' + taxonomyLine(tags, "Readiness lens") + '<strong>' + escapeHtml(recordHeadline(record)) + '</strong><span>' + escapeHtml(record.permit_number || "Public record") + ' · ' + escapeHtml(formatDate(recordDate(record), { month: "short", day: "numeric", timeZone: "America/New_York" })) + '</span></a>';
    }).join("") || '<p class="muted">No storm-relevant filings are present in the current map sample.</p>';
  }

  function renderGraphicDesk() {
    const root = el("#graphic-desk");
    if (!root) return;
    const payload = state.dashboard && state.dashboard.payload ? state.dashboard.payload : null;
    if (!payload && !state.records.length) return;
    const stats = payload && payload.stats ? payload.stats : {};
    const ptypes = payload && Array.isArray(payload.ptypes) ? payload.ptypes.slice(0, 6) : [];
    const values = payload && Array.isArray(payload.valdist) ? payload.valdist : [];
    const contractors = payload && Array.isArray(payload.contractors) ? payload.contractors.slice(0, 6) : [];

    const applicationCounts = state.applicationDates.reduce(function (result, date) { result[date] = (result[date] || 0) + 1; return result; }, {});
    const applicationDays = [];
    for (let dayIndex = 0; dayIndex < 14; dayIndex += 1) {
      const day = new Date(applicationWindowDate.getFullYear(), applicationWindowDate.getMonth(), applicationWindowDate.getDate() + dayIndex);
      const key = day.getFullYear() + "-" + String(day.getMonth() + 1).padStart(2, "0") + "-" + String(day.getDate()).padStart(2, "0");
      applicationDays.push({ label: key.slice(5), value: applicationCounts[key] || 0 });
    }
    const applicationTotal = applicationDays.reduce(function (sum, day) { return sum + day.value; }, 0);
    const applicationMax = Math.max.apply(null, applicationDays.map(function (day) { return day.value; }).concat([1]));

    const streetCounts = state.records.reduce(function (result, record) {
      const street = String(record.address || "").toUpperCase().replace(/^\s*\d+[A-Z-]*\s+/, "").replace(/\s+(APT|UNIT|STE|#).*$/, "").replace(/\s+/g, " ").trim();
      if (street.length >= 4) result[street] = (result[street] || 0) + 1;
      return result;
    }, {});
    const streets = Object.keys(streetCounts).map(function (name) { return { label: titleCase(name), value: streetCounts[name] }; }).sort(function (a, b) { return b.value - a.value; }).slice(0, 5);

    const neighborhoodItems = state.neighborhoods ? neighborhoodCounts(state.neighborhoods.features || [], state.records).slice(0, 7).map(function (item) { return { label: item.name, value: item.count }; }) : streets;
    const zipItems = state.zipBoundaries ? (state.zipBoundaries.features || []).map(function (feature) {
      const hits = state.records.filter(function (record) { return pointInFeature([Number(record.lon), Number(record.lat)], feature); });
      return { label: String((feature.properties || {}).ZCTA5 || (feature.properties || {}).NAME || "ZIP"), value: hits.length };
    }).filter(function (item) { return item.value > 0; }).sort(function (a, b) { return b.value - a.value || a.label.localeCompare(b.label); }).slice(0, 5) : [];

    const tradeDefinitions = [
      { label: "Roofs", test: /roof/i },
      { label: "Windows + doors", test: /(window|door|glazing|shutter)/i },
      { label: "Electrical", test: /(electric|generator|solar)/i },
      { label: "Mechanical", test: /(mechanical|hvac|air condition)/i },
      { label: "Plumbing", test: /(plumb|sewer|drain)/i },
      { label: "Marine + seawall", test: /(marine|seawall|sea wall|dock)/i }
    ];
    const trades = tradeDefinitions.map(function (family) {
      return { label: family.label, value: state.records.filter(function (record) { return family.test.test([record.permit_type, record.permit_category, record.description].join(" ")); }).length };
    }).sort(function (a, b) { return b.value - a.value; }).slice(0, 5);

    const highValue = state.featured.filter(function (record) { return Number(record.valuation_usd_clean) > 0; });
    const highValueTotal = highValue.reduce(function (sum, record) { return sum + Number(record.valuation_usd_clean || 0); }, 0);
    const highValueTop = highValue.slice().sort(function (a, b) { return Number(b.valuation_usd_clean || 0) - Number(a.valuation_usd_clean || 0); })[0];
    const stormRecords = state.records.filter(isStormRecord);
    const nextMeeting = state.meetings[0];
    const applicationThrough = state.applicationDates.concat(state.records.map(function (record) { return record.applied_date; })).filter(Boolean).sort().slice(-1)[0];
    const stampDate = function (value) { return value ? formatDate(value, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) : "source date pending"; };
    const spanDate = function (start, end) { return start && end ? stampDate(start) + "–" + stampDate(end) : "span pending"; };
    const mappedDates = state.records.map(function (record) { return record.applied_date; }).filter(Boolean).sort();
    const featuredDates = state.featured.map(function (record) { return record.applied_date; }).filter(Boolean).sort();
    const meetingDates = state.meetings.map(function (meeting) { return meeting.date; }).filter(Boolean).sort();
    const applicationWindowStamp = "Window " + spanDate(APPLICATION_WINDOW_START, now.toISOString().slice(0, 10));
    const mappedStamp = "Newest " + formatNumber(state.records.length) + " mapped · " + spanDate(mappedDates[0], mappedDates.slice(-1)[0]);
    const featuredStamp = formatNumber(state.featured.length) + "-record queue · " + spanDate(featuredDates[0], featuredDates.slice(-1)[0]);
    const cacheStamp = "Snapshot updated " + stampDate(state.dashboard && state.dashboard.updated_at);
    const browardStamp = "Cumulative · through " + stampDate(stats.broward_fresh);
    const sourceCheckStamp = "Source checked " + stampDate(now.toISOString());
    const meetingStamp = "Meetings " + spanDate(meetingDates[0], meetingDates.slice(-1)[0]);

    function bars(items, colorClass) {
      const maximum = Math.max.apply(null, items.map(function (item) { return Number(item.value || item.n || 0); }).concat([1]));
      return '<div class="graphic-bars">' + items.map(function (item, index) {
        const value = Number(item.value || item.n || 0);
        return '<div class="graphic-bar-row"><span>' + escapeHtml(item.label || item.t || item.b || item.c) + '</span><div><i class="' + (colorClass || "") + '" style="--graphic-width:' + Math.max(value ? 4 : 0, Math.round(value / maximum * 100)) + '%;--graphic-delay:' + (index * .07) + 's"></i></div><strong>' + escapeHtml(formatNumber(value, value >= 10000)) + '</strong></div>';
      }).join("") + '</div>';
    }

    function tiles(items) {
      return '<div class="graphic-tiles">' + items.map(function (item) { return '<div><strong>' + escapeHtml(item.value) + '</strong><span>' + escapeHtml(item.label) + '</span></div>'; }).join("") + '</div>';
    }

    function bubbles(items) {
      const maximum = Math.max.apply(null, items.map(function (item) { return Number(item.value || 0); }).concat([1]));
      return '<div class="graphic-bubbles">' + items.map(function (item, index) {
        const ratio = Number(item.value || 0) / maximum;
        return '<div style="--bubble-size:' + Math.round(62 + ratio * 78) + 'px;--bubble-delay:' + (index * .06) + 's"><strong>' + escapeHtml(formatNumber(item.value)) + '</strong><span>' + escapeHtml(item.label) + '</span></div>';
      }).join("") + '</div>';
    }

    function rings(items) {
      const maximum = Math.max.apply(null, items.map(function (item) { return Number(item.value || 0); }).concat([1]));
      return '<div class="graphic-rings">' + items.map(function (item, index) {
        const percent = Math.max(Number(item.value || 0) ? 4 : 0, Math.round(Number(item.value || 0) / maximum * 100));
        return '<div class="graphic-ring"><i style="--ring-value:' + percent + ';--ring-delay:' + (index * .08) + 's"><b>' + escapeHtml(formatNumber(item.value)) + '</b></i><span>' + escapeHtml(item.label) + '</span></div>';
      }).join("") + '</div>';
    }

    function ranks(items) {
      return '<ol class="graphic-rank">' + items.map(function (item, index) {
        return '<li><em>' + String(index + 1).padStart(2, "0") + '</em><span>' + escapeHtml(item.label || item.c || item.name) + '</span><strong>' + escapeHtml(formatNumber(item.value || item.n)) + '</strong></li>';
      }).join("") + '</ol>';
    }

    function network(items) {
      return '<div class="graphic-network"><div class="graphic-network__core"><img src="assets/mark-square.png" alt=""><span>ENTITY<br>LENS</span></div>' + items.map(function (item, index) {
        return '<div class="graphic-network__node graphic-network__node--' + (index + 1) + '"><strong>' + escapeHtml(item.value) + '</strong><span>' + escapeHtml(item.label) + '</span></div>';
      }).join("") + '</div>';
    }

    function meetingTimeline(items) {
      return '<div class="graphic-timeline">' + items.slice(0, 5).map(function (meeting, index) {
        return '<div><i></i><time>' + escapeHtml(formatDate(meeting.date, { month: "short", day: "numeric", timeZone: "America/New_York" })) + '</time><span>' + escapeHtml(meeting.title) + '</span><small>' + escapeHtml(meeting.location || "Official room") + '</small></div>';
      }).join("") + '</div>';
    }

    function card(slug, kicker, title, dek, body, options) {
      const settings = options || {};
      const pageUrl = window.location.origin + window.location.pathname.replace(/[^/]*$/, "") + "share/" + encodeURIComponent(slug) + ".html";
      const embedUrl = window.location.origin + window.location.pathname + "?embed=" + encodeURIComponent(slug);
      const embedCode = '<iframe src="' + embedUrl + '" width="100%" height="620" loading="lazy" title="Florida Signal — ' + title.replace(/<[^>]+>/g, "") + '"></iframe>';
      const shareTitle = "Florida Signal · " + title.replace(/<[^>]+>/g, "");
      const tags = uniqueTags(["format:graphic", "source:florida-signal", "topic:" + tagSlug(slug)].concat(settings.tags || []));
      return '<article class="graphic-card ' + (settings.tone === "navy" ? "graphic-card--navy " : "") + (settings.wide ? "graphic-card--wide" : "") + '" data-signal-tags="' + taxonomyAttribute(tags) + '" id="' + slug + '">' +
        '<div class="graphic-card__top"><p>' + escapeHtml(kicker) + '</p><span>' + escapeHtml(settings.status || "REAL RECORD") + '</span></div>' +
        '<h2>' + title + '</h2><p class="graphic-card__dek">' + dek + '</p><div class="graphic-card__body">' + body + '</div>' +
        '<p class="graphic-card__clock">' + escapeHtml(settings.clock || "Public event date · source cache shown") + '</p><a class="graphic-card__sponsor" href="mailto:desk@thefloridasignal.com?subject=' + encodeURIComponent("Sponsor Florida Signal graphic: " + slug) + '"><span>Present this intelligence</span><strong>Your logo here ↗</strong></a>' +
        '<div class="graphic-card__brand"><span><img src="assets/' + (settings.tone === "navy" ? "mark-white.png" : "mark-full-color.png") + '" alt=""><b>Florida Signal</b><small>Development intelligence</small></span><time>' + escapeHtml(settings.stamp || applicationWindowStamp) + '</time><div>' +
        '<a href="https://twitter.com/intent/tweet?text=' + encodeURIComponent(shareTitle) + '&url=' + encodeURIComponent(pageUrl) + '" target="_blank" rel="noreferrer" aria-label="Share on X">X</a>' +
        '<a href="https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(pageUrl) + '" target="_blank" rel="noreferrer" aria-label="Share on LinkedIn">in</a>' +
        '<a href="https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(pageUrl) + '" target="_blank" rel="noreferrer" aria-label="Share on Facebook">f</a>' +
        '<button type="button" data-share-card data-share-url="' + escapeHtml(pageUrl) + '" data-share-title="' + escapeHtml(shareTitle) + '" aria-label="Share this graphic">↗</button>' +
        '<button type="button" data-copy-embed data-embed-code="' + escapeHtml(embedCode) + '">&lt;/&gt; Embed</button></div></div></article>';
    }

    const pulseBody = '<div class="graphic-pulse">' + applicationDays.map(function (day, index) {
      return '<div title="' + escapeHtml(day.label + ': ' + formatNumber(day.value) + ' applications') + '"><span>' + escapeHtml(formatNumber(day.value)) + '</span><i style="--graphic-height:' + Math.max(day.value ? 3 : 0, Math.round(day.value / applicationMax * 100)) + '%;--graphic-delay:' + (index * .04) + 's"></i><small>' + escapeHtml(day.label) + '</small></div>';
    }).join("") + '</div>';
    const parcelCoverage = Number(stats.permits_total || 0) > 0 ? Math.round(Number(stats.p_parcel || 0) / Number(stats.permits_total) * 100) : 0;
    const recordRings = rings([
      { label: "Broward instruments", value: Number(stats.broward_docs || 0) },
      { label: "Parcel-linked permits", value: Number(stats.p_parcel || 0) },
      { label: "Ownership changes", value: Number(stats.owner_chg || 0) },
      { label: "Flip signals", value: Number(stats.flip || 0) }
    ]);
    const placeBody = '<div class="graphic-geo"><section><p>NEIGHBORHOOD CONSTELLATION</p>' + bubbles(neighborhoodItems) + '</section><section><p>ZIP SIGNAL RINGS</p>' + (zipItems.length ? rings(zipItems) : '<div class="graphic-empty">ZIP boundary match loading…</div>') + '</section></div>';
    const companyNetwork = network([
      { value: formatNumber(stats.owner_chg), label: "Owner changes" },
      { value: formatNumber(stats.eff_owner), label: "Owners resolved" },
      { value: formatNumber(stats.eff_value), label: "Values joined" },
      { value: formatNumber(stats.p_parcel), label: "Parcel links" }
    ]);
    const stormRadar = '<div class="graphic-radar"><div class="graphic-radar__sweep"></div><div class="graphic-radar__core"><strong>' + formatNumber(stormRecords.length) + '</strong><span>local hardening<br>records</span></div>' + (state.storms.length ? state.storms.slice(0, 3).map(function (storm, index) { return '<i class="graphic-radar__blip graphic-radar__blip--' + (index + 1) + '" title="' + escapeHtml(storm.name) + '"></i>'; }).join("") : '<b class="graphic-radar__standby">NHC STANDBY</b>') + '</div>';
    const cards = [
      card("application-pulse", "APPLICATION DATES · 14 CALENDAR DAYS", formatNumber(applicationTotal) + " <em>FILED</em>", "Fort Lauderdale permit applications grouped by the date the public application was filed—not by the day a batch arrived.", pulseBody, { tone: "navy", wide: true, status: "LIVE QUERY", stamp: applicationWindowStamp, clock: "City permit table · applied_date · window " + spanDate(APPLICATION_WINDOW_START, now.toISOString().slice(0, 10)) + " · latest filing present " + stampDate(applicationThrough) + " · zero days retained" }),
      card("place-lens", "HYPERLOCAL · OFFICIAL BOUNDARIES", "PLACE <em>LENS</em>", "The newest geocoded application sample resolved into official City neighborhoods and Census ZIP areas. Circle size expresses relative filing count inside this sample.", placeBody, { wide: true, status: "CITY + CENSUS", stamp: mappedStamp, clock: "Newest " + formatNumber(state.records.length) + " geocoded permit applications returned · applied_date span " + spanDate(mappedDates[0], mappedDates.slice(-1)[0]) + " · City neighborhoods + Census ZCTAs" }),
      card("trades-pulse", "NEWEST MAPPED APPLICATION SAMPLE", "TRADES <em>PULSE</em>", "A circular read of storm-hardening, mechanical and building work visible in the newest mapped public-record sample.", rings(trades), { tone: "navy", stamp: mappedStamp, clock: "Newest " + formatNumber(state.records.length) + " geocoded applications · applied_date span " + spanDate(mappedDates[0], mappedDates.slice(-1)[0]) + " · classified from permit fields" }),
      card("high-value", "CAPPED HIGH-VALUE FILING QUEUE", highValueTop ? escapeHtml(moneyFormat.format(Number(highValueTop.valuation_usd_clean))) + " <em>TOP FILING</em>" : "VALUE <em>PENDING</em>", highValueTop ? escapeHtml(recordHeadline(highValueTop)) : "No valued high-dollar filing is available in the current query.", tiles([{ value: highValue.length ? formatNumber(highValue.length) : "0", label: "valued records returned" }, { value: highValueTotal ? compactFormat.format(highValueTotal) : "$0", label: "declared value in returned queue" }]), { stamp: featuredStamp, clock: "First " + formatNumber(state.featured.length) + " records in ordered current-month $100K+ query · applied_date span " + spanDate(featuredDates[0], featuredDates.slice(-1)[0]) + " · not a complete monthly total" }),
      card("value-universe", "ENRICHED PROPERTY CONTEXT", "VALUE <em>LADDER</em>", "Where parcel-linked permit records sit across the best-available property-value universe.", bars(values), { tone: "navy", stamp: cacheStamp, clock: "Supabase dashboard cache · enriched property values · cache timestamp shown by site" }),
      card("operator-board", "NORMALIZED CONTRACTOR NAMES", "OPERATOR <em>BOARD</em>", "A true leaderboard—not another bar chart—of names appearing most often in the normalized public cache.", ranks(contractors), { stamp: cacheStamp, clock: "Supabase dashboard cache · normalized contractor names · not a performance ranking" }),
      card("records-desk", "BROWARD RECORD · CIRCULAR COVERAGE", "RECORDS <em>DESK</em>", "Clerk and parcel layers that power ownership and lien intelligence. Relative rings compare cache scale; they do not imply the categories share a denominator.", recordRings + '<p class="graphic-inline-stat"><strong>' + formatNumber(parcelCoverage) + '%</strong> of tracked permit records parcel-linked</p>', { tone: "navy", stamp: browardStamp, clock: "Broward/Supabase cache · latest recording date " + (stats.broward_fresh ? formatDate(stats.broward_fresh, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) : "pending") }),
      card("company-lens", "SUNBIZ + OWNERSHIP RESOLUTION", "WHO IS <em>BEHIND IT</em>", "The geeky part: an address becomes an entity trail through public company filings, parcel joins and recorded instruments.", companyNetwork, { stamp: cacheStamp, clock: "Supabase cache · state registration/filing dates for company movement; pull time is freshness only" }),
      card("storm-window", "NHC + STORM-RELEVANT FILINGS", state.storms.length ? formatNumber(state.storms.length) + " <em>ATLANTIC ACTIVE</em>" : "STORM <em>STANDBY</em>", state.storms.length ? state.storms.map(function (storm) { return escapeHtml(storm.name + " · " + storm.classification); }).join(" · ") : "No named Atlantic system is currently active. Preparation and recovery filings remain searchable.", stormRadar, { tone: "navy", stamp: sourceCheckStamp, clock: "NHC source checked " + stampDate(now.toISOString()) + " · local hardening count uses mapped applied_date span " + spanDate(mappedDates[0], mappedDates.slice(-1)[0]) }),
      card("meetings-watch", "PUBLIC + INDUSTRY ROOMS", nextMeeting ? escapeHtml(formatDate(nextMeeting.date, { month: "short", day: "numeric", timeZone: "America/New_York" })) + " <em>ON DECK</em>" : "ROOMS <em>WATCHED</em>", nextMeeting ? escapeHtml(nextMeeting.title) : "The official calendar is being checked; no meeting is inferred from stale data.", state.meetings.length ? meetingTimeline(state.meetings) : '<div class="graphic-empty">Official calendar check in progress…</div>', { stamp: meetingStamp, clock: "Scheduled meeting span " + spanDate(meetingDates[0], meetingDates.slice(-1)[0]) + " · official/public and named industry calendars · 15-minute site cache" })
    ];

    const embedSlug = new URLSearchParams(window.location.search).get("embed");
    const visibleCards = embedSlug ? cards.filter(function (html) { return html.includes('id="' + embedSlug + '"'); }) : cards;
    if (embedSlug) document.body.classList.add("graphic-embed");
    root.innerHTML = visibleCards.join("") || '<p class="loading-row">That graphic is not available.</p>';
    els("[data-copy-embed]", root).forEach(function (button) {
      button.addEventListener("click", async function () {
        const code = button.getAttribute("data-embed-code") || "";
        try {
          await navigator.clipboard.writeText(code);
          button.textContent = "Copied";
        } catch (error) {
          window.prompt("Copy this embed code", code);
        }
      });
    });
    els("[data-share-card]", root).forEach(function (button) {
      button.addEventListener("click", async function () {
        const url = button.getAttribute("data-share-url") || window.location.href;
        const title = button.getAttribute("data-share-title") || "Florida Signal";
        if (navigator.share) {
          try { await navigator.share({ title: title, url: url }); return; }
          catch (error) { if (error && error.name === "AbortError") return; }
        }
        try {
          await navigator.clipboard.writeText(url);
          button.textContent = "Copied";
        } catch (error) {
          window.prompt("Copy this graphic link", url);
        }
      });
    });
    /* Page-level freshness is rendered in loadPublicRecord; each Graphic Desk card carries its own source clock. */
  }

  function initDataFlipper() {
    const flipper = el(".data-flipper");
    if (!flipper) return;
    const panels = els("[data-flip-panel]", flipper);
    const indexLabel = el("[data-flip-index]", flipper);
    const progress = el(".data-flipper__progress span", flipper);
    let index = 0;
    let timer;
    function show(next, manual) {
      index = (next + panels.length) % panels.length;
      panels.forEach(function (panel, panelIndex) {
        const active = panelIndex === index;
        panel.hidden = !active;
        panel.classList.toggle("is-active", active);
      });
      if (indexLabel) indexLabel.textContent = (index + 1) + " / " + panels.length;
      if (progress) {
        progress.style.animation = "none";
        void progress.offsetWidth;
        progress.style.animation = "";
      }
      window.clearInterval(timer);
      timer = window.setInterval(function () { show(index + 1, false); }, 6000);
      if (manual) flipper.classList.add("was-manual");
    }
    const prev = el("[data-flip-prev]", flipper);
    const next = el("[data-flip-next]", flipper);
    if (prev) prev.addEventListener("click", function () { show(index - 1, true); });
    if (next) next.addEventListener("click", function () { show(index + 1, true); });
    flipper.addEventListener("mouseenter", function () { window.clearInterval(timer); flipper.classList.add("is-paused"); });
    flipper.addEventListener("mouseleave", function () { flipper.classList.remove("is-paused"); show(index, false); });
    flipper.addEventListener("focusin", function () { window.clearInterval(timer); flipper.classList.add("is-paused"); });
    flipper.addEventListener("focusout", function () { flipper.classList.remove("is-paused"); show(index, false); });
    show(0, false);
  }

  function initMobileLiveRail() {
    const viewport = el("[data-mobile-live-rail]");
    if (!viewport) return;
    const cards = els("[data-mobile-live-card]", viewport);
    if (cards.length < 2 || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let index = 0;
    let pauseUntil = 0;
    function advance() {
      if (window.innerWidth > 620 || document.hidden || Date.now() < pauseUntil) return;
      index = (index + 1) % cards.length;
      viewport.scrollTo({ left: Math.max(0, cards[index].offsetLeft - 14), behavior: "smooth" });
    }
    viewport.addEventListener("pointerdown", function () { pauseUntil = Date.now() + 15000; });
    viewport.addEventListener("focusin", function () { pauseUntil = Date.now() + 15000; });
    window.setInterval(advance, 4600);
  }

  function initMobileFieldTest() {
    const root = el("[data-mobile-field-test]");
    if (!root) return;
    const toggle = el("[data-mobile-field-toggle]", root);
    const panel = el("[data-mobile-field-panel]", root);
    const locate = el("[data-mobile-field-locate]", root);
    const form = el("[data-mobile-field-search]", root);
    const status = el("[data-mobile-field-status]", root);
    const results = el("[data-mobile-field-results]", root);
    const mapNode = el("#mobile-field-map", root);
    let fieldMap = null;
    let pointLayer = null;

    function validRecords() {
      return state.records.filter(function (record) { return Number.isFinite(Number(record.lat)) && Number.isFinite(Number(record.lon)); });
    }

    function ensureMap() {
      if (fieldMap || !window.L || !mapNode) return fieldMap;
      fieldMap = L.map(mapNode, { zoomControl: true, scrollWheelZoom: false, attributionControl: true, preferCanvas: true }).setView([26.129, -80.144], 12);
      L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", { maxZoom: 20, attribution: '&copy; OpenStreetMap &copy; CARTO' }).addTo(fieldMap);
      pointLayer = L.layerGroup().addTo(fieldMap);
      addMapBrand(fieldMap);
      return fieldMap;
    }

    function recordDistanceMiles(origin, record) {
      return haversineKm(origin.lat, origin.lon, Number(record.lat), Number(record.lon)) * 0.621371;
    }

    function resultMarkup(record, distance) {
      const tags = recordTaxonomy(record);
      return '<a class="mobile-field-result" href="' + recordUrl(record) + '">' +
        '<span>' + escapeHtml(recordPlace(record)) + (Number.isFinite(distance) ? ' · ' + distance.toFixed(1) + ' mi' : '') + '</span>' +
        '<strong>' + escapeHtml(recordHeadline(record)) + '</strong>' +
        '<small>' + escapeHtml(record.permit_number || "Public filing") + ' · applied ' + escapeHtml(formatDate(record.applied_date, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + '</small>' +
        taxonomyLine(tags, "Field lens") + '<b>Open exact filing →</b></a>';
    }

    function plotRecords(records, origin, label) {
      const map = ensureMap();
      if (!map || !pointLayer) {
        status.textContent = "The field map could not start on this browser.";
        return;
      }
      pointLayer.clearLayers();
      const bounds = [];
      if (origin) {
        const userPoint = [origin.lat, origin.lon];
        bounds.push(userPoint);
        L.circleMarker(userPoint, { radius: 9, color: "#071b32", weight: 3, fillColor: "#ffcf4a", fillOpacity: 1 }).addTo(pointLayer).bindPopup('<strong>' + escapeHtml(label || "Your field point") + '</strong><br>Location stays in this browser.');
        L.circle(userPoint, { radius: 804.672, color: "#1767ff", weight: 1, dashArray: "5 6", fillColor: "#1767ff", fillOpacity: .035 }).addTo(pointLayer);
      }
      records.forEach(function (record, index) {
        const point = [Number(record.lat), Number(record.lon)];
        bounds.push(point);
        L.circleMarker(point, { radius: index === 0 ? 8 : 6, color: "#fff", weight: 2, fillColor: index === 0 ? "#ff6d3a" : "#009f91", fillOpacity: .96 }).addTo(pointLayer).bindPopup(mapPopup(record));
      });
      if (bounds.length) map.fitBounds(bounds, { padding: [32, 32], maxZoom: 15 });
      window.setTimeout(function () { map.invalidateSize(); }, 80);
    }

    async function scanLocation(position) {
      const origin = { lat: position.coords.latitude, lon: position.coords.longitude };
      const records = validRecords();
      if (!records.length) {
        status.textContent = "The live mapped sample is still connecting. Try again in a moment.";
        return;
      }
      const ranked = records.map(function (record) { return { record: record, distance: recordDistanceMiles(origin, record) }; }).sort(function (a, b) { return a.distance - b.distance; }).slice(0, 5);
      const nearby = ranked.filter(function (item) { return item.distance <= 5; });
      const shown = nearby.length ? nearby : ranked.slice(0, 3);
      status.textContent = (nearby.length ? formatNumber(nearby.length) + " nearest mapped filings within five miles." : "No mapped filing is within five miles; showing the nearest current signals.") + " Application dates—not batch arrival dates.";
      results.innerHTML = shown.map(function (item) { return resultMarkup(item.record, item.distance); }).join("");
      plotRecords(shown.map(function (item) { return item.record; }), origin, "Your current location");
    }

    async function scanQuery(query) {
      const normalized = String(query || "").trim().toLowerCase();
      if (!normalized) return;
      if (!state.neighborhoods) {
        try { await loadNeighborhoods(); } catch (error) { /* Address and record matching still work. */ }
      }
      const matches = validRecords().filter(function (record) {
        const haystack = [record.address, record.permit_number, record.description, record.contractor_name, record.region, recordPlace(record)].join(" ").toLowerCase();
        return haystack.includes(normalized);
      }).slice(0, 8);
      if (!matches.length) {
        status.innerHTML = 'No point in the current mapped sample matches “' + escapeHtml(query) + '.” <a href="neighborhoods.html?q=' + encodeURIComponent(query) + '">Open the full record search →</a>';
        results.innerHTML = "";
        return;
      }
      status.textContent = formatNumber(matches.length) + " current mapped filing" + (matches.length === 1 ? "" : "s") + " match this field point. Application dates—not batch arrival dates.";
      results.innerHTML = matches.slice(0, 5).map(function (record) { return resultMarkup(record, NaN); }).join("");
      plotRecords(matches.slice(0, 5), null, query);
    }

    toggle.addEventListener("click", function () {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      panel.hidden = !open;
      root.classList.toggle("is-open", open);
      if (open) window.setTimeout(function () { const map = ensureMap(); if (map) map.invalidateSize(); }, 80);
    });
    locate.addEventListener("click", function () {
      if (!navigator.geolocation) {
        status.textContent = "This browser does not expose location. Enter an address, neighborhood, ZIP or permit instead.";
        return;
      }
      status.textContent = "Locating you and ranking the nearest mapped filings…";
      locate.classList.add("is-locating");
      navigator.geolocation.getCurrentPosition(function (position) {
        locate.classList.remove("is-locating");
        scanLocation(position);
      }, function () {
        locate.classList.remove("is-locating");
        status.textContent = "Location was not shared. Enter an address, neighborhood, ZIP or permit instead.";
      }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
    });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const input = el('input[name="field_query"]', form);
      if (input) scanQuery(input.value);
    });
  }

  function initSignupForms() {
    els("[data-signup-form]").forEach(function (form) {
      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        trackEvent("newsletter_submit", { placement: form.getAttribute("data-signup-source") || (form.classList.contains("signup--hero") ? "homepage-hero" : "homepage-brief") });
        const input = el('input[name="email"]', form);
        const zip = el('input[name="zip"]', form);
        const message = el("[data-signup-message]", form);
        if (!input || !zip || !message) return;
        message.classList.remove("is-error");
        message.textContent = "Saving your place…";
        try {
          const response = await fetch("/api/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: input.value, zip: zip.value, source: form.getAttribute("data-signup-source") || (form.classList.contains("signup--hero") ? "homepage-hero" : "homepage-brief") })
          });
          const data = await response.json();
          if (!response.ok) throw new Error(data.error || "Could not save subscription");
          message.textContent = data.existing ? "You’re already on the list." : "You’re in. Watch for the 6:15 Brief.";
          trackEvent("newsletter_conversion", { placement: form.getAttribute("data-signup-source") || "website", status: data.existing ? "existing" : "created" });
          try { window.localStorage.setItem("florida-signal-brief-subscribed", String(Date.now())); } catch (storageError) { /* Storage is optional. */ }
          input.value = "";
          zip.value = "";
          const prompt = form.closest(".brief-prompt");
          if (prompt) window.setTimeout(function () { const close = el("[data-brief-prompt-close]", prompt); if (close) close.click(); }, 900);
        } catch (error) {
          message.classList.add("is-error");
          message.textContent = "Signup is not connected on this host yet. Email desk@thefloridasignal.com.";
        }
      });
    });
  }

  function initBriefPrompt() {
    const forcePreview = new URLSearchParams(window.location.search).get("brief-preview") === "1";
    let subscribed = false;
    let recentlyDismissed = false;
    let shownThisSession = false;
    try {
      subscribed = Boolean(window.localStorage.getItem("florida-signal-brief-subscribed"));
      const dismissedAt = Number(window.localStorage.getItem("florida-signal-brief-dismissed") || 0);
      recentlyDismissed = dismissedAt > Date.now() - 7 * 24 * 60 * 60 * 1000;
      shownThisSession = window.sessionStorage.getItem("florida-signal-brief-prompt-shown") === "yes";
    } catch (error) { /* Storage is optional. */ }
    if (!forcePreview && (subscribed || recentlyDismissed || shownThisSession)) return;
    const prompt = document.createElement("div");
    prompt.className = "brief-prompt";
    prompt.hidden = true;
    prompt.innerHTML = '<div class="brief-prompt__backdrop" data-brief-prompt-close></div><section class="brief-prompt__dialog" role="dialog" aria-modal="true" aria-labelledby="brief-prompt-title" aria-describedby="brief-prompt-dek"><button class="brief-prompt__close" type="button" data-brief-prompt-close aria-label="Close Daily Intel Brief signup">×</button><div class="brief-prompt__mark" aria-hidden="true"><img src="assets/mark-full-color.png" alt=""></div><p class="eyebrow"><span class="pulse" aria-hidden="true"></span>Tomorrow starts tonight</p><h2 id="brief-prompt-title">Get the 6:15 Daily Intel Brief.</h2><p id="brief-prompt-dek">One sharp Broward email: consequential filings, neighborhood movement, meetings, storm readiness and the records behind every claim.</p><form class="signup signup--prompt" data-signup-form data-signup-source="ten-second-prompt"><label class="sr-only" for="prompt-email">Email address</label><input id="prompt-email" name="email" type="email" autocomplete="email" placeholder="Your email address" required><label class="sr-only" for="prompt-zip">ZIP you watch</label><input id="prompt-zip" name="zip" inputmode="numeric" autocomplete="postal-code" pattern="[0-9]{5}(-[0-9]{4})?" placeholder="ZIP you watch" required><button type="submit">Send me the brief →</button><p class="signup__message" data-signup-message aria-live="polite"></p></form><p class="brief-prompt__fine">Free · Broward Audience · unsubscribe anytime · powered by Graham &amp; Gold LLC</p></section>';
    document.body.appendChild(prompt);
    const closeButtons = els("[data-brief-prompt-close]", prompt);
    let previousFocus = null;
    function closePrompt(recordDismissal) {
      prompt.classList.remove("is-open");
      document.body.classList.remove("brief-prompt-open");
      if (recordDismissal) {
        try { window.localStorage.setItem("florida-signal-brief-dismissed", String(Date.now())); } catch (error) { /* Storage is optional. */ }
      }
      window.setTimeout(function () { prompt.hidden = true; if (previousFocus && previousFocus.focus) previousFocus.focus(); }, 220);
    }
    closeButtons.forEach(function (button) { button.addEventListener("click", function () { closePrompt(true); }); });
    prompt.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { event.preventDefault(); closePrompt(true); return; }
      if (event.key !== "Tab") return;
      const focusable = els('button, input, a[href]', prompt).filter(function (node) { return !node.hidden && node.getAttribute("disabled") === null; });
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    const promptDelay = forcePreview ? 300 : 10000;
    window.setTimeout(function () {
      if (document.hidden || prompt.classList.contains("is-open")) return;
      previousFocus = document.activeElement;
      prompt.hidden = false;
      document.body.classList.add("brief-prompt-open");
      window.requestAnimationFrame(function () { prompt.classList.add("is-open"); const close = el(".brief-prompt__close", prompt); if (close) close.focus(); });
      trackEvent("brief_prompt_view", { placement: "ten-second-prompt" });
      try { window.sessionStorage.setItem("florida-signal-brief-prompt-shown", "yes"); } catch (error) { /* Storage is optional. */ }
    }, promptDelay);
  }

  function initSponsorInventory() {
    const footer = el(".site-footer");
    if (!footer || el(".site-sponsor-rail")) return;
    const pageName = titleCase(document.body.getAttribute("data-page") || "Florida Signal");
    const rail = document.createElement("aside");
    rail.className = "site-sponsor-rail";
    rail.setAttribute("aria-label", "Florida Signal sponsorship availability");
    rail.innerHTML = '<div class="shell"><span>Available inventory · ' + escapeHtml(pageName) + '</span><strong>Own this intelligence surface</strong><a href="mailto:desk@thefloridasignal.com?subject=' + encodeURIComponent("Florida Signal " + pageName + " sponsorship") + '">Your logo here · sponsorship desk ↗</a></div>';
    footer.parentNode.insertBefore(rail, footer);
  }

  async function initDataHealth() {
    const page = document.body.getAttribute("data-page") || "home";
    if (!["home", "neighborhoods", "broward", "graphics", "storm", "method"].includes(page) || el("#source-health")) return;
    const details = document.createElement("details");
    details.className = "source-health";
    details.id = "source-health";
    if (page === "method") details.open = true;
    details.innerHTML = '<summary><span><i aria-hidden="true"></i>Source clocks</span><strong>Checking each feed…</strong><small>Event dates ≠ pull times</small></summary><div class="shell source-health__grid"><p>Reading separate source, sync and event clocks…</p></div>';
    const operations = el("#storm-operations");
    const header = el(".site-header");
    if (operations) operations.insertAdjacentElement("afterend", details);
    else if (header) header.insertAdjacentElement("afterend", details);
    details.addEventListener("toggle", function () { if (details.open) trackEvent("source_health_open", { placement: page }); });
    try {
      const response = await fetch("/api/data-health", { cache: "no-store", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Data health unavailable");
      const payload = await response.json();
      const sources = Array.isArray(payload.sources) ? payload.sources : [];
      const counts = sources.reduce(function (result, source) { result[source.status] = (result[source.status] || 0) + 1; return result; }, {});
      const summary = el("summary strong", details);
      if (summary) summary.textContent = [counts.current ? counts.current + " current" : "", counts.delayed ? counts.delayed + " delayed" : "", counts.stale ? counts.stale + " stale" : "", counts.unverified ? counts.unverified + " unverified" : ""].filter(Boolean).join(" · ") || "Source clocks unavailable";
      const grid = el(".source-health__grid", details);
      grid.innerHTML = sources.map(function (source) {
        const eventClock = source.event_through ? "Event through " + formatDate(source.event_through, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) : "Event date varies by item";
        const systemClock = source.system_time ? "System " + formatDate(source.system_time, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET" : "System timestamp not exposed";
        return '<article><div><span class="source-health__status source-health__status--' + escapeHtml(source.status) + '">' + escapeHtml(source.status) + '</span><strong>' + escapeHtml(source.label) + '</strong></div><p>' + escapeHtml(eventClock) + '</p><p>' + escapeHtml(systemClock) + '</p><small>' + escapeHtml(source.cadence || "") + ' · ' + escapeHtml(source.detail || "") + '</small></article>';
      }).join("") || '<p>Source health is unavailable. The site will not substitute an inferred green status.</p>';
    } catch (error) {
      const summary = el("summary strong", details);
      if (summary) summary.textContent = "Health manifest unavailable";
      const grid = el(".source-health__grid", details);
      grid.innerHTML = '<p>Separate source clocks could not be loaded. No green status is being inferred.</p>';
    }
  }

  function analyticsSessionId() {
    try {
      let sessionId = window.sessionStorage.getItem("florida-signal-analytics-session");
      if (!sessionId) {
        sessionId = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : "fs-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
        window.sessionStorage.setItem("florida-signal-analytics-session", sessionId);
      }
      return sessionId;
    } catch (error) { return ""; }
  }

  function trackEvent(name, properties) {
    const payload = JSON.stringify({
      event: name,
      page: window.location.pathname,
      session_id: analyticsSessionId(),
      properties: Object.assign({ device: window.matchMedia("(max-width: 620px)").matches ? "mobile" : "desktop" }, properties || {})
    });
    if (window.dataLayer && Array.isArray(window.dataLayer)) window.dataLayer.push(Object.assign({ event: name }, properties || {}));
    try {
      if (navigator.sendBeacon) {
        const accepted = navigator.sendBeacon("/api/events", new Blob([payload], { type: "application/json" }));
        if (accepted) return;
      }
      fetch("/api/events", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, keepalive: true }).catch(function () { /* Static hosts may not expose first-party analytics. */ });
    } catch (error) { /* Analytics must never block the product. */ }
  }

  function initAnalytics() {
    trackEvent("page_view", { page_name: document.body.getAttribute("data-page") || "unknown" });
    document.addEventListener("click", function (event) {
      const target = event.target && event.target.closest ? event.target.closest("a,button") : null;
      if (!target) return;
      if (target.matches(".sponsor-slot,.site-sponsor-rail a,.graphic-card__sponsor")) trackEvent("sponsor_interest", { placement: target.closest(".graphic-card") ? "graphic-card" : target.closest(".site-sponsor-rail") ? "site-rail" : "module" });
      else if (target.matches("[data-share-record]")) trackEvent("record_share", { share_type: "native" });
      else if (target.matches("[data-copy-record]")) trackEvent("record_share", { share_type: "copy-link" });
      else if (target.matches("[data-share-card]")) trackEvent("graphic_share", { share_type: "native" });
      else if (target.matches("[data-copy-embed]")) trackEvent("graphic_embed", { action: "copy" });
      else if (target.matches("[data-mobile-field-toggle]")) trackEvent("mobile_field_open", { mode: "panel" });
      else if (target.matches("[data-mobile-field-locate]")) trackEvent("mobile_field_scan", { mode: "browser-location" });
      else if (target.matches(".lead-card__map-cta,.spyglass__open")) trackEvent("map_open", { placement: target.matches(".spyglass__open") ? "spotlight" : "lead-card" });
    });
    document.addEventListener("submit", function (event) {
      if (event.target && event.target.matches && event.target.matches("[data-mobile-field-search]")) trackEvent("mobile_field_scan", { mode: "typed-place" });
      if (event.target && event.target.matches && event.target.matches("#record-search")) trackEvent("record_search", { mode: "typed-query" });
    });
    window.floridaSignalTrack = trackEvent;
  }

  function initNavigation() {
    const button = el(".menu-button");
    if (!button) return;
    const navigation = el(".site-nav");
    if (navigation && !el('a[href="stories.html"]', navigation)) {
      const storiesLink = document.createElement("a");
      storiesLink.href = "stories.html";
      storiesLink.textContent = "Stories";
      if (document.body.getAttribute("data-page") === "stories") storiesLink.setAttribute("aria-current", "page");
      const neighborhoodsLink = el('a[href="neighborhoods.html"]', navigation);
      navigation.insertBefore(storiesLink, neighborhoodsLink || navigation.firstChild);
    }
    if (navigation && !el('a[href="graphics.html"]', navigation)) {
      const graphicsLink = document.createElement("a");
      graphicsLink.href = "graphics.html";
      graphicsLink.textContent = "Graphic desk";
      if (document.body.getAttribute("data-page") === "graphics") graphicsLink.setAttribute("aria-current", "page");
      const stormLink = el('a[href="storm.html"]', navigation);
      navigation.insertBefore(graphicsLink, stormLink || null);
    }
    if (navigation && !el('a[href="meetings.html"]', navigation)) {
      const meetingsLink = document.createElement("a");
      meetingsLink.href = "meetings.html";
      meetingsLink.textContent = "Meetings";
      if (document.body.getAttribute("data-page") === "meetings") meetingsLink.setAttribute("aria-current", "page");
      const methodLink = el('a[href="method.html"]', navigation);
      navigation.insertBefore(meetingsLink, methodLink || null);
    }
    button.addEventListener("click", function () {
      const open = !document.body.classList.contains("nav-open");
      document.body.classList.toggle("nav-open", open);
      button.setAttribute("aria-expanded", String(open));
      const label = el(".sr-only", button);
      if (label) label.textContent = open ? "Close navigation" : "Open navigation";
    });
    els(".site-nav a").forEach(function (link) { link.addEventListener("click", function () { document.body.classList.remove("nav-open"); button.setAttribute("aria-expanded", "false"); const label = el(".sr-only", button); if (label) label.textContent = "Open navigation"; }); });
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape" || !document.body.classList.contains("nav-open")) return;
      document.body.classList.remove("nav-open");
      button.setAttribute("aria-expanded", "false");
      const label = el(".sr-only", button);
      if (label) label.textContent = "Open navigation";
      button.focus();
    });
  }

  function stormTrackImage(storm) {
    const id = String((storm || {}).id || "").toUpperCase();
    if (!/^[A-Z]{2}\d{6}$/.test(id)) return "";
    return "https://www.nhc.noaa.gov/storm_graphics/" + id.slice(0, 4) + "/refresh/" + id + "_5day_cone+png/";
  }

  function startStormTicker(storm) {
    if (stormTickerTimer) window.clearInterval(stormTickerTimer);
    const story = el("#live-bar-story");
    const time = el("#live-bar-time");
    if (!story || !time || !document.body.classList.contains("storm-mode")) return;
    const items = storm ? [
      storm.name + " · " + storm.classification + " · " + storm.intensity + " KT",
      "CENTER " + storm.latitude + " · " + storm.longitude,
      "MOVEMENT " + storm.movementDir + "° AT " + storm.movementSpeed + " KT",
      "PRESSURE " + storm.pressure + " MB",
      "OFFICIAL NHC UPDATE " + formatDate(storm.lastUpdate, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET"
    ] : [
      "ATLANTIC BASIN MONITORED BY THE NATIONAL HURRICANE CENTER",
      "NO NAMED ATLANTIC SYSTEM ACTIVE",
      "GOES-EAST SOUTHEAST SATELLITE · OFFICIAL NOAA SOURCE"
    ];
    let index = 0;
    function flip() { story.textContent = items[index % items.length]; time.textContent = "EDITOR-CONTROLLED STORM WATCH"; index += 1; }
    flip();
    stormTickerTimer = window.setInterval(flip, 4200);
  }

  function renderStormOperations(payload) {
    const root = el("#storm-operations");
    if (!root) return;
    const active = document.body.classList.contains("storm-mode");
    root.hidden = !active;
    if (!active) return;
    const storms = ((payload || state.stormPayload || {}).activeStorms || []).filter(function (storm) { return String(storm.id || "").toLowerCase().startsWith("al"); });
    const storm = storms[0] || null;
    const trackImage = stormTrackImage(storm);
    const trackPage = storm && storm.forecastGraphics && storm.forecastGraphics.url ? storm.forecastGraphics.url : "https://www.nhc.noaa.gov/";
    const advisory = storm && storm.publicAdvisory && storm.publicAdvisory.url ? storm.publicAdvisory.url : "https://www.nhc.noaa.gov/";
    const title = storm ? storm.name + " · " + storm.classification + " · " + storm.intensity + " kt" : "Atlantic basin · official-source standby";
    const coordinates = storm ? storm.latitude + " · " + storm.longitude : "No named Atlantic center fix";
    const movement = storm ? "Moving " + storm.movementDir + "° at " + storm.movementSpeed + " kt · " + storm.pressure + " mb" : "Publisher Storm Watch is active; NHC has no named Atlantic system in its current feed.";
    const update = storm && storm.lastUpdate ? "NHC updated " + formatDate(storm.lastUpdate, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET" : "Official sources remain the authority";
    root.innerHTML = '<div class="shell storm-operations__head"><p><span aria-hidden="true">🌀</span><strong>Florida Signal Storm Watch</strong></p><p>' + escapeHtml(update) + '</p></div><div class="shell storm-operations__grid">' +
      '<a class="storm-operations__visual" href="' + escapeHtml(trackPage) + '" target="_blank" rel="noopener"><img src="' + escapeHtml(trackImage || "https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png") + '" alt="' + escapeHtml(storm ? "Official National Hurricane Center forecast cone for " + storm.name : "Official National Hurricane Center seven-day Atlantic outlook") + '"><span>Official NHC ' + (storm ? "forecast track" : "Atlantic outlook") + ' ↗</span></a>' +
      '<a class="storm-operations__visual" href="https://www.star.nesdis.noaa.gov/goes/sector.php?sat=G19&amp;sector=se" target="_blank" rel="noopener"><img src="https://cdn.star.nesdis.noaa.gov/GOES19/ABI/SECTOR/se/GEOCOLOR/600x600.jpg" alt="Current NOAA GOES-East GeoColor satellite view of the Southeast United States"><span>NOAA GOES-East Southeast satellite ↗</span></a>' +
      '<div class="storm-operations__readout"><p>Official center fix</p><h2>' + escapeHtml(title) + '</h2><strong>' + escapeHtml(coordinates) + '</strong><span>' + escapeHtml(movement) + '</span><div><a href="' + escapeHtml(advisory) + '" target="_blank" rel="noopener">Public advisory ↗</a><a href="storm.html">Open Storm Window →</a></div><small>Florida Signal adds local readiness records. It does not replace NHC, NWS or emergency management.</small></div></div>';
    startStormTicker(storm);
  }

  function applyStormMode(active, mode) {
    const status = el("#storm-mode-status");
    const liveLabel = el(".live-bar__inner p:first-child strong");
    document.body.classList.toggle("storm-mode", active);
    if (liveLabel) {
      if (!liveLabel.dataset.defaultLabel) liveLabel.dataset.defaultLabel = liveLabel.textContent;
      liveLabel.textContent = active ? "Storm Watch active" : liveLabel.dataset.defaultLabel;
    }
    if (status) {
      status.classList.toggle("is-active", active);
      status.setAttribute("aria-label", "Publisher-controlled Florida Signal Storm Watch is " + (active ? "active" : "on standby"));
      status.innerHTML = '<span class="storm-mode-toggle__icon" aria-hidden="true">🌀</span><span>Storm watch ' + (active ? "active" : "standby") + '</span>';
      status.title = "Publisher-controlled site state" + (mode && mode.updated_at ? " · updated " + mode.updated_at : "");
    }
    const themeColor = el('meta[name="theme-color"]');
    if (themeColor) themeColor.setAttribute("content", active ? "#8f1118" : "#ffffff");
    if (active && document.body.dataset.stormAnalyticsSent !== "yes") {
      document.body.dataset.stormAnalyticsSent = "yes";
      trackEvent("storm_watch_view", { mode: "publisher-controlled" });
    }
    renderStormOperations(state.stormPayload);
  }

  function initStormMode() {
    const bar = el(".live-bar__inner");
    if (!bar) return;
    const status = document.createElement("span");
    status.className = "storm-mode-toggle";
    status.id = "storm-mode-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    bar.appendChild(status);
    const operations = document.createElement("section");
    operations.className = "storm-operations";
    operations.id = "storm-operations";
    operations.hidden = true;
    operations.setAttribute("aria-label", "Florida Signal Storm Watch official track, satellite and center coordinates");
    const header = el(".site-header");
    if (header) header.insertAdjacentElement("afterend", operations);
    applyStormMode(false, state.siteMode);
    (async function () {
      let mode = null;
      try {
        let response = await fetch("/api/site-mode", { cache: "no-store" });
        if (!response.ok) response = await fetch("data/site_mode.json", { cache: "no-store" });
        if (response.ok) mode = await response.json();
      } catch (error) { mode = null; }
      state.siteMode = mode || { storm_watch: "off" };
      const preview = new URLSearchParams(window.location.search).get("storm-preview");
      const active = preview === "on" ? true : preview === "off" ? false : String(state.siteMode.storm_watch || "off").toLowerCase() === "on";
      applyStormMode(active, state.siteMode);
    })();
  }

  function initMethodologyToggle() {
    const toggle = el("[data-method-toggle]");
    const panel = el("[data-method-panel]");
    if (!toggle || !panel) return;
    toggle.addEventListener("click", function () {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      panel.hidden = !open;
      toggle.innerHTML = (open ? "Close methodology " : "Flip to methodology ") + '<span aria-hidden="true">↻</span>';
    });
  }

  function init() {
    els("[data-year]").forEach(function (node) { node.textContent = String(new Date().getFullYear()); });
    initAnalytics();
    initStormMode();
    initDataHealth();
    initMethodologyToggle();
    initNavigation();
    initBriefPrompt();
    initSignupForms();
    initSponsorInventory();
    initDataFlipper();
    initMobileLiveRail();
    initMobileFieldTest();
    initLensSwitch();
    initMapOverlayTools();
    initRecordSearch();
    initLeadDesk();
    loadStorms();
    loadMeetings();
    loadAgendaRecon();
    loadCmsContent();
    loadPublicRecord().catch(function () {
      const ticker = el("#live-bar-story");
      if (ticker) ticker.textContent = "The public feed is temporarily unavailable; no fallback data is being substituted.";
      renderSignals();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
