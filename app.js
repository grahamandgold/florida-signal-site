(function () {
  "use strict";

  const SUPABASE_URL = "https://jrjewmzkyluxdywyusrw.supabase.co";
  // Supabase publishable keys are designed for public clients. RLS remains the access boundary.
  const SUPABASE_KEY = "sb_publishable_dEyBjKE_vcTj3YYx4p6XvA_xnkVW3Wb";
  const API_BASE = /(^|\.)thefloridasignal\.com$/i.test(window.location.hostname)
    ? "https://api.thefloridasignal.com"
    : "";
  function apiUrl(path) { return API_BASE + path; }
  const NEIGHBORHOODS_URL = "https://gis.fortlauderdale.gov/arcgis/rest/services/GeneralPurpose/gisdata/MapServer/61/query?where=1%3D1&outFields=OFFICIALNAME&returnGeometry=true&f=geojson&outSR=4326";
  const CENSUS_ENVELOPE = "-80.36,25.91,-80.04,26.36";
  const CENSUS_LAYERS = {
    zip: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query", where: "1=1", fields: "ZCTA5,NAME", color: "#7654b5", label: "ZIP" },
    congress: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/0/query", where: "STATE='12'", fields: "NAME,BASENAME,CD119", color: "#1767ff", label: "U.S. House" },
    senate: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/1/query", where: "STATE='12'", fields: "NAME,BASENAME,SLDU", color: "#ff6d3a", label: "FL Senate" },
    house: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/2/query", where: "STATE='12'", fields: "NAME,BASENAME,SLDL", color: "#009f91", label: "FL House" },
    corridor: { url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4/query", where: "STATE='12' AND NAME IN ('Hollywood city','Pompano Beach city','Oakland Park city','Wilton Manors city','Plantation city','Cooper City city','Southwest Ranches town')", fields: "NAME,BASENAME,PLACE,STATE", color: "#a81920", label: "Broward corridor" }
  };
  const ACTIVE_CITY = "fort-lauderdale";
  const CITY_ROOT = "/fort-lauderdale";
  const OFFICIAL_PERMIT_PORTAL = "https://aca3.accela.com/FTL";
  const FIELD_BRIEF_STORAGE_KEY = "florida-signal-field-brief-v1";
  const PUBLIC_ROUTES = {
    home: CITY_ROOT + "/",
    briefs: CITY_ROOT + "/briefs/",
    neighborhoods: CITY_ROOT + "/neighborhoods/",
    broward: CITY_ROOT + "/broward-record/",
    graphics: CITY_ROOT + "/graphics/",
    storm: CITY_ROOT + "/storm/",
    meetings: CITY_ROOT + "/meetings/",
    method: CITY_ROOT + "/method/",
    brand: CITY_ROOT + "/brand/"
  };
  const BROWARD_CITIES = [
    ["coconut-creek", "Coconut Creek"], ["cooper-city", "Cooper City"], ["coral-springs", "Coral Springs"],
    ["dania-beach", "Dania Beach"], ["davie", "Davie"], ["deerfield-beach", "Deerfield Beach"],
    ["fort-lauderdale", "Fort Lauderdale"], ["hallandale-beach", "Hallandale Beach"], ["hillsboro-beach", "Hillsboro Beach"],
    ["hollywood", "Hollywood"], ["lauderdale-by-the-sea", "Lauderdale-by-the-Sea"], ["lauderdale-lakes", "Lauderdale Lakes"],
    ["lauderhill", "Lauderhill"], ["lazy-lake", "Lazy Lake"], ["lighthouse-point", "Lighthouse Point"],
    ["margate", "Margate"], ["miramar", "Miramar"], ["north-lauderdale", "North Lauderdale"],
    ["oakland-park", "Oakland Park"], ["parkland", "Parkland"], ["pembroke-park", "Pembroke Park"],
    ["pembroke-pines", "Pembroke Pines"], ["plantation", "Plantation"], ["pompano-beach", "Pompano Beach"],
    ["sea-ranch-lakes", "Sea Ranch Lakes"], ["southwest-ranches", "Southwest Ranches"], ["sunrise", "Sunrise"],
    ["tamarac", "Tamarac"], ["west-park", "West Park"], ["weston", "Weston"], ["wilton-manors", "Wilton Manors"]
  ];
  const BRIEF_INTERESTS = [
    ["development", "Development + permits"], ["neighborhoods", "Neighborhood intelligence"],
    ["meetings", "Meetings + agendas"], ["property", "Property + ownership"],
    ["liens", "Liens + courthouse"], ["storm", "Storm readiness"]
  ];
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
  function setCountStat(name, value, options) {
    const settings = options || {};
    const prefix = settings.estimated && Number.isFinite(Number(value)) ? "≈" : "";
    els('[data-stat="' + name + '"]').forEach(function (node) {
      node.textContent = prefix + formatNumber(value);
      node.dataset.countQuality = settings.estimated ? "estimated" : "exact";
      if (settings.estimated) {
        node.title = "Approximate database planner count; verify against the source snapshot before citation.";
        node.setAttribute("aria-label", "Approximately " + formatNumber(value));
      } else {
        node.removeAttribute("title");
        node.setAttribute("aria-label", formatNumber(value) + (settings.asOf ? " as of " + settings.asOf : ""));
      }
    });
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
  function recordUrl(record) { return PUBLIC_ROUTES.neighborhoods + "?permit=" + encodeURIComponent(record.permit_number || ""); }

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
    const tags = ["market:broward", "county:broward-county", "city:fort-lauderdale", "source:city-permit", "geography:" + tagSlug(recordPlace(record)), "audience:field-desk"];
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

  function initTaxonomyDefaults() {
    const page = tagSlug(document.body.getAttribute("data-page") || "home");
    const base = ["market:broward", "county:broward-county", "city:fort-lauderdale"];
    const selectors = "main > section, main article, [data-flip-panel], [data-signal-tags], .visual-recon-strip > a, .sponsor-slot, .site-sponsor-rail";
    function decorate(node) {
      if (!(node instanceof Element) || !node.matches(selectors)) return;
      const existing = String(node.getAttribute("data-signal-tags") || "").split(/\s+/).filter(Boolean);
      const tags = existing.slice();
      base.forEach(function (baseTag) {
        const namespace = baseTag.split(":")[0] + ":";
        if (!existing.some(function (tag) { return tag.indexOf(namespace) === 0; })) tags.push(baseTag);
      });
      if (!existing.some(function (tag) { return tag.indexOf("topic:") === 0; })) tags.push("topic:" + page);
      if (!existing.some(function (tag) { return tag.indexOf("format:") === 0; })) {
        if (node.matches("[data-flip-panel]")) tags.push("format:live-panel");
        else if (node.matches(".visual-recon-strip > a")) tags.push("format:visual-promo");
        else if (node.matches(".sponsor-slot,.site-sponsor-rail")) tags.push("format:sponsorship");
        else tags.push(node.tagName === "ARTICLE" ? "format:card" : "format:section");
      }
      node.setAttribute("data-signal-tags", uniqueTags(tags).join(" "));
    }
    function scan(root) {
      if (root instanceof Element) decorate(root);
      els(selectors, root instanceof Element ? root : document).forEach(decorate);
    }
    scan(document);
    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) { Array.from(mutation.addedNodes).forEach(scan); });
    });
    observer.observe(document.body, { childList: true, subtree: true });
    [
      ["florida-signal:market", "broward"],
      ["florida-signal:county", "broward-county"],
      ["florida-signal:city", "fort-lauderdale"]
    ].forEach(function (entry) {
      let meta = el('meta[name="' + entry[0] + '"]');
      if (!meta) { meta = document.createElement("meta"); meta.name = entry[0]; document.head.appendChild(meta); }
      meta.content = entry[1];
    });
  }

  function placeSignature(record) {
    return '<span class="place-signature"><i aria-hidden="true"></i>' + escapeHtml(recordPlace(record)) + '</span>';
  }

  function shareRecordUrl(record) {
    return new URL(recordUrl(record), window.location.href).href;
  }

  function recordInvestigationUrls(record) {
    const hasPoint = Number.isFinite(Number(record.lat)) && Number.isFinite(Number(record.lon));
    const point = hasPoint ? Number(record.lat) + "," + Number(record.lon) : encodeURIComponent(String(record.address || "Fort Lauderdale, FL"));
    return {
      street: hasPoint ? "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=" + point : "https://www.google.com/maps/search/?api=1&query=" + point,
      satellite: hasPoint ? "https://www.google.com/maps/@?api=1&map_action=map&center=" + point + "&zoom=19&basemap=satellite" : "https://www.google.com/maps/search/?api=1&query=" + point,
      official: OFFICIAL_PERMIT_PORTAL,
      floridaSignal: shareRecordUrl(record)
    };
  }

  function recordShareMarkup(record) {
    const url = shareRecordUrl(record);
    const title = "Florida Signal · " + recordPlace(record) + " · " + titleCase(String(record.address || record.permit_number || "development record").replace(/\s+/g, " "));
    const message = title + " — " + (record.permit_number || "public filing") + " " + url;
    const investigate = recordInvestigationUrls(record);
    return '<div class="record-share" aria-label="Share this Florida Signal record">' +
      '<a class="record-action record-action--street" data-action-label="Street View" href="' + escapeHtml(investigate.street) + '" target="_blank" rel="noreferrer" aria-label="Open nearby Street View">Street view</a>' +
      '<a class="record-action record-action--satellite" data-action-label="Satellite" href="' + escapeHtml(investigate.satellite) + '" target="_blank" rel="noreferrer" aria-label="Open satellite map">Satellite</a>' +
      '<a class="record-action record-action--text" data-action-label="Text" href="sms:?&body=' + encodeURIComponent(message) + '" aria-label="Text this record">Text</a>' +
      '<button class="record-action record-action--share" data-action-label="Share" type="button" data-share-record data-share-url="' + escapeHtml(url) + '" data-share-title="' + escapeHtml(title) + '">Share</button>' +
      '<button class="record-action record-action--brief" data-action-label="Add to report" type="button" data-report-add data-report-id="permit:' + escapeHtml(record.permit_number || url) + '" data-report-title="' + escapeHtml(title) + '" data-report-meta="' + escapeHtml((record.permit_number || "Public filing") + " · applied " + formatDate(record.applied_date, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + '" data-report-url="' + escapeHtml(url) + '" data-report-tags="' + taxonomyAttribute(recordTaxonomy(record)) + '">Add to report</button></div>';
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
    const exactPermits = Number(stats.permits_total);
    const permitsAreExact = Number.isFinite(exactPermits);
    const permits = permitsAreExact ? exactPermits : (results[1].status === "fulfilled" ? results[1].value : null);
    // The query planner's filtered estimate is intentionally not used here; the
    // dashboard cache carries the last exact geocoded-row count and timestamp.
    const mapped = stats.p_geo || (results[2].status === "fulfilled" ? results[2].value : null);
    const sunbiz = results[3].status === "fulfilled" ? results[3].value : null;
    setCountStat("permits", permits, { estimated: !permitsAreExact, asOf: state.dashboard && state.dashboard.updated_at });
    setCountStat("mapped", mapped, { estimated: !Number.isFinite(Number(stats.p_geo)), asOf: state.dashboard && state.dashboard.updated_at });
    setCountStat("sunbiz", sunbiz, { estimated: true });
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

    const railLine = el("#rail-signal-line");
    if (railLine && state.featured.length) {
      const railMoney = function (v) {
        const n = Number(v);
        if (!Number.isFinite(n) || n <= 0) return null;
        return n >= 1000000 ? "$" + (n / 1000000).toFixed(1).replace(/\.0$/, "") + "M" : "$" + Math.round(n / 1000) + "K";
      };
      const railItems = state.featured.slice(0, 8).map(function (r) {
        const money = railMoney(r.valuation_usd_clean);
        const place = r.address || r.permit_number || "Fort Lauderdale";
        const kind = r.work_type || r.permit_type || "application";
        return (money ? money + " " : "") + String(kind).toLowerCase() + " filed · " + place;
      }).filter(Boolean);
      if (railItems.length) {
        let railIndex = 0;
        railLine.textContent = railItems[0];
        window.setInterval(function () {
          railIndex = (railIndex + 1) % railItems.length;
          railLine.textContent = railItems[railIndex];
        }, 6200);
      }
    }

    if (state.records.length && (el("#signal-list") || el("#lead-list") || el("#graphic-desk"))) await Promise.allSettled([loadNeighborhoods()]);
    if (el("#graphic-desk")) await Promise.allSettled([loadZipBoundaries()]);
    renderSignals();
    renderInfographics();
    renderStormRecords();
    renderGraphicDesk();
    renderLiveWindows();
    renderDiagramPromo();
    renderStormPromo();
    await initMaps();
    renderLeadDesk();
    initRecordSpotlights();
    const initialQuery = new URLSearchParams(window.location.search).get("q");
    if (initialQuery && el("#record-search")) await runRecordSearch(initialQuery);
  }

  async function loadCmsContent() {
    const status = el("#cms-status");
    try {
      const response = await fetch(apiUrl("/api/cms"), { headers: { Accept: "application/json" } });
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
    return PUBLIC_ROUTES.briefs + "?story=" + encodeURIComponent(story.id || story.slug || "");
  }

  function renderStoriesPage(loadError) {
    const grid = el("#stories-grid");
    const reader = el("#story-reader");
    const status = el("#stories-status");
    if (!grid || !reader) return;
    const stories = state.cms && Array.isArray(state.cms.stories) ? state.cms.stories : [];
    if (loadError) {
      if (status) status.textContent = "The approved public wire is temporarily unavailable. No older draft is being substituted.";
      grid.innerHTML = '<div class="stories-empty"><p class="eyebrow">Source gate closed</p><h2>No brief is being inferred.</h2><p>The permit, meeting and map surfaces remain available while the editorial wire reconnects.</p><a class="button" href="' + PUBLIC_ROUTES.neighborhoods + '">Open live field map →</a></div>';
      return;
    }
    if (!state.cms.configured) {
      if (status) status.textContent = "The Fort Lauderdale Briefs desk is ready; The Data Wire connection has not been configured on this server.";
      grid.innerHTML = '<div class="stories-empty"><p class="eyebrow">Desk ready · no synthetic seed</p><h2>The first brief will arrive through the source gate.</h2><p>This page starts honestly empty. Drafts, agent notes and uncited summaries remain private until a human editor approves a source-linked WirePacket.</p><a class="button" href="' + PUBLIC_ROUTES.method + '">Read the publishing standard →</a></div>';
      return;
    }
    if (status) status.textContent = stories.length ? formatNumber(stories.length) + " approved brief" + (stories.length === 1 ? "" : "s") + " on the public wire · city: Fort Lauderdale" : "The Data Wire is connected. No Fort Lauderdale brief has passed every publishing gate yet.";
    const selectedId = new URLSearchParams(window.location.search).get("story");
    const selected = selectedId ? stories.find(function (story) { return String(story.id) === selectedId || String(story.slug) === selectedId; }) : null;
    if (selected) {
      const tags = Array.isArray(selected.tags) ? selected.tags : [];
      const body = String(selected.body || selected.summary || "").split(/\n\s*\n/).filter(Boolean).map(function (paragraph) { return "<p>" + escapeHtml(paragraph) + "</p>"; }).join("");
      const sourceLinks = Array.isArray(selected.source_links) && selected.source_links.length ? selected.source_links : [selected.source_url];
      reader.hidden = false;
      reader.innerHTML = '<a class="story-reader__back" href="' + PUBLIC_ROUTES.briefs + '">← All approved briefs</a>' +
        (selected.hero_image ? '<figure><img src="' + escapeHtml(selected.hero_image) + '" alt=""><figcaption>Florida Signal story image · source and licensing retained by the desk</figcaption></figure>' : '') +
        '<header>' + taxonomyLine(tags, "Filed under") + '<p class="story-reader__date">Event date ' + escapeHtml(formatDate(selected.event_date || selected.published_at, { month: "long", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + ' · approved ' + escapeHtml(formatDate(selected.published_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" })) + ' ET</p><h1>' + escapeHtml(selected.title) + '</h1><p class="story-reader__dek">' + escapeHtml(selected.summary || "") + '</p><span>By ' + escapeHtml(selected.byline || "Florida Signal Desk") + '</span><button class="story-report-add" type="button" data-report-add data-report-id="story:' + escapeHtml(selected.slug || selected.id || publicStoryUrl(selected)) + '" data-report-title="' + escapeHtml(selected.title) + '" data-report-meta="Approved Florida Signal brief · ' + escapeHtml(formatDate(selected.event_date || selected.published_at, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + '" data-report-url="' + escapeHtml(publicStoryUrl(selected)) + '" data-report-tags="' + taxonomyAttribute(tags) + '">＋ Add to report</button></header><div class="story-reader__body">' + body + '</div><footer><strong>Sources</strong>' + sourceLinks.filter(Boolean).map(function (url, index) { return '<a href="' + escapeHtml(url) + '" target="_blank" rel="noreferrer">Open cited source ' + (index + 1) + ' ↗</a>'; }).join("") + '<small>Florida Signal separates event dates from pull, enrichment and publication times.</small></footer>';
      grid.hidden = true;
      document.title = selected.title + " — Florida Signal";
      return;
    }
    reader.hidden = true;
    grid.hidden = false;
    if (!stories.length) {
      grid.innerHTML = '<div class="stories-empty"><p class="eyebrow">Watching, not filling space</p><h2>No brief has cleared the wire yet.</h2><p>The desk is connected. The site will publish the first article only after its source, claims, tags and human review pass.</p><a class="button" href="' + PUBLIC_ROUTES.home + '#signals">See live public-record signals →</a></div>';
      return;
    }
    grid.innerHTML = stories.map(function (story, index) {
      const tags = Array.isArray(story.tags) ? story.tags : [];
      return '<article class="story-card ' + (index === 0 ? "story-card--lead" : "") + '">' +
        (story.hero_image ? '<a class="story-card__image" href="' + publicStoryUrl(story) + '"><img src="' + escapeHtml(story.hero_image) + '" alt=""></a>' : '<a class="story-card__mark" href="' + publicStoryUrl(story) + '" aria-label="Open ' + escapeHtml(story.title) + '"><img src="/assets/emblem-2026.png" alt=""></a>') +
        '<div>' + taxonomyLine(tags, "Filed under") + '<p class="story-card__date">' + escapeHtml(formatDate(story.event_date || story.published_at, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + '</p><h2><a href="' + publicStoryUrl(story) + '">' + escapeHtml(story.title) + '</a></h2><p>' + escapeHtml(story.summary || "Approved Florida Desk report") + '</p><footer><span>' + escapeHtml(story.byline || "Florida Signal Desk") + '</span><a href="' + publicStoryUrl(story) + '">Read + sources →</a><button type="button" data-report-add data-report-id="story:' + escapeHtml(story.slug || story.id || publicStoryUrl(story)) + '" data-report-title="' + escapeHtml(story.title) + '" data-report-meta="Approved Florida Signal brief · ' + escapeHtml(formatDate(story.event_date || story.published_at, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + '" data-report-url="' + escapeHtml(publicStoryUrl(story)) + '" data-report-tags="' + taxonomyAttribute(tags) + '">＋ Add to report</button></footer></div></article>';
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
    startSignalTicker((cmsStories.length ? cmsStories.map(function (story) { return story.title; }) : state.records.slice(0, 8).map(recordHeadline)).filter(Boolean));
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

  let signalTickerTimer = null;
  function startSignalTicker(headlines) {
    if (signalTickerTimer) window.clearInterval(signalTickerTimer);
    if (!headlines || !headlines.length || document.body.classList.contains("storm-mode")) return;
    const ticker = el("#live-bar-story");
    const mobileTicker = el("#mobile-live-story");
    let index = 0;
    function flip() {
      const headline = headlines[index % headlines.length];
      [ticker, mobileTicker].forEach(function (node) {
        if (!node) return;
        node.classList.remove("is-flipping");
        window.requestAnimationFrame(function () {
          node.textContent = headline;
          node.classList.add("is-flipping");
        });
      });
      index += 1;
    }
    flip();
    signalTickerTimer = window.setInterval(flip, 5200);
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
      if (source) source.textContent = "City of Fort Lauderdale permit records · grouped by applied_date · live query · pipeline processing is separate: " + formatNumber(pulled) + " pulled / " + formatNumber(enriched) + " enriched in the latest verified run";
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
    const verifiedOperatorProfiles = {
      "c-craig-edewaard-inc": { base: "Fort Lauderdale", url: "https://www.edewaarddevelopment.com/", label: "Official site" },
      "sdg-services-llc": { base: "Weston", url: "https://www.myfloridalicense.com/LicenseDetail.asp?SID=&id=5AEFAED3D91A5FDDB6A26397E7B2ADFF", label: "Florida license" },
      "gulf-building-llc": { base: "Fort Lauderdale", url: "https://www.gulfbuilding.com/", label: "Official site" }
    };
    const operatorList = el("#operator-list");
    if (operatorList && contractors.length) {
      operatorList.innerHTML = contractors.slice(0, 6).map(function (operator, index) {
        const name = String(operator.c || "").trim();
        const key = tagSlug(name);
        const verified = verifiedOperatorProfiles[key];
        const filings = state.records.filter(function (record) { return tagSlug(record.contractor_name) === key; });
        const places = filings.reduce(function (result, record) {
          const place = recordPlace(record);
          result[place] = (result[place] || 0) + 1;
          return result;
        }, {});
        const target = Object.keys(places).sort(function (a, b) { return places[b] - places[a] || a.localeCompare(b); })[0];
        const footprint = (verified ? 'Based: ' + verified.base + ' · ' : '') + (target ? 'Newest mapped footprint: ' + target + ' · ' + formatNumber(filings.length) + ' exact-name filing' + (filings.length === 1 ? '' : 's') : 'Target footprint not resolved in the newest mapped sample');
        return '<li><span>' + String(index + 1).padStart(2, "0") + '</span><div><strong>' + escapeHtml(titleCase(name)) + '</strong><small>' + escapeHtml(footprint) + '</small></div><em>' + formatNumber(operator.n) + ' records</em><div class="operator-list__links"><a href="' + PUBLIC_ROUTES.neighborhoods + '?q=' + encodeURIComponent(name) + '">Filings ↗</a>' + (verified ? '<a href="' + escapeHtml(verified.url) + '" target="_blank" rel="noopener">' + escapeHtml(verified.label) + ' ↗</a>' : '') + '</div></li>';
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
    const investigate = recordInvestigationUrls(record);
    const title = "Florida Signal · " + recordPlace(record) + " · " + titleCase(String(record.address || record.permit_number || "development record").replace(/\s+/g, " "));
    const tags = recordTaxonomy(record);
    return placeSignature(record) + '<div class="popup-kicker">' + escapeHtml(record.permit_type || "Permit record") + '</div>' +
      '<div class="popup-title">' + escapeHtml(titleCase(String(record.address || "Address pending").replace(/\s+/g, " "))) + '</div>' +
      '<div class="popup-meta">' + escapeHtml(record.description || record.permit_number || "Public record") + (Number.isFinite(value) && value > 0 ? "<br><strong>" + escapeHtml(moneyFormat.format(value)) + " declared value</strong>" : "") + '</div>' +
      '<p class="popup-record-clock">Applied ' + escapeHtml(formatDate(record.applied_date, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + ' · ' + escapeHtml(record.permit_number || "record ID pending") + '</p>' +
      '<div class="popup-actions" aria-label="Investigate this filing">' +
        '<a href="' + escapeHtml(investigate.street) + '" target="_blank" rel="noreferrer" title="Open nearby Google Street View"><span aria-hidden="true">◉</span>Street</a>' +
        '<a href="' + escapeHtml(investigate.satellite) + '" target="_blank" rel="noreferrer" title="Open a satellite view"><span aria-hidden="true">◇</span>Satellite</a>' +
        '<a href="' + escapeHtml(investigate.official) + '" target="_blank" rel="noreferrer" title="Open the official City portal; search the displayed record number"><span aria-hidden="true">↗</span>City source</a>' +
        '<button type="button" data-popup-share data-share-url="' + escapeHtml(investigate.floridaSignal) + '" data-share-title="' + escapeHtml(title) + '" title="Share this filing"><span aria-hidden="true">↑</span>Share</button>' +
        '<button type="button" data-report-add data-report-id="permit:' + escapeHtml(record.permit_number || investigate.floridaSignal) + '" data-report-title="' + escapeHtml(title) + '" data-report-meta="' + escapeHtml((record.permit_number || "Public filing") + " · applied " + formatDate(record.applied_date, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" })) + '" data-report-url="' + escapeHtml(investigate.floridaSignal) + '" data-report-tags="' + taxonomyAttribute(tags) + '" title="Add to your Florida Signal report"><span aria-hidden="true">＋</span>Add to report</button>' +
      '</div><p class="popup-source-note">Cross-check against the City portal using the record ID above.</p>';
  }

  function markerColor(record) {
    const text = [record.permit_type, record.description].join(" ");
    if (/(demo|demolition)/i.test(text)) return "#ff6d3a";
    if (isStormRecord(record)) return "#1767ff";
    if (Number(record.valuation_usd_clean) >= 500000) return "#071b32";
    return "#00b8dc";
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
      return '<a class="neighborhood-profile neighborhood-profile--' + (index % 3) + ' neighborhood-profile--' + template + '" data-signal-tags="' + taxonomyAttribute(tags) + '" href="' + PUBLIC_ROUTES.neighborhoods + '?area=' + encodeURIComponent(item.name) + '">' + fieldMap(item, index) + '<div class="neighborhood-profile__content">' +
        '<div><span class="neighborhood-profile__rank">0' + (index + 1) + ' · ' + escapeHtml(dateSpan) + '</span><h3>' + escapeHtml(item.name) + '</h3>' + taxonomyLine(tags, "Lens") + '</div>' +
        '<dl><div><dt>Mapped filings</dt><dd>' + formatNumber(item.count) + '</dd></div><div><dt>Declared value</dt><dd>' + (declared > 0 ? escapeHtml(moneyFormat.format(declared)) : 'Not listed') + '</dd></div><div><dt>Storm-relevant</dt><dd>' + formatNumber(storm) + '</dd></div><div><dt>Operators</dt><dd>' + formatNumber(operators) + '</dd></div></dl>' +
        '<span class="neighborhood-profile__link"><i aria-hidden="true"></i> Open field brief →</span></div></a>';
    }).join("");
  }

  // The share rail is authored outside the map; its positioning ancestor is a narrow column, so it
  // straddled the map edge. Re-parent it into the Leaflet container so it anchors to the map itself.
  function adoptMapShareRail(map) {
    const container = map.getContainer();
    if (!container) return;
    const rail = document.querySelector(".map-publish-tools--map");
    if (!rail || container.contains(rail)) return;
    container.appendChild(rail);
    if (window.L && L.DomEvent) L.DomEvent.disableClickPropagation(rail);
  }

  /* Lockup tracking: measure the wordmark and stretch the tagline's letter-spacing so it spans
     exactly that width, centred. Runs on load + resize so it stays exact at every breakpoint. */
  function fitLockupTagline(nameSel, tagSel) {
    els(nameSel).forEach(function (name, i) {
      const tag = els(tagSel)[i];
      if (!tag || !name.offsetParent) return;
      const text = (tag.textContent || "").trim();
      if (!text) return;
      tag.style.letterSpacing = "normal";
      tag.style.textIndent = "0px";
      const target = name.getBoundingClientRect().width;
      const natural = tag.getBoundingClientRect().width;
      const chars = text.length;
      if (!target || !natural || chars < 2) return;
      const ls = Math.max(0, (target - natural) / chars);
      tag.style.letterSpacing = ls.toFixed(3) + "px";
      tag.style.textIndent = ls.toFixed(3) + "px";   // offset the trailing space so it stays centred
    });
  }

  function initLockups() {
    const run = function () {
      fitLockupTagline(".brand__name", ".brand__tag");
    };
    run();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(run).catch(function () {});
    let t = 0;
    window.addEventListener("resize", function () { window.clearTimeout(t); t = window.setTimeout(run, 120); });
  }

  function addMapReset(map, home) {
    const container = map.getContainer();
    if (!container || container.querySelector(".map-reset-control")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "map-reset-control";
    btn.setAttribute("aria-label", "Reset map to the default view");
    btn.innerHTML = '<span aria-hidden="true">\u27F2</span><b>Reset view</b>';
    btn.addEventListener("click", function (event) {
      event.preventDefault();
      map.setView(home && home.center ? home.center : [26.129, -80.144], home && home.zoom ? home.zoom : 12);
      if (map.closePopup) map.closePopup();
    });
    L.DomEvent.disableClickPropagation(btn);
    container.appendChild(btn);
  }

  function addMapBrand(map) {
    const container = map.getContainer();
    if (!container || container.querySelector(".map-signal-control")) return;
    const badge = document.createElement("a");
    badge.className = "map-signal-control";
    // Absolute + new tab so the brand still returns to Florida Signal when the map is embedded.
    badge.href = "https://thefloridasignal.com" + PUBLIC_ROUTES.home;
    badge.target = "_blank";
    badge.rel = "noopener";
    badge.title = "Open Florida Signal";
    badge.setAttribute("aria-label", "Florida Signal Development Intelligence — open the live desk");
    badge.innerHTML = '<img class="map-signal-control__lockup" src="/assets/lockup-2026-v2.png" ' +
      'alt="Florida Signal — Development Intelligence" width="1800" height="248">';
    L.DomEvent.disableClickPropagation(badge);
    container.appendChild(badge);
    if (!container.querySelector(".map-key")) {
      const key = document.createElement("div");
      key.className = "map-key";
      key.innerHTML = '<b>Key · permit applications</b>' +
        '<span><i style="background:#00b8dc"></i>Application</span>' +
        '<span><i style="background:#071b32"></i>$500K+ declared</span>' +
        '<span><i style="background:#1767ff"></i>Storm-related</span>' +
        '<span><i style="background:#ff6d3a"></i>Demolition</span>';
      L.DomEvent.disableClickPropagation(key);
      container.appendChild(key);
    }
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
    adoptMapShareRail(map);
    addMapReset(map, { center: (typeof settings !== 'undefined' && settings.center) || [26.129, -80.144], zoom: (typeof settings !== 'undefined' && settings.zoom) || 12 });
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
      marker.bindPopup(item.record ? mapPopup(item.record) : '<div class="popup-kicker">' + escapeHtml(settings.popupKicker || "Signal Spyglass") + '</div><div class="popup-title">' + escapeHtml(item.title) + '</div><div class="popup-meta">' + escapeHtml(item.meta) + '<br><a href="' + escapeHtml(item.url) + '">' + escapeHtml(item.linkLabel || "Open the connected map") + '</a></div>');
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
      tags: tags,
      record: record
    };
  }

  function initRecordSpotlights() {
    const signalRecords = (state.featured.length ? state.featured : state.records).slice(0, 8);
    const windowNode = el("#signals-window");
    if (windowNode) {
      const dates = signalRecords.map(function (record) { return record.applied_date; }).filter(Boolean).sort();
      windowNode.textContent = dates.length ? "Application window · " + formatDate(dates[0], { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) + "–" + formatDate(dates[dates.length - 1], { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) + " · " + formatNumber(signalRecords.length) + " mapped signals" : "Application-date window unavailable; batch time not substituted.";
    }
    renderSpyglass("signal", signalRecords.map(recordSpotlightItem), { color: "#009f91", popupKicker: "What’s Moving Spotlight" });
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
    addMapReset(map, { center: (typeof settings !== 'undefined' && settings.center) || [26.129, -80.144], zoom: (typeof settings !== 'undefined' && settings.zoom) || 12 });
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

  /* ===== Live Signals Map (SignalV1) =====
     Adds a curated, clustered, multi-source Signal layer on top of the existing map.
     Preserves all legacy behaviour: the raw permit points layer, storm lens, overlays and heat
     map are untouched. Only eligible Signals render; excluded ones never reach the map. */
  const SIGNAL_SOURCE_KEYS = ["permits", "faa", "fdep", "deeds", "easements"];
  const AMOUNT_SOURCES = { permits: 1, deeds: 1, easements: 1 };
  const CITY_SOURCES = { deeds: 1, easements: 1 };

  // The county parcel layer publishes an empty MUNICIPALITY column for all 554,358 records; the only
  // place it names a city is SITUS_CITY, a two-letter county code with no published lookup table.
  // Codes are therefore shown as the county writes them. No label is guessed.
  const SITUS_CITY_NOTE = "County situs code (Broward publishes no municipality name on this layer)";

  const signalState = {
    service: null, all: [], layer: null, counts: {}, totals: null, errors: [],
    filters: { sources: {}, status: "all", days: 365, minAmount: 0, municipality: "" },
    search: { query: "", results: [], searching: false, ran: false },
    loaded: false, error: null
  };

  function signalSourceKey(signal) {
    if (signal.source_table === "permits") return "permits";
    if (signal.source_table === "faa_oeaaa") return "faa";
    if (signal.source_table === "fdep_erp") return "fdep";
    if (signal.source_table === "broward_property_transfer_links") {
      return signal.layer === "easement" ? "easements" : "deeds";
    }
    return "other";
  }

  function visibleSignals() {
    const f = signalState.filters;
    const cutoff = new Date(Date.now() - f.days * 86400000).toISOString().slice(0, 10);
    return signalState.all.filter(function (s) {
      if (!s.public_eligibility) return false;
      if (f.sources[signalSourceKey(s)] === false) return false;
      if (f.status === "verified" && s.verification_status !== "VERIFIED") return false;
      if (f.status === "preliminary" && s.verification_status !== "PRELIMINARY") return false;
      if (s.source_record_date && s.source_record_date < cutoff) return false;
      // The amount threshold applies ONLY to sources that publish an amount (permits, deeds).
      // FAA and FDEP records state no amount, so a threshold must not silently erase them.
      if (f.minAmount > 0 && AMOUNT_SOURCES[signalSourceKey(s)] &&
          (s.valuation_or_amount == null || s.valuation_or_amount < f.minAmount)) return false;
      // Municipality is only knowable for deeds and easements (via the county situs code), so the
      // filter is scoped to those sources rather than silently hiding sources it cannot judge.
      if (f.municipality && CITY_SOURCES[signalSourceKey(s)] &&
          String((s._raw && s._raw.situs_city) || "") !== f.municipality) return false;
      return true;
    });
  }

  function signalCardHtml(s) {
    const V = window.FloridaSignalV1;
    const badge = s.verification_status === "VERIFIED"
      ? '<span class="signal-badge signal-badge--verified">Verified record</span>'
      : '<span class="signal-badge signal-badge--preliminary">Preliminary · not yet reconciled</span>';
    const rows = [];
    if (s.address || s.municipality) rows.push(["Location", [s.address, s.municipality].filter(Boolean).join(" · ")]);
    if (s.verified_parcel_id) rows.push(["County parcel (folio)", s.verified_parcel_id]);
    if (s._raw && s._raw.linkage_method) rows.push(["How it was located", "Exact county folio match"]);
    if (s.source_record_date) rows.push(["Source record date", V.fmtDate(s.source_record_date)]);
    if (s.first_detected_at) rows.push(["First detected", V.fmtDate(s.first_detected_at)]);
    if (s.valuation_or_amount) {
      rows.push([s.source_table === "broward_property_transfer_links" ? "Stated amount on the deed" : "Declared value",
                 V.money(s.valuation_or_amount)]);
    }
    if (s.project_scale) rows.push(["Scale", s.project_scale]);
    if (s.owner_or_applicant) rows.push(["Owner / applicant", s.owner_or_applicant]);
    if (s.contractor_or_sponsor) rows.push(["Contractor / sponsor", s.contractor_or_sponsor]);
    if (s.related_record_count) rows.push(["Related records", String(s.related_record_count)]);
    return '<div class="signal-card" data-signal-id="' + escapeHtml(s.signal_id) + '">' +
      '<p class="signal-card__layer" style="color:' + escapeHtml(V.LAYER_COLOR[s.layer] || "#1767ff") + '">' + escapeHtml(V.LAYER_LABEL[s.layer] || s.public_label) + '</p>' +
      '<h4 class="signal-card__headline">' + escapeHtml(s.headline || "Signal") + '</h4>' +
      badge +
      (s.why_it_matters ? '<p class="signal-card__why"><strong>Why it matters.</strong> ' + escapeHtml(s.why_it_matters) + '</p>' : '') +
      (s.what_changed ? '<p class="signal-card__changed">' + escapeHtml(s.what_changed) + '</p>' : '') +
      '<dl class="signal-card__facts">' + rows.map(function (r) { return '<dt>' + escapeHtml(r[0]) + '</dt><dd>' + escapeHtml(r[1]) + '</dd>'; }).join("") + '</dl>' +
      (s.what_to_watch ? '<p class="signal-card__watch"><strong>What to watch.</strong> ' + escapeHtml(s.what_to_watch) + '</p>' : '') +
      (s.caveat ? '<p class="signal-card__caveat">' + escapeHtml(s.caveat) + '</p>' : '') +
      '<p class="signal-card__source">' + escapeHtml(s.source_attribution || s.source_name) + '</p>' +
      '<div class="signal-card__actions">' +
        (s.source_record_url ? '<a href="' + escapeHtml(s.source_record_url) + '" target="_blank" rel="noreferrer">Open source ↗</a>' : '') +
        '<button type="button" data-report-add data-report-id="signal:' + escapeHtml(s.signal_id) + '" data-report-title="' + escapeHtml(s.headline || s.signal_id) + '" data-report-meta="' + escapeHtml((s.source_attribution || "") + (s.source_record_date ? " · " + s.source_record_date : "")) + '" data-report-url="' + escapeHtml(s.source_record_url || window.location.href) + '">＋ Add to report</button>' +
      '</div></div>';
  }

  // A Signal card must never open underneath the brand badge or the key. autoPanPadding reserves
  // room for both, so Leaflet pans the map instead of dropping the card behind an overlay.
  function signalPopupOptions() {
    // This function is called only from map code after Leaflet has loaded. Keeping
    // L.point out of module initialization lets non-map pages use the shared app.
    return {
      maxWidth: 340, className: "signal-popup", autoPan: true,
      autoPanPaddingTopLeft: L.point(24, 104),     // brand badge sits at the top centre
      autoPanPaddingBottomRight: L.point(24, 120)  // key sits bottom-left, credit strip below
    };
  }

  // Belt and braces alongside the CSS :has() rule — older engines still dim the overlays.
  function bindPopupOverlayGuard(map) {
    if (!map || map._fsPopupGuard) return;
    map._fsPopupGuard = true;
    var container = map.getContainer();
    map.on("popupopen", function () { container.classList.add("has-open-popup"); });
    map.on("popupclose", function () { container.classList.remove("has-open-popup"); });
  }

  function drawSignalLayer() {
    if (!state.map || !window.FloridaSignalV1) return;
    const V = window.FloridaSignalV1;
    if (signalState.layer) { state.map.removeLayer(signalState.layer); signalState.layer = null; }
    const items = visibleSignals();
    const useCluster = typeof L.markerClusterGroup === "function";
    const layer = useCluster
      ? L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 46, spiderfyOnMaxZoom: true, showCoverageOnHover: false })
      : L.layerGroup();
    items.forEach(function (s) {
      const marker = L.circleMarker([s.latitude, s.longitude], {
        radius: s.editorial_priority >= 70 ? 8 : 6,
        color: "#ffffff", weight: 1.6,
        fillColor: V.LAYER_COLOR[s.layer] || "#1767ff",
        fillOpacity: .92
      });
      marker.signalId = s.signal_id;              // deterministic marker identity
      marker.bindPopup(signalCardHtml(s), signalPopupOptions());
      layer.addLayer(marker);
    });
    signalState.layer = layer;
    layer.addTo(state.map);
    const countEl = el("#signal-layer-count");
    if (countEl) countEl.textContent = formatNumber(items.length);
    const emptyEl = el("#signal-empty-state");
    if (emptyEl) emptyEl.hidden = items.length > 0;
    renderSignalCounts();
  }

  function renderSignalControls() {
    const host = el("[data-signal-controls]");
    if (!host || !window.FloridaSignalV1) return;
    const V = window.FloridaSignalV1;
    const counts = {};
    signalState.all.forEach(function (s) { if (s.public_eligibility) { const k = signalSourceKey(s); counts[k] = (counts[k] || 0) + 1; } });
    // Sources are grouped by what the reader is looking for, not by which agency published them.
    const SOURCE_IN_FAMILY = {
      "development": [["permits", "Permits, demolition & storm work"]],
      "property-money": [["deeds", "Property transfers (deeds)"], ["easements", "Easements"]],
      "environment": [["fdep", "FDEP environmental permits"]],
      "skyline": [["faa", "FAA cases & cranes"]]
    };
    const f = signalState.filters;
    const cities = uniqueTags(signalState.all.map(function (s) { return s._raw && s._raw.situs_city; })).sort();

    const families = V.SOURCE_FAMILIES.map(function (fam) {
      if (fam.status !== "live") {
        return '<div class="signal-family signal-family--planned">' +
          '<p class="signal-family__label">' + escapeHtml(fam.label) + ' <span class="signal-family__tag">Not connected yet</span></p>' +
          '<p class="signal-family__note">' + escapeHtml(fam.note || "") + '</p></div>';
      }
      const rows = (SOURCE_IN_FAMILY[fam.key] || []).map(function (pair) {
        const on = f.sources[pair[0]] !== false;
        return '<label class="signal-toggle"><input type="checkbox" data-signal-source="' + pair[0] + '"' + (on ? " checked" : "") + '>' +
          '<span>' + escapeHtml(pair[1]) + ' (' + formatNumber(counts[pair[0]] || 0) + ')</span></label>';
      }).join("");
      return '<div class="signal-family"><p class="signal-family__label">' + escapeHtml(fam.label) + '</p>' + rows + '</div>';
    }).join("");

    host.innerHTML =
      '<div class="signal-controls__row"><p class="signal-readout" id="signal-count-readout">Loading…</p></div>' +
      '<form class="signal-search" data-signal-search>' +
        '<label class="signal-field signal-field--grow"><span>Search</span>' +
          '<input type="search" data-signal-query placeholder="Address, folio, instrument, permit, owner" value="' + escapeHtml(signalState.search.query) + '"></label>' +
        '<button type="submit">Search</button>' +
      '</form>' +
      '<div class="signal-results" id="signal-search-results" hidden></div>' +
      '<div class="signal-controls__row signal-controls__sources">' + families + '</div>' +
      '<div class="signal-controls__row">' +
        '<label class="signal-field"><span>Verification</span><select data-signal-status>' +
          '<option value="all"' + (f.status === "all" ? " selected" : "") + '>All</option>' +
          '<option value="verified"' + (f.status === "verified" ? " selected" : "") + '>Verified only</option>' +
          '<option value="preliminary"' + (f.status === "preliminary" ? " selected" : "") + '>Preliminary only</option></select></label>' +
        '<label class="signal-field"><span>Window</span><select data-signal-days>' +
          [30, 60, 120, 365].map(function (d) {
            return '<option value="' + d + '"' + (f.days === d ? " selected" : "") + '>' + (d === 365 ? "1 year" : d + " days") + '</option>';
          }).join("") + '</select></label>' +
        '<label class="signal-field"><span>Stated amount</span><select data-signal-amount>' +
          [[0, "Any"], [250000, "$250K+"], [1000000, "$1M+"], [5000000, "$5M+"], [25000000, "$25M+"]].map(function (p) {
            return '<option value="' + p[0] + '"' + (f.minAmount === p[0] ? " selected" : "") + '>' + p[1] + '</option>';
          }).join("") + '</select></label>' +
        (cities.length ? '<label class="signal-field"><span>Municipality</span><select data-signal-city title="' + escapeHtml(SITUS_CITY_NOTE) + '">' +
          '<option value="">All</option>' + cities.map(function (c) {
            return '<option value="' + escapeHtml(c) + '"' + (f.municipality === c ? " selected" : "") + '>' + escapeHtml(c) + '</option>';
          }).join("") + '</select></label>' : '') +
      '</div>' +
      (f.minAmount > 0 ? '<p class="signal-note">Amount filter applies to permits and deeds only. FAA and FDEP records state no amount and are unaffected.</p>' : '') +
      (cities.length ? '<p class="signal-note">' + escapeHtml(SITUS_CITY_NOTE) + '. It filters deeds and easements only.</p>' : '') +
      '<ul class="signal-legend">' + Object.keys(V.LAYER_LABEL).map(function (k) {
        return '<li><i style="background:' + V.LAYER_COLOR[k] + '"></i>' + escapeHtml(V.LAYER_LABEL[k]) + '</li>';
      }).join("") + '</ul>' +
      '<p class="signal-empty" id="signal-empty-state" hidden>No Signals match these filters. Widen the window or re-enable a source.</p>' +
      ((signalState.errors && signalState.errors.length) ? '<p class="signal-error">Temporarily unavailable: ' + escapeHtml(signalState.errors.map(function (e) { return e.source; }).join(', ')) + ' — this is a source error, not zero records.</p>' : '');

    els("[data-signal-source]", host).forEach(function (box) {
      box.addEventListener("change", function () { signalState.filters.sources[box.dataset.signalSource] = box.checked; loadSignalsForView(); });
    });
    const statusSel = el("[data-signal-status]", host);
    if (statusSel) statusSel.addEventListener("change", function () { signalState.filters.status = statusSel.value; drawSignalLayer(); });
    const daysSel = el("[data-signal-days]", host);
    if (daysSel) daysSel.addEventListener("change", function () { signalState.filters.days = Number(daysSel.value); loadSignalsForView(); });
    const amtSel = el("[data-signal-amount]", host);
    if (amtSel) amtSel.addEventListener("change", function () { signalState.filters.minAmount = Number(amtSel.value); loadSignalsForView(); });
    const citySel = el("[data-signal-city]", host);
    if (citySel) citySel.addEventListener("change", function () { signalState.filters.municipality = citySel.value; drawSignalLayer(); });
    const form = el("[data-signal-search]", host);
    if (form) form.addEventListener("submit", function (event) {
      event.preventDefault();
      const input = el("[data-signal-query]", host);
      runSignalSearch(input ? input.value : "");
    });
    if (signalState.search.ran) renderSearchResults();
  }

  // ---------- SEARCH ----------
  // Exact identifiers (folio, Clerk instrument, permit number) are looked up on the server so a
  // record can be found outside the current viewport. Free text matches the loaded set. A search
  // that finds nothing says so, and names what was searched — it never fails silently.
  function classifySearchQuery(raw) {
    const q = String(raw || "").trim();
    if (!q) return { kind: "empty", q: q };
    const compact = q.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
    if (compact.length === 12) return { kind: "folio", q: compact };
    if (/^\d{9}$/.test(compact)) return { kind: "instrument", q: compact };
    return { kind: "text", q: q };
  }

  async function runSignalSearch(raw) {
    const parsed = classifySearchQuery(raw);
    signalState.search.query = String(raw || "");
    signalState.search.ran = true;
    if (parsed.kind === "empty") {
      signalState.search.results = [];
      renderSearchResults();
      return;
    }
    signalState.search.searching = true;
    renderSearchResults();

    let results = [];
    try {
      if (parsed.kind === "folio" || parsed.kind === "instrument") {
        const opts = { limit: 50, offset: 0, sources: ["deeds", "easements"] };
        if (parsed.kind === "folio") opts.folio = parsed.q; else opts.instrument = parsed.q;
        const res = await signalState.service.load(opts);
        results = res.signals || [];
      }
      if (!results.length) {
        const needle = parsed.q.toLowerCase();
        results = signalState.all.filter(function (s) {
          if (!s.public_eligibility) return false;
          return [s.address, s.owner_or_applicant, s.contractor_or_sponsor, s.project_name,
                  s.source_record_id, s.verified_parcel_id, s.municipality, s.neighborhood]
            .some(function (v) { return v && String(v).toLowerCase().indexOf(needle) > -1; });
        }).slice(0, 50);
      }
    } catch (error) {
      signalState.search.error = String(error && error.message || error);
    }
    signalState.search.results = results;
    signalState.search.searching = false;
    renderSearchResults();
  }

  function renderSearchResults() {
    const host = el("#signal-search-results");
    if (!host) return;
    const V = window.FloridaSignalV1;
    const st = signalState.search;
    if (!st.ran) { host.hidden = true; return; }
    host.hidden = false;
    if (st.searching) { host.innerHTML = '<p class="signal-loading">Searching…</p>'; return; }
    if (!st.results.length) {
      host.innerHTML = '<p class="signal-empty">No match for “' + escapeHtml(st.query) + '”. ' +
        'Searched: address, folio, Clerk instrument, permit number, owner and party names across permits, deeds, easements, FDEP and FAA. ' +
        'Mortgages, liens, lis pendens and judgments are not searchable on the map — the Clerk’s public files carry no parcel for them.</p>';
      return;
    }
    host.innerHTML = '<p class="signal-results__head">' + formatNumber(st.results.length) + ' match' + (st.results.length === 1 ? "" : "es") + '</p>' +
      st.results.slice(0, 25).map(function (s, i) {
        const badge = s.verification_status === "VERIFIED" ? "Verified" : (s.verification_status === "PRELIMINARY" ? "Preliminary" : s.verification_status);
        return '<button type="button" class="signal-result" data-search-index="' + i + '">' +
          '<span class="signal-result__layer" style="color:' + escapeHtml(V.LAYER_COLOR[s.layer] || "#1767ff") + '">' + escapeHtml(V.LAYER_LABEL[s.layer] || "") + '</span>' +
          '<span class="signal-result__title">' + escapeHtml(s.headline || s.signal_id) + '</span>' +
          '<span class="signal-result__meta">' + escapeHtml(s.source_name) + ' · ' + escapeHtml(badge) +
          (s.source_record_date ? ' · ' + escapeHtml(V.fmtDate(s.source_record_date)) : '') + '</span></button>';
      }).join("");
    els("[data-search-index]", host).forEach(function (btn) {
      btn.addEventListener("click", function () {
        const s = signalState.search.results[Number(btn.dataset.searchIndex)];
        if (!s || s.latitude == null || s.longitude == null || !state.map) return;
        state.map.setView([s.latitude, s.longitude], Math.max(state.map.getZoom(), 17));
        L.popup(signalPopupOptions())
          .setLatLng([s.latitude, s.longitude]).setContent(signalCardHtml(s)).openOn(state.map);
      });
    });
  }

  function signalBoundsFromMap() {
    if (!state.map) return null;
    var b = state.map.getBounds();
    return { south: b.getSouth().toFixed(5), north: b.getNorth().toFixed(5),
             west: b.getWest().toFixed(5), east: b.getEast().toFixed(5) };
  }

  function signalQueryOptions(useBounds) {
    var f = signalState.filters;
    var startDate = new Date(Date.now() - f.days * 86400000).toISOString().slice(0, 10);
    var sources = Object.keys(f.sources).filter(function (k) { return f.sources[k] !== false; });
    return {
      bounds: useBounds === false ? null : signalBoundsFromMap(),
      startDate: startDate,
      sources: sources.length ? sources : SIGNAL_SOURCE_KEYS.slice(),
      minAmount: f.minAmount || 0,
      municipality: f.municipality || "",
      limit: 600, offset: 0
    };
  }

  function renderSignalCounts() {
    var host = el("#signal-count-readout");
    if (!host) return;
    var c = signalState.counts || {};
    var f = signalState.filters;
    // Report only on sources the reader currently has switched on. Counts left over from a previous
    // load must never be added in — a stale number is worse than no number.
    var active = SIGNAL_SOURCE_KEYS.filter(function (k) { return f.sources[k] !== false; });
    var loaded = signalState.all.filter(function (s) {
      return s.public_eligibility && active.indexOf(signalSourceKey(s)) > -1;
    }).length;
    var visible = visibleSignals().length;
    var filteredTotal = active.reduce(function (sum, k) {
      var v = c[k] && c[k].filteredTotal; return v == null ? sum : sum + v;
    }, 0);
    var anyUnknown = active.some(function (k) { return !c[k] || c[k].filteredTotal == null; });
    var eligTotal = signalState.totals && signalState.totals.all;
    // A source that returned a full page has more records behind it. Say so plainly rather than
    // presenting a capped page as if it were the complete set for this view.
    var capped = active.filter(function (k) { return c[k] && c[k].hasMore; });
    host.innerHTML =
      '<strong>' + formatNumber(visible) + '</strong> Signals shown · ' +
      formatNumber(loaded) + ' loaded in this view' +
      (capped.length
        ? '<small class="signal-readout__cap">More records exist here than one view can load (' +
          escapeHtml(capped.join(", ")) + ' reached the per-request cap of ' +
          formatNumber(signalState.service ? signalState.service.PAGE_CAP : 600) +
          '). Zoom in or narrow the window for complete coverage of an area.</small>'
        : '') +
      (filteredTotal && !anyUnknown
        ? '<small>≈' + formatNumber(filteredTotal) + ' match these filters countywide (planner estimate)</small>'
        : '') +
      (eligTotal ? '<small>' + formatNumber(eligTotal) + ' eligible Signals across Broward (all dates)</small>' : '');
  }

  var signalLoadTimer = 0;
  async function loadSignalsForView(opts) {
    if (!signalState.service) return;
    var host = el("[data-signal-controls]");
    if (host) host.setAttribute("data-loading", "1");
    try {
      var result = await signalState.service.load(signalQueryOptions((opts && opts.all) ? false : true));
      if (result.stale) return;                       // a newer request won
      signalState.all = result.signals;
      signalState.counts = result.counts;      // replaced wholesale; no key survives a source change
      signalState.errors = result.errors || [];
      renderSignalControls();
      drawSignalLayer();
      renderSignalCounts();
    } catch (error) {
      if (host) host.innerHTML = '<p class="signal-error">Signals are temporarily unavailable. No substitute data is shown.</p>';
    } finally {
      if (host) host.removeAttribute("data-loading");
    }
  }

  function scheduleSignalReload() {
    window.clearTimeout(signalLoadTimer);
    signalLoadTimer = window.setTimeout(function () { loadSignalsForView(); }, 420);   // debounce pan/zoom
  }

  async function initSignalLayer() {
    if (!state.map || !window.FloridaSignalV1 || !el("[data-signal-controls]")) return;
    var host = el("[data-signal-controls]");
    host.innerHTML = '<p class="signal-loading">Loading Signals…</p>';
    signalState.service = window.FloridaSignalV1.createService({ supabaseUrl: SUPABASE_URL, key: SUPABASE_KEY });
    // Unbounded eligible totals first (server-side counts only — no rows transferred).
    signalState.service.totals({}).then(function (t) { signalState.totals = t; renderSignalCounts(); }).catch(function () {});
    bindPopupOverlayGuard(state.map);
    await loadSignalsForView();
    state.map.on("moveend zoomend", scheduleSignalReload);
  }

  async function initMaps() {
    const node = el("#home-map") || el("#full-map") || el("#data-room-map");
    if (!node || !window.L || !state.records.length) return;
    try { await buildMap(node); await initSignalLayer(); }
    catch (error) {
      node.innerHTML = '<div class="loading-row">The official neighborhood layer is temporarily unavailable. No substitute map is being shown.</div>';
    }
  }

  function applyMapLens(lens, options) {
    const settings = options || {};
    state.lens = lens === "storm" ? "storm" : "all";
    els("[data-map-lens]").forEach(function (button) { button.classList.toggle("is-active", button.dataset.mapLens === state.lens); });
    if (!state.map || !state.neighborhoods) return;
    const records = state.lens === "storm" ? state.records.filter(isStormRecord) : state.records;
    drawMarkers(state.map, records);
    if (state.overlayVisibility.heat) {
      const heat = rebuildHeatLayer();
      if (heat) heat.addTo(state.map);
    }
    renderNeighborhoodLists(neighborhoodCounts(state.neighborhoods.features || [], records), state.map);
    if (settings.fit) {
      const points = records.filter(function (record) { return Number.isFinite(Number(record.lat)) && Number.isFinite(Number(record.lon)); }).map(function (record) { return [Number(record.lat), Number(record.lon)]; });
      if (points.length === 1) state.map.setView(points[0], 15);
      else if (points.length > 1) state.map.fitBounds(points, { padding: [38, 38], maxZoom: 14 });
    }
  }

  function initLensSwitch() {
    if (new URLSearchParams(window.location.search).get("storm") === "ready") state.lens = "storm";
    els("[data-map-lens]").forEach(function (button) {
      button.classList.toggle("is-active", button.dataset.mapLens === state.lens);
      button.addEventListener("click", function () {
        applyMapLens(button.dataset.mapLens, { fit: true });
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
      window.location.href = PUBLIC_ROUTES.neighborhoods + "?q=" + encodeURIComponent(input ? input.value.trim() : "");
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
    if (!status && !updated && !el("#graphic-desk") && !el("#storm-operations") && !el(".storm-promise")) return;
    try {
      let response = await fetch(apiUrl("/api/storms"), { cache: "no-store" });
      if (!response.ok) response = await fetch("https://www.nhc.noaa.gov/CurrentStorms.json", { cache: "no-store" });
      if (!response.ok) throw new Error("NHC unavailable");
      const data = await response.json();
      const storms = (data.activeStorms || []).filter(function (storm) { return String(storm.id || "").toLowerCase().startsWith("al"); });
      state.storms = storms;
      state.stormPayload = data;
      if (status) status.textContent = storms.length ? storms.map(function (storm) { return storm.name + " · " + storm.classification + " " + storm.intensity + " kt"; }).join(" · ") : "No named Atlantic storms active";
      const promiseStatus = el("#promise-storm-status");
      if (promiseStatus) promiseStatus.textContent = storms.length ? formatNumber(storms.length) + " Atlantic system" + (storms.length === 1 ? "" : "s") + " active · NHC live" : "NHC outlook live · standing by";
      const responseState = el("#storm-response-state");
      if (responseState) responseState.textContent = storms.length ? formatNumber(storms.length) + " Atlantic system" + (storms.length === 1 ? "" : "s") : "Standby";
      const newest = storms[0];
      if (updated) updated.textContent = newest && newest.lastUpdate ? "NHC " + formatDate(newest.lastUpdate, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET" : "NHC live";
      renderStormOperations(data);
      renderGraphicDesk();
      renderStormPromo();
    } catch (error) {
      if (status) status.textContent = "Open the official NHC outlook";
      const promiseStatus = el("#promise-storm-status");
      if (promiseStatus) promiseStatus.textContent = "Official NHC outlook · open source";
      const responseState = el("#storm-response-state");
      if (responseState) responseState.textContent = "Source check needed";
      if (updated) updated.textContent = "Source link active";
      renderStormOperations(null);
      renderGraphicDesk();
      renderStormPromo();
    }
  }

  function renderStormPromo() {
    const active = el("[data-storm-active-count]");
    const records = el("[data-storm-record-count]");
    if (active) active.textContent = formatNumber(state.storms.length);
    if (records) records.textContent = formatNumber(state.records.filter(isStormRecord).length);
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
      const response = await fetch(apiUrl("/api/meetings"), { cache: "no-store" });
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
    if (updated) updated.textContent = "Official calendar checked " + formatDate(payload.updated_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET · refreshed every 15 minutes";

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
        const tags = ["format:meeting", "market:" + tagSlug(meeting.market || "broward"), "county:" + tagSlug(meeting.county || "broward-county"), "city:" + tagSlug(meeting.city || "fort-lauderdale"), "topic:" + type, "source:" + tagSlug(meeting.source), "geography:" + tagSlug(meeting.location || meeting.city || "broward"), meeting.agenda_available ? "urgency:agenda-posted" : "urgency:agenda-watch"];
        const meetingUrl = meeting.agenda_url || meeting.details_url || payload.calendar_url;
        const watchLabel = type === "industry" ? "Industry" : type === "development" ? "Development review" : type === "commission" ? "Commission" : "Public board";
        return '<article class="meeting-row" data-signal-tags="' + taxonomyAttribute(tags) + '">' +
          '<div class="meeting-row__date"><span>' + escapeHtml(formatDate(meetingDate, { weekday: "short" })) + '</span><strong>' + escapeHtml(formatDate(meetingDate, { day: "numeric" })) + '</strong><small>' + escapeHtml(formatDate(meetingDate, { month: "short" })) + ' · ' + escapeHtml(meeting.time || "Time pending") + '</small></div>' +
          '<div class="meeting-row__body"><p>' + escapeHtml(watchLabel) + ' · ' + escapeHtml(daysAway ? "in " + daysAway + " days" : "today") + '</p><h2>' + escapeHtml(meeting.title) + '</h2><span>' + escapeHtml(meeting.location || "Location pending") + '</span><small>' + escapeHtml(meeting.source) + '</small></div>' +
          '<div class="meeting-row__actions"><a class="meeting-row__details" href="' + escapeHtml(meetingUrl) + '" target="_blank" rel="noreferrer">' + agendaLabel + '</a>' +
          (meeting.watch_url ? '<a class="meeting-row__watch" href="' + escapeHtml(meeting.watch_url) + '" target="_blank" rel="noreferrer"><span class="meeting-tv" aria-hidden="true"></span>Watch live</a>' : '') +
          (meeting.ical_url ? '<a class="meeting-row__calendar" href="' + escapeHtml(meeting.ical_url) + '" target="_blank" rel="noreferrer" aria-label="Add ' + escapeHtml(meeting.title) + ' to calendar">＋ Calendar</a>' : '') +
          '<button class="meeting-row__brief" type="button" data-report-add data-report-id="meeting:' + escapeHtml((meeting.date || "") + ":" + meeting.title) + '" data-report-title="' + escapeHtml(meeting.title) + '" data-report-meta="' + escapeHtml(formatDate(meetingDate, { month: "short", day: "numeric", year: "numeric" }) + " · " + (meeting.time || "Time pending") + " · " + (meeting.location || "Location pending")) + '" data-report-url="' + escapeHtml(meetingUrl) + '" data-report-tags="' + taxonomyAttribute(tags) + '">＋ Add to report</button></div></article>';
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
      const response = await fetch(apiUrl("/api/agenda-recon"), { cache: "no-store" });
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
          const street = "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=" + point.join(",");
          const satellite = "https://www.google.com/maps/@?api=1&map_action=map&center=" + point.join(",") + "&zoom=19&basemap=satellite";
          const reconTags = uniqueTags(["format:agenda-recon", "market:" + tagSlug(item.market || "broward"), "county:" + tagSlug(item.county || "broward-county"), "city:" + tagSlug(item.city || "fort-lauderdale"), "topic:agenda-recon", "source:official-agenda"].concat(item.neighborhood ? ["neighborhood:" + tagSlug(item.neighborhood)] : []).concat(item.zip ? ["zip:" + tagSlug(item.zip)] : []));
          L.circleMarker(point, { radius: 8, color: "#071b32", weight: 2, fillColor: "#ffcf4a", fillOpacity: .95 }).addTo(reconMap).bindPopup('<div class="popup-kicker">Agenda Recon · item ' + escapeHtml(item.item_number) + '</div><div class="popup-title">' + escapeHtml(item.property_address) + '</div><div class="popup-meta">' + escapeHtml(item.meeting_title) + '</div><div class="popup-actions"><a href="' + escapeHtml(street) + '" target="_blank" rel="noreferrer"><span>◉</span>Street</a><a href="' + escapeHtml(satellite) + '" target="_blank" rel="noreferrer"><span>◇</span>Satellite</a><a href="' + escapeHtml(item.source_url) + '" target="_blank" rel="noreferrer"><span>↗</span>Packet</a><button type="button" data-report-add data-report-id="agenda:' + escapeHtml(item.source_hash || item.source_url) + '" data-report-title="' + escapeHtml(item.property_address + " · " + item.meeting_title) + '" data-report-meta="' + escapeHtml(item.meeting_date + " · item " + item.item_number) + '" data-report-url="' + escapeHtml(item.source_url) + '" data-report-tags="' + taxonomyAttribute(reconTags) + '"><span>＋</span>Add to report</button></div>');
        });
        if (bounds.length) reconMap.fitBounds(bounds, { padding: [35, 35], maxZoom: 15 });
      }
      if (status) status.textContent = items.length ? formatNumber(items.length) + " source-cleared agenda propert" + (items.length === 1 ? "y" : "ies") : "No future property item has cleared the source gate yet";
      results.innerHTML = items.length ? items.map(function (item) {
        const tags = uniqueTags(["format:agenda-recon", "market:" + tagSlug(item.market || "broward"), "county:" + tagSlug(item.county || "broward-county"), "city:" + tagSlug(item.city || "fort-lauderdale"), "topic:agenda-recon", "source:official-agenda"].concat(item.neighborhood ? ["neighborhood:" + tagSlug(item.neighborhood)] : []).concat(item.zip ? ["zip:" + tagSlug(item.zip)] : []));
        return '<article class="recon-result" data-signal-tags="' + taxonomyAttribute(tags) + '"><p>' + escapeHtml(item.meeting_date) + ' · item ' + escapeHtml(item.item_number) + '</p><h3>' + escapeHtml(item.property_address) + '</h3><span>' + escapeHtml(item.proposed_action || item.meeting_title) + '</span><div><a href="' + escapeHtml(item.source_url) + '" target="_blank" rel="noreferrer">Open cited packet ↗</a><a href="' + PUBLIC_ROUTES.neighborhoods + '?q=' + encodeURIComponent(item.property_address) + '">Open field map →</a><button type="button" data-report-add data-report-id="agenda:' + escapeHtml(item.source_hash || item.source_url) + '" data-report-title="' + escapeHtml(item.property_address + " · " + item.meeting_title) + '" data-report-meta="' + escapeHtml(item.meeting_date + " · item " + item.item_number) + '" data-report-url="' + escapeHtml(item.source_url) + '" data-report-tags="' + taxonomyAttribute(tags) + '">＋ Add to report</button></div></article>';
      }).join("") : '<p class="meeting-empty"><strong>Watching, not guessing.</strong> No upcoming official packet currently contains a property item that has completed extraction, coordinate resolution and editorial clearance.</p>';
    } catch (error) {
      results.innerHTML = '<p class="meeting-empty">Agenda sweep is temporarily unavailable. No older or inferred property pins are being substituted.</p>';
      const status = el("#recon-map-status");
      if (status) status.textContent = "Source check needed";
    }
  }

  function renderStormRecords() {
    const records = state.records.filter(isStormRecord);
    const count = el("#storm-permit-count");
    if (count) count.textContent = formatNumber(records.length);
    const mapWindow = el("#storm-map-window");
    if (mapWindow) {
      const dates = records.map(function (record) { return record.applied_date; }).filter(Boolean).sort();
      mapWindow.textContent = dates.length ? "Application window · " + formatDate(dates[0], { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) + "–" + formatDate(dates[dates.length - 1], { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) + " · mapped points only" : "Application-date window unavailable; no batch-pull date substituted.";
    }
    const preparation = state.records.filter(function (record) { return /(roof|impact|shutter|generator|seawall|sea wall|drain|flood|elevation|window|door)/i.test([record.permit_type, record.permit_category, record.description].join(" ")); });
    const openings = state.records.filter(function (record) { return /(impact|shutter|window|door|glazing|opening)/i.test([record.permit_type, record.permit_category, record.description, record.work_type].join(" ")); });
    const recovery = state.records.filter(function (record) { return /(repair|restore|restoration|remediation|damage|roof|demolition|rebuild)/i.test([record.permit_type, record.permit_category, record.description].join(" ")); });
    const preCount = el("#storm-phase-pre");
    const recoveryCount = el("#storm-phase-recovery");
    if (preCount) preCount.textContent = formatNumber(preparation.length) + " records";
    const openingCount = el("#storm-opening-count");
    if (openingCount) openingCount.textContent = formatNumber(openings.length);
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
      return '<div class="graphic-network"><div class="graphic-network__core"><img src="/assets/emblem-2026.png" alt=""><span>ENTITY<br>LENS</span></div>' + items.map(function (item, index) {
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
      const pageUrl = window.location.origin + CITY_ROOT + "/share/" + encodeURIComponent(slug) + ".html";
      const embedUrl = window.location.origin + window.location.pathname + "?embed=" + encodeURIComponent(slug);
      const embedCode = '<iframe src="' + embedUrl + '" width="100%" height="620" loading="lazy" title="Florida Signal — ' + title.replace(/<[^>]+>/g, "") + '"></iframe>';
      const shareTitle = "Florida Signal · " + title.replace(/<[^>]+>/g, "");
      const tags = uniqueTags(["format:graphic", "source:florida-signal", "topic:" + tagSlug(slug)].concat(settings.tags || []));
      const openLink = settings.href ? '<a class="graphic-card__open" href="' + escapeHtml(settings.href) + '">' + escapeHtml(settings.linkLabel || "Open the connected intelligence") + ' →</a>' : '';
      return '<article class="graphic-card ' + (settings.tone === "navy" ? "graphic-card--navy " : "") + (settings.wide ? "graphic-card--wide" : "") + '" data-signal-tags="' + taxonomyAttribute(tags) + '" id="' + slug + '">' +
        '<div class="graphic-card__top"><p>' + escapeHtml(kicker) + '</p><span>' + escapeHtml(settings.status || "REAL RECORD") + '</span></div>' +
        '<span class="graphic-card__crest" aria-hidden="true"><img src="/assets/emblem-2026.png" alt=""></span>' +
        '<h2>' + title + '</h2><p class="graphic-card__dek">' + dek + '</p>' + openLink + '<div class="graphic-card__body">' + body + '</div>' +
        '<p class="graphic-card__clock">' + escapeHtml(settings.clock || "Public event date · data update shown") + '</p><a class="graphic-card__sponsor" href="mailto:desk@thefloridasignal.com?subject=' + encodeURIComponent("Sponsor Florida Signal graphic: " + slug) + '"><span>Present this intelligence</span><strong>Your logo here ↗</strong></a>' +
        '<div class="graphic-card__brand"><span><img src="/assets/' + (settings.tone === "navy" ? "emblem-2026-white.png" : "emblem-2026.png") + '" alt=""><b>Florida Signal</b><small>Development intelligence</small></span><time>' + escapeHtml(settings.stamp || applicationWindowStamp) + '</time><div>' +
        '<a class="publish-social publish-social--x" data-network="X" href="https://twitter.com/intent/tweet?text=' + encodeURIComponent(shareTitle) + '&url=' + encodeURIComponent(pageUrl) + '" target="_blank" rel="noreferrer" aria-label="Share on X">X</a>' +
        '<a class="publish-social publish-social--linkedin" data-network="LinkedIn" href="https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(pageUrl) + '" target="_blank" rel="noreferrer" aria-label="Share on LinkedIn">in</a>' +
        '<a class="publish-social publish-social--facebook" data-network="Facebook" href="https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(pageUrl) + '" target="_blank" rel="noreferrer" aria-label="Share on Facebook">f</a>' +
        '<button type="button" data-share-card data-share-url="' + escapeHtml(pageUrl) + '" data-share-title="' + escapeHtml(shareTitle) + '" aria-label="Share this graphic">↗</button>' +
        '<button type="button" data-copy-embed data-embed-code="' + escapeHtml(embedCode) + '">&lt;/&gt; Embed</button>' +
        '<button type="button" data-report-add data-report-id="graphic:' + escapeHtml(slug) + '" data-report-title="' + escapeHtml(shareTitle) + '" data-report-meta="' + escapeHtml(settings.stamp || applicationWindowStamp) + '" data-report-url="' + escapeHtml(settings.href || pageUrl) + '" data-report-tags="' + taxonomyAttribute(tags) + '" aria-label="Add graphic to Field Brief" title="Add to Field Brief">＋</button></div></div></article>';
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
    const stormFamilies = [
      { label: "Roofs", test: /roof/i },
      { label: "Windows + shutters", test: /(window|door|glazing|shutter|opening)/i },
      { label: "Drainage", test: /(drain|flood|elevation|sewer)/i },
      { label: "Seawalls + marine", test: /(seawall|sea wall|marine|dock)/i },
      { label: "Generators + electric", test: /(generator|electric|solar)/i }
    ];
    const stormMix = stormFamilies.map(function (family) {
      return { label: family.label, value: stormRecords.filter(function (record) { return family.test.test([record.permit_type, record.permit_category, record.description, record.work_type].join(" ")); }).length };
    }).filter(function (item) { return item.value > 0; });
    const cards = [
      card("application-pulse", "APPLICATION DATES · 14 CALENDAR DAYS", formatNumber(applicationTotal) + " <em>FILED</em>", "Fort Lauderdale permit applications grouped by the date the public application was filed—not by the day a batch arrived.", pulseBody, { tone: "navy", wide: true, status: "LIVE QUERY", stamp: applicationWindowStamp, clock: "City permit table · applied_date · window " + spanDate(APPLICATION_WINDOW_START, now.toISOString().slice(0, 10)) + " · latest filing present " + stampDate(applicationThrough) + " · zero days retained", href: PUBLIC_ROUTES.neighborhoods + "#full-map", linkLabel: "Explore these filings on the live map" }),
      card("place-lens", "HYPERLOCAL · OFFICIAL BOUNDARIES", "PLACE <em>LENS</em>", "The newest geocoded application sample resolved into official City neighborhoods and Census ZIP areas. Circle size expresses relative filing count inside this sample.", placeBody, { wide: true, status: "CITY + CENSUS", stamp: mappedStamp, clock: "Newest " + formatNumber(state.records.length) + " geocoded permit applications returned · applied_date span " + spanDate(mappedDates[0], mappedDates.slice(-1)[0]) + " · City neighborhoods + Census ZCTAs", href: PUBLIC_ROUTES.neighborhoods + "#full-map", linkLabel: "Open the neighborhood and ZIP map" }),
      card("trades-pulse", "DIAGRAM OF THE DAY · LIVE WORK MIX", "WHAT FORT LAUDERDALE IS <em>BUILDING</em>", "Permit categories become momentum intelligence when trade mix, place and filing time are read together.", bars(trades), { tone: "navy", wide: true, status: "LIVE QUERY", stamp: mappedStamp, clock: "Newest " + formatNumber(state.records.length) + " geocoded applications · applied_date span " + spanDate(mappedDates[0], mappedDates.slice(-1)[0]) + " · categories may overlap when one filing names more than one trade", href: PUBLIC_ROUTES.neighborhoods + "#full-map", linkLabel: "Investigate the work mix on the map" }),
      card("high-value", "CAPPED HIGH-VALUE FILING QUEUE", highValueTop ? escapeHtml(moneyFormat.format(Number(highValueTop.valuation_usd_clean))) + " <em>TOP FILING</em>" : "VALUE <em>PENDING</em>", highValueTop ? escapeHtml(recordHeadline(highValueTop)) : "No valued high-dollar filing is available in the current query.", tiles([{ value: highValue.length ? formatNumber(highValue.length) : "0", label: "valued records returned" }, { value: highValueTotal ? compactFormat.format(highValueTotal) : "$0", label: "declared value in returned queue" }]), { stamp: featuredStamp, clock: "First " + formatNumber(state.featured.length) + " records in ordered current-month $100K+ query · applied_date span " + spanDate(featuredDates[0], featuredDates.slice(-1)[0]) + " · not a complete monthly total", href: PUBLIC_ROUTES.neighborhoods + "#full-map", linkLabel: "Open the exact high-value filings" }),
      card("value-universe", "ENRICHED PROPERTY CONTEXT", "VALUE <em>LADDER</em>", "Where parcel-linked permit records sit across the best-available property-value universe.", bars(values), { tone: "navy", stamp: cacheStamp, clock: "Verified dashboard snapshot · enriched property values · update time shown", href: PUBLIC_ROUTES.broward, linkLabel: "Open the Broward property record" }),
      card("operator-board", "NORMALIZED CONTRACTOR NAMES", "OPERATOR <em>BOARD</em>", "Names appearing most often in the normalized public record set. This measures filing activity—not quality or performance.", ranks(contractors), { stamp: cacheStamp, clock: "Verified dashboard snapshot · normalized contractor names · not a performance ranking", href: PUBLIC_ROUTES.broward, linkLabel: "Open the operator evidence" }),
      card("records-desk", "BROWARD RECORD · COVERAGE", "RECORDS <em>DESK</em>", "Recorded instruments, parcel links, ownership changes and permit joins—shown with their separate scales and source dates.", recordRings + '<p class="graphic-inline-stat"><strong>' + formatNumber(parcelCoverage) + '%</strong> of tracked permit records parcel-linked</p>', { tone: "navy", stamp: browardStamp, clock: "Broward records · latest recording date " + (stats.broward_fresh ? formatDate(stats.broward_fresh, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) : "pending"), href: PUBLIC_ROUTES.broward, linkLabel: "Open deeds, liens and ownership intelligence" }),
      card("company-lens", "SUNBIZ + OWNERSHIP RESOLUTION", "WHO IS <em>BEHIND IT</em>", "An address becomes an entity trail through public company filings, parcel joins and recorded instruments.", companyNetwork, { stamp: cacheStamp, clock: "Verified data snapshot · state registration/filing dates drive company movement; pull time shows freshness only", href: PUBLIC_ROUTES.broward, linkLabel: "Follow the ownership trail" }),
      card("storm-window", "ROOFS · WINDOWS · DRAINAGE · GENERATORS", formatNumber(stormRecords.length) + " <em>LOCAL FILINGS</em>", "What the current permit sample says people are hardening. These are applications—not completed installations or evidence of storm damage.", stormMix.length ? bars(stormMix, "graphic-bar--storm") : '<div class="graphic-empty">No classified hardening filings are present in this mapped application window.</div>', { tone: "navy", stamp: mappedStamp, status: "STORM WATCH DATA", clock: "Mapped hardening applications · applied_date span " + spanDate(mappedDates[0], mappedDates.slice(-1)[0]) + " · categories may overlap", href: PUBLIC_ROUTES.storm, linkLabel: "Open the filings and official outlook on Storm Watch" }),
      card("meetings-watch", "PUBLIC + INDUSTRY ROOMS", nextMeeting ? escapeHtml(formatDate(nextMeeting.date, { month: "short", day: "numeric", timeZone: "America/New_York" })) + " <em>ON DECK</em>" : "ROOMS <em>WATCHED</em>", nextMeeting ? escapeHtml(nextMeeting.title) : "The official calendar is being checked; no meeting is inferred from stale data.", state.meetings.length ? meetingTimeline(state.meetings) : '<div class="graphic-empty">Official calendar check in progress…</div>', { stamp: meetingStamp, clock: "Scheduled meeting span " + spanDate(meetingDates[0], meetingDates.slice(-1)[0]) + " · official/public and named industry calendars · refreshed every 15 minutes", href: PUBLIC_ROUTES.meetings, linkLabel: "Open agendas, rooms and stream links" })
    ];

    const embedSlug = new URLSearchParams(window.location.search).get("embed");
    const visibleCards = embedSlug ? cards.filter(function (html) { return html.includes('id="' + embedSlug + '"'); }) : cards;
    if (embedSlug) document.body.classList.add("graphic-embed");
    const applicationCount = el("#data-room-application-count");
    const mapCount = el("#data-room-map-count");
    const stormCount = el("#data-room-storm-count");
    const mapWindow = el("#data-room-map-window");
    if (applicationCount) applicationCount.textContent = formatNumber(applicationTotal);
    if (mapCount) mapCount.textContent = formatNumber(state.records.length);
    if (stormCount) stormCount.textContent = formatNumber(stormRecords.length);
    if (mapWindow) mapWindow.textContent = "Application window · " + spanDate(mappedDates[0], mappedDates.slice(-1)[0]) + " · " + formatNumber(state.records.length) + " mapped filings";
    function cardWithId(slug) { return cards.find(function (html) { return html.includes('id="' + slug + '"'); }) || ""; }
    function group(id, kicker, title, dek, slugs, featured) {
      return '<section class="graphic-group' + (featured ? ' graphic-group--featured' : '') + '" id="' + id + '"><header class="graphic-group__head"><div><p>' + escapeHtml(kicker) + '</p><h2>' + escapeHtml(title) + '</h2></div><span>' + escapeHtml(dek) + '</span></header><div class="graphic-group__grid">' + slugs.map(cardWithId).join("") + '</div></section>';
    }
    root.innerHTML = embedSlug ? (visibleCards.join("") || '<p class="loading-row">That graphic is not available.</p>') : [
      group("today", "01 · Now", "The live picture", "The application clock and today’s work mix.", ["application-pulse", "trades-pulse"], true),
      group("places", "02 · Places", "Where it is moving", "Neighborhood, ZIP, value and operator context.", ["place-lens", "high-value", "operator-board"]),
      group("property", "03 · Property", "Who and what sit behind it", "Parcel, instrument, ownership and entity joins.", ["records-desk", "value-universe", "company-lens"]),
      group("watch", "04 · Watch", "What is coming next", "Hardening filings, official outlooks, agendas and rooms.", ["storm-window", "meetings-watch"])
    ].join("");
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

  function renderDiagramPromo() {
    const panel = el(".diagram-watch");
    if (!panel || !state.records.length) return;
    const chart = el(".diagram-watch__chart", panel);
    const title = el(".diagram-watch__title strong", panel);
    const detail = el(".diagram-watch__title span", panel);
    const insight = el("[data-diagram-insight]", panel);
    const day = el("[data-diagram-day]", panel);
    if (!chart) return;
    const categories = [
      { label: "Mechanical", pattern: /mechanical|hvac|air condition|a\/c/i },
      { label: "Plumbing", pattern: /plumb|drain|sewer/i },
      { label: "Electrical", pattern: /electr|solar/i },
      { label: "Roofs", pattern: /roof/i },
      { label: "Windows + doors", pattern: /window|door|shutter|opening/i },
      { label: "Pools + spas", pattern: /\bpool\b|\bspa\b/i }
    ].map(function (category) {
      const value = state.records.filter(function (record) {
        return category.pattern.test([record.permit_type, record.permit_category, record.description, record.work_type].join(" "));
      }).length;
      return { label: category.label, value: value };
    }).sort(function (a, b) { return b.value - a.value; });
    const maximum = Math.max.apply(null, categories.map(function (category) { return category.value; }).concat([1]));
    const classifiedTotal = categories.reduce(function (sum, category) { return sum + category.value; }, 0);
    chart.innerHTML = categories.map(function (category) {
      return '<div><span>' + escapeHtml(category.label) + '</span><i><b style="width:' + Math.max(category.value ? 6 : 0, Math.round((category.value / maximum) * 100)) + '%"></b></i><strong>' + formatNumber(category.value) + '</strong></div>';
    }).join("");
    const dates = state.records.map(function (record) { return record.applied_date; }).filter(Boolean).sort();
    const leader = categories[0];
    const share = classifiedTotal && leader ? Math.round((leader.value / classifiedTotal) * 100) : 0;
    if (day) day.textContent = "Diagram of the day · " + new Intl.DateTimeFormat("en-US", { weekday: "long", timeZone: "America/New_York" }).format(new Date());
    if (title) title.textContent = "What Fort Lauderdale is building";
    if (detail) detail.textContent = dates.length ? "Mapped permits · applied " + formatDate(dates[0], { month: "short", day: "numeric" }) + "–" + formatDate(dates[dates.length - 1], { month: "short", day: "numeric" }) : "Current mapped application window";
    if (insight) insight.textContent = leader && leader.value ? leader.label + " leads: " + formatNumber(leader.value) + " records · " + formatNumber(share) + "% of the categories shown. We connect trade mix, place and filing time to uncover momentum intelligence." : "No classified permit mix is available in the current mapped sample.";
    chart.setAttribute("aria-label", categories.map(function (category) { return category.label + " " + formatNumber(category.value); }).join(", ") + ". Current mapped permit application sample.");
  }

  function renderLiveWindows() {
    const dates = state.applicationDates.filter(Boolean).slice().sort();
    const dayCount = el("[data-window-24-count]");
    const dayDate = el("[data-window-24-date]");
    const weekCount = el("[data-window-7-count]");
    const weekTrend = el("[data-window-7-trend]");
    const weekDates = el("[data-window-7-dates]");
    if (!dayCount && !weekCount) return;
    if (!dates.length) {
      if (dayCount) dayCount.textContent = "—";
      if (dayDate) dayDate.textContent = "Application-date feed unavailable";
      if (weekCount) weekCount.textContent = "—";
      if (weekTrend) weekTrend.textContent = "Comparison unavailable";
      if (weekDates) weekDates.textContent = "No system time substituted";
      return;
    }
    const latestKey = dates[dates.length - 1];
    const latest = new Date(latestKey + "T12:00:00-04:00");
    function keyOffset(days) {
      const date = new Date(latest);
      date.setDate(date.getDate() + days);
      return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
    }
    const latestDayCount = dates.filter(function (date) { return date === latestKey; }).length;
    const currentStart = keyOffset(-6);
    const priorStart = keyOffset(-13);
    const priorEnd = keyOffset(-7);
    const currentTotal = dates.filter(function (date) { return date >= currentStart && date <= latestKey; }).length;
    const priorTotal = dates.filter(function (date) { return date >= priorStart && date <= priorEnd; }).length;
    let trend = "No prior-window comparison";
    if (priorTotal > 0) {
      const change = Math.round(((currentTotal - priorTotal) / priorTotal) * 100);
      trend = change === 0 ? "Flat" : (change > 0 ? "+" + formatNumber(change) + "%" : formatNumber(change) + "%");
    }
    if (dayCount) dayCount.textContent = formatNumber(latestDayCount);
    if (dayDate) dayDate.textContent = "Applied " + formatDate(latestKey, { month: "long", day: "numeric", year: "numeric", timeZone: "America/New_York" });
    if (weekCount) weekCount.textContent = formatNumber(currentTotal);
    if (weekTrend) weekTrend.textContent = trend;
    if (weekDates) weekDates.textContent = "Applied " + formatDate(currentStart, { month: "short", day: "numeric", timeZone: "America/New_York" }) + "–" + formatDate(latestKey, { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }) + " →";
  }

  function initDataFlipper() {
    const flipper = el(".data-flipper");
    if (!flipper) return;
    const panels = els("[data-flip-panel]", flipper);
    const diagramIndex = panels.findIndex(function (panel) { return panel.classList.contains("diagram-watch"); });
    if (diagramIndex > 1) panels.splice(1, 0, panels.splice(diagramIndex, 1)[0]);
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

  function initHeroSequence() {
    const sequence = el("[data-hero-sequence]");
    if (!sequence) return;
    const photos = els("[data-hero-photo]", sequence);
    const caption = el("[data-hero-caption]", sequence);
    const counter = el("[data-hero-photo-index]", sequence);
    const rails = els(".hero-sequence-rail i", sequence);
    if (photos.length < 2) return;
    let index = 0;
    let timer = null;
    function show(next) {
      index = (next + photos.length) % photos.length;
      photos.forEach(function (photo, photoIndex) { photo.classList.toggle("is-active", photoIndex === index); });
      rails.forEach(function (rail, railIndex) { rail.classList.toggle("is-active", railIndex === index); });
      if (caption) caption.textContent = photos[index].getAttribute("data-caption") || "Fort Lauderdale field view";
      if (counter) counter.textContent = String(index + 1).padStart(2, "0") + " / " + String(photos.length).padStart(2, "0");
    }
    function start() {
      window.clearInterval(timer);
      timer = window.setInterval(function () { if (!document.hidden) show(index + 1); }, 5200);
    }
    sequence.addEventListener("mouseenter", function () { window.clearInterval(timer); });
    sequence.addEventListener("mouseleave", start);
    sequence.addEventListener("focusin", function () { window.clearInterval(timer); });
    sequence.addEventListener("focusout", start);
    show(0);
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) start();
  }

  function initMobileLiveRail() {
    const viewport = el("[data-mobile-live-rail]");
    if (!viewport) return;
    const cards = els("[data-mobile-live-card]", viewport);
    const position = el("[data-mobile-live-position]");
    if (cards.length < 2) return;
    let index = 0;
    let pauseUntil = 0;
    let scrollFrame = 0;
    function updatePosition() {
      if (position) position.textContent = "Auto · " + (index + 1) + " / " + cards.length;
    }
    function syncIndex() {
      let nearest = 0;
      let distance = Infinity;
      cards.forEach(function (card, cardIndex) {
        const delta = Math.abs(card.offsetLeft - 14 - viewport.scrollLeft);
        if (delta < distance) { distance = delta; nearest = cardIndex; }
      });
      index = nearest;
      updatePosition();
    }
    function advance() {
      if (window.innerWidth > 620 || document.hidden || Date.now() < pauseUntil) return;
      index = (index + 1) % cards.length;
      viewport.scrollTo({ left: Math.max(0, cards[index].offsetLeft - 14), behavior: "smooth" });
      updatePosition();
    }
    viewport.addEventListener("pointerdown", function () { pauseUntil = Date.now() + 15000; });
    viewport.addEventListener("focusin", function () { pauseUntil = Date.now() + 15000; });
    viewport.addEventListener("scroll", function () {
      window.cancelAnimationFrame(scrollFrame);
      scrollFrame = window.requestAnimationFrame(syncIndex);
    }, { passive: true });
    updatePosition();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    window.setInterval(advance, 4600);
  }

  function initHomepagePriority() {
    const main = el("main#main");
    const signals = el("#signals", main);
    const intel = el(".intel-section", main);
    const map = el(".map-section", main);
    if (!main || !signals || !intel || !map) return;
    const mobile = window.matchMedia("(max-width: 620px)");
    function arrange() {
      if (mobile.matches) {
        if (map.previousElementSibling !== signals) main.insertBefore(map, signals.nextElementSibling);
      } else if (intel.previousElementSibling !== signals) {
        main.insertBefore(intel, signals.nextElementSibling);
      }
    }
    arrange();
    if (mobile.addEventListener) mobile.addEventListener("change", arrange);
    else mobile.addListener(arrange);
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
      return state.records.filter(function (record) {
        return Number.isFinite(Number(record.lat)) && Number.isFinite(Number(record.lon)) && (!document.body.classList.contains("storm-mode") || isStormRecord(record));
      });
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
        status.innerHTML = 'No point in the current mapped sample matches “' + escapeHtml(query) + '.” <a href="' + PUBLIC_ROUTES.neighborhoods + '?q=' + encodeURIComponent(query) + '">Open the full record search →</a>';
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

  function addCityInterests(form, formIndex) {
    if (el(".city-interests", form)) return;
    const preferences = document.createElement("details");
    preferences.className = "signup-preferences";
    preferences.innerHTML = '<summary><span>Personalize your brief</span><strong>Fort Lauderdale · All intel</strong></summary><div class="signup-preferences__body"></div>';
    const preferenceBody = el(".signup-preferences__body", preferences);
    const fieldset = document.createElement("fieldset");
    fieldset.className = "city-interests";
    fieldset.innerHTML = '<legend>City desks</legend><div class="city-interests__grid">' +
      BROWARD_CITIES.map(function (city, cityIndex) {
        const id = "city-interest-" + formIndex + "-" + cityIndex;
        return '<label for="' + id + '"><input id="' + id + '" name="cities" type="checkbox" value="' + escapeHtml(city[0]) + '"' + (city[0] === ACTIVE_CITY ? ' checked' : '') + '><span>' + escapeHtml(city[1]) + '</span></label>';
      }).join("") + '</div>';
    const message = el("[data-signup-message]", form);
    preferenceBody.appendChild(fieldset);
    const summary = el("summary strong", preferences);
    let selectedCityLabel = "Fort Lauderdale";
    let selectedInterestLabel = "All intel";
    function updatePreferenceSummary() { summary.textContent = selectedCityLabel + " · " + selectedInterestLabel; }
    function updateSummary() {
      const selected = els('input[name="cities"]:checked', fieldset).map(function (input) {
        const city = BROWARD_CITIES.find(function (entry) { return entry[0] === input.value; });
        return city ? city[1] : input.value;
      });
      selectedCityLabel = selected.length === 1 ? selected[0] : selected.length + " cities";
      updatePreferenceSummary();
    }
    fieldset.addEventListener("change", updateSummary);
    updateSummary();

    const interestSet = document.createElement("fieldset");
    interestSet.className = "brief-interests";
    interestSet.innerHTML = '<legend>Intelligence topics</legend><div class="brief-interests__grid">' +
      BRIEF_INTERESTS.map(function (interest, interestIndex) {
        const id = "brief-interest-" + formIndex + "-" + interestIndex;
        return '<label for="' + id + '"><input id="' + id + '" name="interests" type="checkbox" value="' + escapeHtml(interest[0]) + '" checked><span>' + escapeHtml(interest[1]) + '</span></label>';
      }).join("") + '</div>';
    preferenceBody.appendChild(interestSet);
    const note = document.createElement("p");
    note.textContent = "Fort Lauderdale is live. Other city choices record your interests—no coverage promises.";
    preferenceBody.appendChild(note);
    form.insertBefore(preferences, message || null);
    function updateInterestSummary() {
      const selected = els('input[name="interests"]:checked', interestSet);
      selectedInterestLabel = selected.length === BRIEF_INTERESTS.length ? "All intel" : selected.length ? selected.length + " topics" : "Choose topics";
      updatePreferenceSummary();
    }
    interestSet.addEventListener("change", updateInterestSummary);
    updateInterestSummary();
  }

  function initSignupForms() {
    els("[data-signup-form]").forEach(function (form, formIndex) {
      addCityInterests(form, formIndex);
      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        trackEvent("newsletter_submit", { placement: form.getAttribute("data-signup-source") || (form.classList.contains("signup--hero") ? "homepage-hero" : "homepage-brief") });
        const input = el('input[name="email"]', form);
        const zip = el('input[name="zip"]', form);
        const message = el("[data-signup-message]", form);
        if (!input || !zip || !message) return;
        const cities = els('input[name="cities"]:checked', form).map(function (checkbox) { return checkbox.value; });
        const interests = els('input[name="interests"]:checked', form).map(function (checkbox) { return checkbox.value; });
        if (!cities.length) {
          message.classList.add("is-error");
          message.textContent = "Choose at least one Broward city.";
          const selector = el(".signup-preferences", form);
          if (selector) selector.open = true;
          return;
        }
        message.classList.remove("is-error");
        message.textContent = "Saving your place…";
        try {
          const response = await fetch(apiUrl("/api/subscribe"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: input.value, zip: zip.value, cities: cities, interests: interests, source: form.getAttribute("data-signup-source") || (form.classList.contains("signup--hero") ? "homepage-hero" : "homepage-brief") })
          });
          const data = await response.json();
          if (!response.ok) throw new Error(data.error || "Could not save subscription");
          message.textContent = data.existing ? "You’re already on the list." : "You’re in. Watch for the 6:15 Brief.";
          trackEvent("newsletter_conversion", { placement: form.getAttribute("data-signup-source") || "website", status: data.existing ? "existing" : "created" });
          try { window.localStorage.setItem("florida-signal-brief-subscribed", String(Date.now())); } catch (storageError) { /* Storage is optional. */ }
          input.value = "";
          zip.value = "";
          els('input[name="cities"]', form).forEach(function (checkbox) { checkbox.checked = checkbox.value === ACTIVE_CITY; });
          els('input[name="interests"]', form).forEach(function (checkbox) { checkbox.checked = true; });
          const preferenceSummary = el(".signup-preferences summary strong", form);
          if (preferenceSummary) preferenceSummary.textContent = "Fort Lauderdale · All intel";
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
    prompt.innerHTML = '<div class="brief-prompt__backdrop" data-brief-prompt-close></div><section class="brief-prompt__dialog" role="dialog" aria-modal="true" aria-labelledby="brief-prompt-title" aria-describedby="brief-prompt-dek"><button class="brief-prompt__close" type="button" data-brief-prompt-close aria-label="Close Daily Intel Brief signup">×</button><div class="brief-prompt__mark" aria-hidden="true"><img src="/assets/emblem-2026.png" alt=""></div><p class="eyebrow"><span class="pulse" aria-hidden="true"></span>Tomorrow starts tonight</p><h2 id="brief-prompt-title">Get the 6:15 Daily Intel Brief.</h2><p id="brief-prompt-dek">One sharp Broward email: consequential filings, neighborhood movement, meetings, storm readiness and the records behind every claim.</p><form class="signup signup--prompt" data-signup-form data-signup-source="ten-second-prompt"><label class="sr-only" for="prompt-email">Email address</label><input id="prompt-email" name="email" type="email" autocomplete="email" placeholder="Your email address" required><label class="sr-only" for="prompt-zip">ZIP you watch</label><input id="prompt-zip" name="zip" inputmode="numeric" autocomplete="postal-code" pattern="[0-9]{5}(-[0-9]{4})?" placeholder="ZIP you watch" required><button type="submit">Send me the brief →</button><p class="signup__message" data-signup-message aria-live="polite"></p></form><p class="brief-prompt__fine">Free · Broward Audience · unsubscribe anytime · powered by Graham &amp; Gold LLC</p></section>';
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
    rail.innerHTML = '<div class="shell"><i class="site-sponsor-rail__signal" aria-hidden="true"><b></b><b></b><b></b><b></b></i><span>Presented intelligence · ' + escapeHtml(pageName) + '</span><strong>Put your brand beside the data people use.</strong><a href="mailto:desk@thefloridasignal.com?subject=' + encodeURIComponent("Florida Signal " + pageName + " sponsorship") + '">Sponsor this desk →</a></div>';
    footer.parentNode.insertBefore(rail, footer);
  }

  function initCrossPagePromo() {
    const page = document.body.getAttribute("data-page") || "home";
    if (page === "home" || el(".cross-page-promo")) return;
    const promos = {
      neighborhoods: { image: "/social/graphic-desk/place-lens.png", alt: "Florida Signal neighborhood and ZIP intelligence diagram", kicker: "From the field to the pattern", title: "See what the mapped filings add up to.", copy: "Live diagrams turn block-level records into neighborhood momentum.", label: "Open the Data Room", url: PUBLIC_ROUTES.graphics + "#place-lens", target: ".live-map-stage" },
      meetings: { image: "/assets/photos/fort-lauderdale-barrier-island-skyline-adobe-257427799.jpg", alt: "Fort Lauderdale skyline and waterways", kicker: "From agenda to address", title: "Take the meeting into the field.", copy: "Open cited properties, nearby filings and neighborhood context on the live map.", label: "Open the live map", url: PUBLIC_ROUTES.neighborhoods + "#full-map", target: ".meeting-board" },
      storm: { image: "/assets/photos/fort-lauderdale-construction-cranes-adobe-490952530.jpg", alt: "Tower cranes above Fort Lauderdale construction", kicker: "Beyond the weather window", title: "See the development pipeline still moving.", copy: "Switch from readiness records to the wider live permit and neighborhood map.", label: "Open the live map", url: PUBLIC_ROUTES.neighborhoods + "#full-map", target: ".storm-map-focus" },
      graphics: { image: "/assets/photos/fort-lauderdale-waterfront-neighborhoods-aerial-adobe-428926084.jpg", alt: "Aerial view of Fort Lauderdale waterfront neighborhoods", kicker: "Take the diagram outside", title: "Move from pattern to parcel.", copy: "Search the block, inspect the filing and cross-check Street View or satellite.", label: "Open field intelligence", url: PUBLIC_ROUTES.neighborhoods + "#full-map", target: ".graphic-desk-section" },
      broward: { image: "/assets/photos/las-olas-boulevard-street-scene-adobe-861811982.jpg", alt: "Las Olas Boulevard street scene", kicker: "The record enters the room", title: "Watch what is discussed before it moves.", copy: "Official meetings, agendas and source-cleared property intelligence.", label: "Open Meetings", url: PUBLIC_ROUTES.meetings, target: "main > section:nth-of-type(2)" },
      method: { image: "/social/graphic-desk/application-pulse.png", alt: "Florida Signal application-date pulse diagram", kicker: "See the method working", title: "Open the live diagrams.", copy: "Every visual carries its event window, update time and source note.", label: "Enter the Data Room", url: PUBLIC_ROUTES.graphics, target: "main > section:nth-of-type(2)" },
      stories: { image: "/assets/photos/fort-lauderdale-skyline-panorama-adobe-125666941.jpg", alt: "Fort Lauderdale skyline panorama", kicker: "Reporting meets reconnaissance", title: "Investigate the place behind the story.", copy: "Move from an approved brief to the cited map and public-record surface.", label: "Open the live map", url: PUBLIC_ROUTES.neighborhoods + "#full-map", target: "main > section:first-of-type" },
      "brand-kit": { image: "/social/graphic-desk/place-lens.png", alt: "Florida Signal branded Place Lens diagram", kicker: "The brand in motion", title: "See Florida Signal on live intelligence.", copy: "Embeddable diagrams and maps carry the source, window and emblem with them.", label: "Open the Data Room", url: PUBLIC_ROUTES.graphics, target: "main > section:first-of-type" }
    };
    const promo = promos[page];
    if (!promo) return;
    const section = document.createElement("aside");
    section.className = "cross-page-promo";
    section.setAttribute("data-signal-tags", "format:visual-promo city:fort-lauderdale county:broward-county");
    section.innerHTML = '<div class="shell cross-page-promo__grid"><a class="cross-page-promo__image" href="' + escapeHtml(promo.url) + '"><img src="' + escapeHtml(promo.image) + '" alt="' + escapeHtml(promo.alt) + '" loading="lazy"><span>Florida Signal · Live intelligence</span></a><div class="cross-page-promo__copy"><p>' + escapeHtml(promo.kicker) + '</p><h2>' + escapeHtml(promo.title) + '</h2><span>' + escapeHtml(promo.copy) + '</span><div><a href="' + escapeHtml(promo.url) + '">' + escapeHtml(promo.label) + ' →</a><button type="button" data-report-add data-report-id="promo:' + escapeHtml(page) + '" data-report-title="' + escapeHtml(promo.title) + '" data-report-meta="Florida Signal cross-desk intelligence" data-report-url="' + escapeHtml(promo.url) + '" data-report-tags="format:visual-promo city:fort-lauderdale county:broward-county">＋ Add to report</button></div></div></div>';
    const target = el(promo.target);
    if (target) target.insertAdjacentElement("afterend", section);
    else {
      const main = el("main");
      if (main) main.appendChild(section);
    }
  }

  async function initDataHealth() {
    const page = document.body.getAttribute("data-page") || "home";
    if (page !== "method" || el("#source-health")) return;
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
      const response = await fetch(apiUrl("/api/data-health"), { cache: "no-store", headers: { Accept: "application/json" } });
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
        const verification = source.verification ? '<span class="source-health__evidence source-health__evidence--' + escapeHtml(source.verification) + '">' + escapeHtml(source.verification) + '</span>' : '';
        return '<article><div><span class="source-health__status source-health__status--' + escapeHtml(source.status) + '">' + escapeHtml(source.status) + '</span><strong>' + escapeHtml(source.label) + '</strong>' + verification + '</div><p>' + escapeHtml(eventClock) + '</p><p>' + escapeHtml(systemClock) + '</p><small>' + escapeHtml(source.cadence || "") + ' · ' + escapeHtml(source.detail || "") + '</small></article>';
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
        const accepted = navigator.sendBeacon(apiUrl("/api/events"), new Blob([payload], { type: "application/json" }));
        if (accepted) return;
      }
      fetch(apiUrl("/api/events"), { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, keepalive: true }).catch(function () { /* Analytics are best-effort. */ });
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

  function currentCitySlug() {
    const explicit = document.body.getAttribute("data-city");
    if (explicit) return explicit;
    const first = window.location.pathname.split("/").filter(Boolean)[0];
    return BROWARD_CITIES.some(function (city) { return city[0] === first; }) ? first : ACTIVE_CITY;
  }

  function initCitySwitcher() {
    const header = el(".site-header__inner");
    if (!header || el(".city-switcher", header)) return;
    const current = currentCitySlug();
    const currentLabel = (BROWARD_CITIES.find(function (city) { return city[0] === current; }) || [ACTIVE_CITY, "Fort Lauderdale"])[1];
    const switcher = document.createElement("details");
    switcher.className = "city-switcher";
    switcher.innerHTML = '<summary aria-label="Choose a Broward city desk"><span>City desk</span><strong>' + escapeHtml(currentLabel) + '</strong><i aria-hidden="true"></i></summary>' +
      '<div class="city-switcher__panel"><div class="city-switcher__head"><span>Broward city desks</span><small>Launching city by city</small></div><div class="city-switcher__list">' +
      BROWARD_CITIES.map(function (city) {
        const live = city[0] === ACTIVE_CITY;
        const isCurrent = city[0] === current;
        return '<a href="/' + escapeHtml(city[0]) + '/"' + (isCurrent ? ' aria-current="page"' : '') + '><span>' + escapeHtml(city[1]) + '</span><small class="' + (live ? 'is-live' : '') + '">' + (live ? 'Live' : 'Coming soon') + '</small></a>';
      }).join("") + '</div><p>No dates. No coverage promises. A desk goes live only when its source chain is ready.</p></div>';
    const menu = el(".menu-button", header);
    header.insertBefore(switcher, menu || header.children[1] || null);
    document.addEventListener("click", function (event) {
      if (switcher.open && !switcher.contains(event.target)) switcher.open = false;
    });
    document.addEventListener("keydown", function (event) { if (event.key === "Escape" && switcher.open) { switcher.open = false; el("summary", switcher).focus(); } });
  }

  function initNavigation() {
    const button = el(".menu-button");
    if (!button) return;
    const navigation = el(".site-nav");
    if (navigation) {
      const page = document.body.getAttribute("data-page");
      const signalHref = page === "home" ? "#signals" : PUBLIC_ROUTES.home + "#signals";
      const items = [
        { href: PUBLIC_ROUTES.neighborhoods + "#full-map", label: "Live map", className: "nav-live-map", current: page === "neighborhoods" },
        { href: signalHref, label: "Signals", current: page === "home" },
        { href: PUBLIC_ROUTES.graphics, label: "Data room", current: page === "graphics" },
        { href: PUBLIC_ROUTES.meetings, label: "Meetings", current: page === "meetings" }
      ];
      navigation.innerHTML = items.map(function (item) {
        return '<a href="' + item.href + '"' + (item.className ? ' class="' + item.className + '"' : '') + (item.current ? ' aria-current="page"' : '') + '>' + item.label + '</a>';
      }).join("");
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
      '<div class="storm-operations__readout"><p>Official center fix</p><h2>' + escapeHtml(title) + '</h2><strong>' + escapeHtml(coordinates) + '</strong><span>' + escapeHtml(movement) + '</span><div><a href="' + escapeHtml(advisory) + '" target="_blank" rel="noopener">Public advisory ↗</a><a href="' + PUBLIC_ROUTES.storm + '">Open Storm Window →</a></div><small>Florida Signal adds local readiness records. It does not replace NHC, NWS or emergency management.</small></div></div>';
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
      status.innerHTML = '<span class="storm-mode-toggle__icon" aria-hidden="true">&#127744;</span><span>Storm watch ' + (active ? "active" : "standby") + '</span>';
      status.title = "Publisher-controlled site state" + (mode && mode.updated_at ? " · updated " + mode.updated_at : "");
    }
    const themeColor = el('meta[name="theme-color"]');
    if (themeColor) themeColor.setAttribute("content", active ? "#8f1118" : "#ffffff");
    if (active && document.body.dataset.stormAnalyticsSent !== "yes") {
      document.body.dataset.stormAnalyticsSent = "yes";
      trackEvent("storm_watch_view", { mode: "publisher-controlled" });
    }
    applyMapLens(active ? "storm" : "all", { fit: active });
    const mapSidebar = el(".full-map-sidebar");
    if (mapSidebar) {
      let notice = el(".storm-map-notice", mapSidebar);
      if (active && !notice) {
        notice = document.createElement("p");
        notice.className = "storm-map-notice";
        const lensSwitch = el(".lens-switch", mapSidebar);
        notice.innerHTML = '<strong>Storm lens active</strong><span>Showing hardening and recovery-type permit applications by application date. These records do not prove storm cause or damage.</span>';
        if (lensSwitch) mapSidebar.insertBefore(notice, lensSwitch);
      }
      if (notice) notice.hidden = !active;
    }
    renderStormOperations(state.stormPayload);
  }

  function initStormMode() {
    const bar = el(".live-bar__inner");
    if (!bar) return;
    const status = document.createElement("a");
    status.className = "storm-mode-toggle";
    status.id = "storm-mode-status";
    status.href = PUBLIC_ROUTES.storm;
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
        let response = await fetch(apiUrl("/api/site-mode"), { cache: "no-store" });
        if (!response.ok) response = await fetch("/data/site_mode.json", { cache: "no-store" });
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

  function easternParts(date) {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York", year: "numeric", month: "numeric", day: "numeric",
      hour: "numeric", minute: "numeric", second: "numeric", hourCycle: "h23"
    }).formatToParts(date).reduce(function (parts, part) {
      if (part.type !== "literal") parts[part.type] = Number(part.value);
      return parts;
    }, {});
  }

  function easternOffsetMs(date) {
    const parts = easternParts(date);
    return Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second) - date.getTime();
  }

  function nextEasternDaily(now, hour, minute) {
    const current = easternParts(now);
    function makeTarget(dayOffset) {
      const daySeed = new Date(Date.UTC(current.year, current.month - 1, current.day + dayOffset, 12));
      const day = easternParts(daySeed);
      let guess = Date.UTC(day.year, day.month - 1, day.day, hour, minute, 0);
      guess -= easternOffsetMs(new Date(guess));
      return new Date(guess);
    }
    let target = makeTarget(0);
    if (target <= now) target = makeTarget(1);
    return target;
  }

  function initDataCountdown() {
    const time = el("#live-bar-time");
    const lead = el(".live-bar__inner p:first-child");
    const label = lead ? el("strong", lead) : null;
    if (!time || !lead || !label) return;
    const mobile = document.createElement("span");
    mobile.className = "live-bar__countdown-mobile";
    lead.appendChild(mobile);
    if (!el(".live-bar__processing", lead)) lead.insertAdjacentHTML("beforeend", '<span class="live-bar__processing" aria-label="Feeds processing"><i></i><i></i><i></i></span>');
    label.textContent = "Newest signals";
    label.dataset.defaultLabel = "Newest signals";

    function clock(ms) {
      const total = Math.max(0, Math.floor(ms / 1000));
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      const seconds = total % 60;
      return [hours, minutes, seconds].map(function (value) { return String(value).padStart(2, "0"); }).join(":");
    }
    function render() {
      if (document.body.classList.contains("storm-mode")) { mobile.textContent = ""; return; }
      const now = new Date();
      const jobs = [
        { label: "Permits", target: nextEasternDaily(now, 22, 0) },
        { label: "Sunbiz", target: nextEasternDaily(now, 23, 30) }
      ].sort(function (a, b) { return a.target - b.target; });
      const job = jobs[0];
      const remaining = clock(job.target - now);
      time.textContent = "NEXT PULL · " + job.label.toUpperCase() + " · " + remaining;
      time.title = job.label + " scheduled for " + job.target.toLocaleString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
      mobile.textContent = "NEXT " + job.label.toUpperCase() + " · " + remaining;
    }
    render();
    window.setInterval(render, 1000);
  }

  function initMapPublishing() {
    const share = el("[data-share-map]");
    const embed = el("[data-copy-map-embed]");
    if (!share && !embed) return;
    const url = window.location.origin + PUBLIC_ROUTES.neighborhoods + "#full-map";
    const embedUrl = window.location.origin + PUBLIC_ROUTES.neighborhoods + "?embed=map#full-map";
    const embedCode = '<iframe src="' + embedUrl + '" width="100%" height="720" loading="lazy" title="Florida Signal live Broward field map"></iframe>';
    if (new URLSearchParams(window.location.search).get("embed") === "map") document.body.classList.add("map-embed");
    if (share) share.addEventListener("click", async function () {
      if (navigator.share) {
        try { await navigator.share({ title: "Florida Signal live Broward field map", url: url }); return; } catch (error) { if (error && error.name === "AbortError") return; }
      }
      try { await navigator.clipboard.writeText(url); share.textContent = "Link copied"; } catch (error) { window.prompt("Copy this map link", url); }
      window.setTimeout(function () { share.textContent = "Share"; }, 1800);
    });
    if (embed) embed.addEventListener("click", async function () {
      try { await navigator.clipboard.writeText(embedCode); embed.textContent = "Embed copied"; } catch (error) { window.prompt("Copy this embed code", embedCode); }
      window.setTimeout(function () { embed.innerHTML = "&lt;/&gt; Embed"; }, 1800);
    });
  }

  function initPublishingSurfaces() {
    function absolute(path) { return window.location.origin + path; }
    const graphicsEmbed = function (slug) { return absolute(PUBLIC_ROUTES.graphics + "?embed=" + encodeURIComponent(slug)); };
    const surfaces = [
      { selector: "#signal-spotlight-map", title: "Florida Signal · Newest signals map", url: absolute(PUBLIC_ROUTES.home + "#signals"), overlay: true },
      { selector: "#mobile-field-map", title: "Florida Signal · Live field map", url: absolute(PUBLIC_ROUTES.neighborhoods + "#full-map"), map: true },
      { selector: "#activity-chart", title: "Florida Signal · Application Pulse", url: absolute(CITY_ROOT + "/share/application-pulse.html"), embed: graphicsEmbed("application-pulse") },
      { selector: "#value-bars", title: "Florida Signal · Value Ladder", url: absolute(CITY_ROOT + "/share/value-universe.html"), embed: graphicsEmbed("value-universe") },
      { selector: "#operator-list", title: "Florida Signal · Operator Board", url: absolute(CITY_ROOT + "/share/operator-board.html"), embed: graphicsEmbed("operator-board") },
      { selector: "#home-map", title: "Florida Signal · Live Broward field map", url: absolute(PUBLIC_ROUTES.neighborhoods + "#full-map"), embed: absolute(PUBLIC_ROUTES.neighborhoods + "?embed=map#full-map"), map: true },
      { selector: "#data-room-map", title: "Florida Signal · Live Broward field map", url: absolute(PUBLIC_ROUTES.neighborhoods + "#full-map"), embed: absolute(PUBLIC_ROUTES.neighborhoods + "?embed=map#full-map"), map: true },
      { selector: ".method-flow", title: "Florida Signal · Public-record methodology", url: absolute(PUBLIC_ROUTES.method + "#method-flow") },
      { selector: "#meeting-spotlight-map", title: "Florida Signal · Rooms Watched map", url: absolute(PUBLIC_ROUTES.meetings + "#meeting-board"), overlay: true },
      { selector: "#agenda-recon-map", title: "Florida Signal · Agenda Recon map", url: absolute(PUBLIC_ROUTES.meetings + "#agenda-recon-title"), map: true },
      { selector: ".recon-process ol", title: "Florida Signal · Agenda Recon clearance chain", url: absolute(PUBLIC_ROUTES.meetings + "#agenda-recon-title") },
      { selector: ".storm-page-card img", title: "Florida Signal · Storm Window", url: absolute(CITY_ROOT + "/share/storm-window.html"), embed: graphicsEmbed("storm-window") },
      { selector: ".storm-phases", title: "Florida Signal · Storm operating picture", url: absolute(PUBLIC_ROUTES.storm + "#storm-operating-picture") },
      { selector: "#storm-spotlight-map", title: "Florida Signal · Storm Readiness map", url: absolute(PUBLIC_ROUTES.storm + "#storm-readiness"), overlay: true }
    ];

    function railFor(settings) {
      const rail = document.createElement("div");
      rail.className = "surface-publish" + (settings.overlay ? " surface-publish--overlay" : "") + (settings.compact ? " surface-publish--compact" : "");
      rail.setAttribute("aria-label", "Share " + settings.title);
      const embedCode = settings.embed ? '<iframe src="' + settings.embed + '" width="100%" height="720" loading="lazy" title="' + settings.title + '"></iframe>' : "";
      const compactTools = settings.map || settings.overlay;
      rail.innerHTML = '<span>Share this intelligence</span>' +
        '<a class="publish-social publish-social--x" data-network="X" href="https://twitter.com/intent/tweet?text=' + encodeURIComponent(settings.title) + '&url=' + encodeURIComponent(settings.url) + '" target="_blank" rel="noreferrer" aria-label="Share on X">X</a>' +
        '<a class="publish-social publish-social--linkedin" data-network="LinkedIn" href="https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(settings.url) + '" target="_blank" rel="noreferrer" aria-label="Share on LinkedIn">in</a>' +
        '<a class="publish-social publish-social--facebook" data-network="Facebook" href="https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(settings.url) + '" target="_blank" rel="noreferrer" aria-label="Share on Facebook">f</a>' +
        '<button type="button" data-surface-share aria-label="Share this visual" title="Share">' + (compactTools ? '↗' : 'Share') + '</button>' +
        (embedCode ? '<button type="button" data-surface-embed aria-label="Copy embed code" title="Embed">' + (compactTools ? '&lt;/&gt;' : '&lt;/&gt; Embed') + '</button>' : '') +
        '<button type="button" class="surface-report" data-report-add data-report-id="surface:' + escapeHtml(settings.url) + '" data-report-title="' + escapeHtml(settings.title) + '" data-report-meta="Florida Signal map or diagram · source window shown on the visual" data-report-url="' + escapeHtml(settings.url) + '" data-report-tags="format:visual city:fort-lauderdale county:broward-county" aria-label="Add to Field Brief" title="Add to Field Brief">' + (compactTools ? '＋' : '＋ Report') + '</button>';
      const share = el("[data-surface-share]", rail);
      const copy = el("[data-surface-copy]", rail);
      const embed = el("[data-surface-embed]", rail);
      share.addEventListener("click", async function () {
        if (navigator.share) {
          try { await navigator.share({ title: settings.title, url: settings.url }); return; }
          catch (error) { if (error && error.name === "AbortError") return; }
        }
        try { await navigator.clipboard.writeText(settings.url); share.textContent = "Copied"; }
        catch (error) { window.prompt("Copy this Florida Signal link", settings.url); }
        window.setTimeout(function () { share.textContent = compactTools ? "↗" : "Share"; }, 1800);
      });
      if (copy) copy.addEventListener("click", async function () {
        try { await navigator.clipboard.writeText(settings.url); copy.textContent = "Copied"; }
        catch (error) { window.prompt("Copy this Florida Signal link", settings.url); }
        window.setTimeout(function () { copy.textContent = "Copy link"; }, 1800);
      });
      if (embed) embed.addEventListener("click", async function () {
        try { await navigator.clipboard.writeText(embedCode); embed.textContent = "Embed copied"; }
        catch (error) { window.prompt("Copy this embed code", embedCode); }
        window.setTimeout(function () { embed.innerHTML = "&lt;/&gt; Embed"; }, 1800);
      });
      return rail;
    }

    surfaces.forEach(function (settings) {
      const target = el(settings.selector);
      if (!target || target.dataset.publishReady === "true") return;
      target.dataset.publishReady = "true";
      const rail = railFor(settings);
      if (settings.overlay) target.appendChild(rail);
      else if (settings.map && target.parentNode) {
        const frame = document.createElement("div");
        frame.className = "surface-map-frame";
        target.parentNode.insertBefore(frame, target);
        frame.appendChild(target);
        rail.classList.add("surface-publish--map");
        frame.appendChild(rail);
      } else target.insertAdjacentElement("afterend", rail);
    });
  }

  function initFieldBrief() {
    let items = [];
    try {
      const stored = JSON.parse(window.localStorage.getItem(FIELD_BRIEF_STORAGE_KEY) || "[]");
      if (Array.isArray(stored)) items = stored.slice(0, 50);
    } catch (error) { items = []; }

    const launcher = document.createElement("button");
    launcher.className = "field-brief-launcher";
    launcher.type = "button";
    launcher.setAttribute("data-field-brief-open", "");
    launcher.setAttribute("aria-label", "Open your Florida Signal Field Brief");
    launcher.title = "Open your collected Florida Signal report";
    launcher.innerHTML = '<svg class="field-brief-launcher__icon" viewBox="0 0 32 32" aria-hidden="true"><path d="M8.5 6.5h12l3 3v16h-15z"></path><path d="M20.5 6.5v4h4"></path><path d="M12 15h8M12 19h5"></path><path class="field-brief-launcher__plus" d="M23.5 18.5v9M19 23h9"></path></svg><span><small>Your report</small><strong>Field Brief</strong></span><b data-field-brief-count>0</b>';

    const drawer = document.createElement("section");
    drawer.className = "field-brief-drawer";
    drawer.hidden = true;
    drawer.setAttribute("aria-label", "Florida Signal Field Brief builder");
    drawer.innerHTML = '<button class="field-brief-drawer__backdrop" type="button" data-field-brief-close aria-label="Close Field Brief"></button><div class="field-brief-drawer__panel"><header><div><p>Florida Signal · field intelligence</p><h2>Build your report.</h2><span>Collect permits, meetings, maps and diagrams. Every item keeps its source link and place tags.</span></div><button type="button" data-field-brief-close aria-label="Close Field Brief">×</button></header><div class="field-brief-list" data-field-brief-list></div><footer><button type="button" data-field-brief-share>Send / Notes</button><button type="button" data-field-brief-copy>Copy report</button><button type="button" data-field-brief-print>Print / PDF</button><button type="button" data-field-brief-clear>Clear</button><p data-field-brief-status aria-live="polite"></p></footer></div>';
    document.body.appendChild(launcher);
    document.body.appendChild(drawer);

    const list = el("[data-field-brief-list]", drawer);
    const status = el("[data-field-brief-status]", drawer);
    const count = el("[data-field-brief-count]", launcher);

    function persist() {
      try { window.localStorage.setItem(FIELD_BRIEF_STORAGE_KEY, JSON.stringify(items)); } catch (error) { /* Browser storage may be disabled. */ }
    }

    function reportText() {
      const lines = ["FLORIDA SIGNAL — FIELD BRIEF", "Fort Lauderdale · Broward County", "Assembled " + new Date().toLocaleString("en-US", { timeZone: "America/New_York" }) + " ET", ""];
      items.forEach(function (item, index) {
        lines.push((index + 1) + ". " + item.title, item.meta || "", item.url || "", item.tags ? "Tags: " + item.tags.replace(/\s+/g, ", ") : "", "");
      });
      lines.push("Florida Signal · Development intelligence · Powered by Graham & Gold LLC");
      return lines.join("\n");
    }

    function render() {
      count.textContent = String(items.length);
      launcher.classList.toggle("has-items", items.length > 0);
      list.innerHTML = items.length ? items.map(function (item, index) {
        return '<article><span>' + String(index + 1).padStart(2, "0") + '</span><div><h3>' + escapeHtml(item.title) + '</h3><p>' + escapeHtml(item.meta || "Saved Florida Signal intelligence") + '</p><a href="' + escapeHtml(item.url || window.location.href) + '" target="_blank" rel="noreferrer">Open evidence ↗</a></div><button type="button" data-field-brief-remove="' + escapeHtml(item.id) + '" aria-label="Remove ' + escapeHtml(item.title) + '">×</button></article>';
      }).join("") : '<div class="field-brief-empty"><img src="/assets/mark-navy-mono.png" alt=""><h3>Your field report starts here.</h3><p>Use <strong>Add to report</strong> on any permit, meeting, map, diagram or story. Nothing is sent until you choose.</p></div>';
      els("[data-report-add]").forEach(function (button) {
        const id = button.getAttribute("data-report-id") || button.getAttribute("data-report-url");
        button.classList.toggle("is-saved", items.some(function (item) { return item.id === id; }));
      });
    }

    function openDrawer() { drawer.hidden = false; document.body.classList.add("field-brief-open"); render(); }
    function closeDrawer() { drawer.hidden = true; document.body.classList.remove("field-brief-open"); }

    document.addEventListener("click", async function (event) {
      const add = event.target.closest("[data-report-add]");
      if (add) {
        event.preventDefault();
        event.stopPropagation();
        const id = add.getAttribute("data-report-id") || add.getAttribute("data-report-url") || window.location.href;
        if (!items.some(function (item) { return item.id === id; })) {
          items.unshift({ id: id, title: add.getAttribute("data-report-title") || "Florida Signal intelligence", meta: add.getAttribute("data-report-meta") || "", url: add.getAttribute("data-report-url") || window.location.href, tags: add.getAttribute("data-report-tags") || "", saved_at: new Date().toISOString() });
          items = items.slice(0, 50);
          persist();
          trackEvent("field_brief_add", { item_id: id });
        }
        add.classList.add("is-saved");
        launcher.classList.add("field-brief-launcher--pulse");
        window.setTimeout(function () { launcher.classList.remove("field-brief-launcher--pulse"); }, 700);
        render();
        return;
      }
      const popupShare = event.target.closest("[data-popup-share]");
      if (popupShare) {
        const url = popupShare.getAttribute("data-share-url") || window.location.href;
        const title = popupShare.getAttribute("data-share-title") || "Florida Signal filing";
        if (navigator.share) {
          try { await navigator.share({ title: title, url: url }); return; } catch (error) { if (error && error.name === "AbortError") return; }
        }
        try { await navigator.clipboard.writeText(url); popupShare.textContent = "Copied"; } catch (error) { window.prompt("Copy this filing", url); }
        return;
      }
      if (event.target.closest("[data-field-brief-open]")) { openDrawer(); return; }
      if (event.target.closest("[data-field-brief-close]")) { closeDrawer(); return; }
      const remove = event.target.closest("[data-field-brief-remove]");
      if (remove) { items = items.filter(function (item) { return item.id !== remove.getAttribute("data-field-brief-remove"); }); persist(); render(); return; }
      if (event.target.closest("[data-field-brief-clear]")) { items = []; persist(); render(); status.textContent = "Field Brief cleared."; return; }
      if (event.target.closest("[data-field-brief-copy]")) {
        try { await navigator.clipboard.writeText(reportText()); status.textContent = "Report copied with links."; }
        catch (error) { window.prompt("Copy your Florida Signal Field Brief", reportText()); }
        return;
      }
      if (event.target.closest("[data-field-brief-share]")) {
        if (!items.length) { status.textContent = "Add at least one item first."; return; }
        if (navigator.share) {
          try { await navigator.share({ title: "Florida Signal Field Brief", text: reportText(), url: window.location.origin + PUBLIC_ROUTES.home }); status.textContent = "Share sheet opened."; return; }
          catch (error) { if (error && error.name === "AbortError") return; }
        }
        try { await navigator.clipboard.writeText(reportText()); status.textContent = "Report copied—paste it into Notes or a message."; }
        catch (error) { window.prompt("Copy your Florida Signal Field Brief", reportText()); }
        return;
      }
      if (event.target.closest("[data-field-brief-print]")) {
        if (!items.length) { status.textContent = "Add at least one item first."; return; }
        const printWindow = window.open("", "_blank");
        if (!printWindow) { status.textContent = "Allow pop-ups to print this report."; return; }
        const rows = items.map(function (item, index) { return '<article><span>' + String(index + 1).padStart(2, "0") + '</span><div><h2>' + escapeHtml(item.title) + '</h2><p>' + escapeHtml(item.meta || "") + '</p><a href="' + escapeHtml(item.url || "") + '">' + escapeHtml(item.url || "") + '</a><small>' + escapeHtml((item.tags || "").replace(/\s+/g, " · ")) + '</small></div></article>'; }).join("");
        printWindow.document.write('<!doctype html><html><head><meta charset="utf-8"><title>Florida Signal Field Brief</title><style>*{box-sizing:border-box}body{margin:38px;color:#071b32;font:14px Arial,sans-serif}header{position:relative;padding:24px 0;border-top:8px solid #00a596;border-bottom:1px solid #cbd8dc}header:after{content:"";position:absolute;right:10px;top:5px;width:120px;height:140px;background:url("' + window.location.origin + '/assets/emblem-2026.png") center/contain no-repeat;opacity:.1}header img{width:330px}header p{margin:8px 0 0;color:#63788b;text-transform:uppercase;letter-spacing:.12em;font-size:10px}main{margin-top:24px}article{display:grid;grid-template-columns:38px 1fr;gap:12px;padding:16px 0;border-bottom:1px solid #d8e1e4;break-inside:avoid}article>span{color:#009f91;font-weight:700}h2{margin:0 0 5px;font:24px Georgia,serif}p{margin:0 0 7px;color:#52697c}a{color:#007c72;font-size:10px;overflow-wrap:anywhere}small{display:block;margin-top:7px;color:#8797a3;font-size:8px;text-transform:uppercase}footer{margin-top:30px;padding-top:12px;border-top:2px solid #071b32;font-size:9px;color:#63788b}@media print{body{margin:12mm}}</style></head><body><header><img src="' + window.location.origin + '/assets/lockup-2026-v2.png" alt="Florida Signal"><p>Field Brief · ' + escapeHtml(new Date().toLocaleString("en-US", { timeZone: "America/New_York" })) + ' ET · ' + items.length + ' saved item' + (items.length === 1 ? '' : 's') + '</p></header><main>' + rows + '</main><footer>Florida Signal · Development Intelligence · Powered by Graham &amp; Gold LLC · Every item links to its cited public-record surface.</footer></body></html>');
        printWindow.document.close();
        printWindow.focus();
        window.setTimeout(function () { printWindow.print(); }, 500);
      }
    });

    render();
  }

  function init() {
    els("[data-year]").forEach(function (node) { node.textContent = String(new Date().getFullYear()); });
    initAnalytics();
    initTaxonomyDefaults();
    initStormMode();
    initDataCountdown();
    initMapPublishing();
    initPublishingSurfaces();
    initFieldBrief();
    initDataHealth();
    initMethodologyToggle();
    initCitySwitcher();
    initNavigation();
    initBriefPrompt();
    initSignupForms();
    initCrossPagePromo();
    initSponsorInventory();
    initHeroSequence();
    initDataFlipper();
    (function applyDiagramOfDay() {
      var picks = [
        { slug: "place-lens", title: "Neighborhood + ZIP Place Lens", img: "place-lens" },
        { slug: "application-pulse", title: "Application Pulse \u00b7 14-day window", img: "application-pulse" },
        { slug: "trades-pulse", title: "Live Work Mix \u00b7 what\u2019s being built", img: "trades-pulse" },
        { slug: "value-universe", title: "Value Universe \u00b7 declared dollars", img: "value-universe" },
        { slug: "operator-board", title: "Operator Board \u00b7 who\u2019s filing", img: "operator-board" },
        { slug: "records-desk", title: "Records Desk \u00b7 Broward instruments", img: "records-desk" },
        { slug: "high-value", title: "High-Value Queue \u00b7 $100K+", img: "high-value" }
      ];
      var now = new Date();
      var start = Date.UTC(now.getUTCFullYear(), 0, 0);
      var day = Math.floor((Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - start) / 86400000);
      var pick = picks[day % picks.length];
      els("[data-dod-link]").forEach(function (a) { a.href = "/fort-lauderdale/graphics/#" + pick.slug; });
      els("[data-dod-title]").forEach(function (t) { t.textContent = pick.title; });
      els("[data-dod-img]").forEach(function (i) { i.src = "/social/graphic-desk/" + pick.img + ".png"; i.alt = "Florida Signal diagram of the day: " + pick.title; });
    })();
    initLockups();
    initMobileLiveRail();
    initHomepagePriority();
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
