/*!
 * Florida Signal — SignalV1
 * Source-neutral Signal model + adapters + eligibility + intelligence + bounded read-only service.
 * Consumed by: Live Signals Map, Signal Cards, Data Desk, editorial review queue.
 *
 * RULES ENFORCED HERE
 *  - Event dates over pull dates. Never present a fetch time as a record date.
 *  - No source, no claim. Every Signal keeps source_name + source_record_id (+ url when the source offers one).
 *  - Preliminary != verified. PRELIMINARY renders only with a visible badge.
 *  - Conflicting values are preserved and flagged (CONFLICT), never silently merged, never public.
 *  - Deterministic facts only. Prose is a presentation layer over evidence that already exists in the record.
 *  - A filing is a filing; an application is an application. Never imply construction, damage, or intent.
 */
(function (global) {
  "use strict";

  var SIGNAL_VERSION = "SignalV1";

  var STATUS = { PRELIMINARY: "PRELIMINARY", VERIFIED: "VERIFIED", CONFLICT: "CONFLICT", NEEDS_REVIEW: "NEEDS_REVIEW" };
  var REVIEW = { NEW: "NEW", REVIEWING: "REVIEWING", HOLD: "HOLD", APPROVED: "APPROVED", REJECTED: "REJECTED", NEEDS_MORE_REPORTING: "NEEDS_MORE_REPORTING" };

  // Map layers. These are PRODUCT layers, not a claim that each is a separate source system.
  var LAYER = {
    DEVELOPMENT: "development",
    HIGH_VALUE: "high-value",
    DEMOLITION: "demolition",
    STORM: "storm",
    FAA: "faa",
    ENVIRONMENTAL: "environmental",
    DEED: "deed",
    EASEMENT: "easement"
  };

  var LAYER_LABEL = {
    "development": "Development",
    "high-value": "High-value activity",
    "demolition": "Demolition",
    "storm": "Storm",
    "faa": "FAA / Cranes",
    "environmental": "Environmental",
    "deed": "Property transfers",
    "easement": "Easements"
  };

  var LAYER_COLOR = {
    "development": "#00b8dc",
    "high-value": "#071b32",
    "demolition": "#ff6d3a",
    "storm": "#1767ff",
    "faa": "#7d3cc4",
    "environmental": "#0f9d76",
    "deed": "#b8860b",
    "easement": "#8a6d1f"
  };

  // Primary map categories, organised around what a user is trying to find rather than which
  // agency published the record. A family with no connected source is declared "planned" so the
  // map never presents an empty category as though it were fully covered.
  var SOURCE_FAMILIES = [
    { key: "development",     label: "Development",    layers: ["development", "high-value", "demolition", "storm"], status: "live" },
    { key: "property-money",  label: "Property & Money", layers: ["deed", "easement"], status: "live" },
    { key: "environment",     label: "Environment",    layers: ["environmental"], status: "live" },
    { key: "skyline",         label: "Skyline",        layers: ["faa"], status: "live" },
    { key: "government",      label: "Government",     layers: [], status: "planned",
      note: "Meeting agendas and municipal actions are not connected yet." },
    { key: "risk-legal",      label: "Risk & Legal",   layers: [], status: "planned",
      note: "Mortgages, liens, lis pendens and judgments are not map-eligible: the Clerk's public files carry no parcel identifier for them." }
  ];

  var BROWARD_BOX = { minLat: 25.90, maxLat: 26.45, minLon: -80.60, maxLon: -80.02 };

  // ---------- helpers (deterministic; no invention) ----------
  // NOTE: Number(null) === 0 and Number("") === 0, which would turn a missing coordinate into a
  // real point at 0,0. Treat null/undefined/blank as absent so eligibility reports it honestly.
  function num(v) {
    if (v === null || v === undefined || v === "") return null;
    var n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  function txt(v) { return v == null ? "" : String(v).trim(); }
  function isoDate(v) { var s = txt(v); return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : null; }
  // Compass directions and unit markers stay uppercase — "401 SW 1 Ave", never "401 Sw 1 Ave".
  var KEEP_UPPER = { N: 1, S: 1, E: 1, W: 1, NE: 1, NW: 1, SE: 1, SW: 1, US: 1, SR: 1, LLC: 1, LP: 1, LLP: 1, INC: 1, PA: 1, NA: 1, II: 1, III: 1, IV: 1 };
  function titleish(s) {
    return txt(s).toLowerCase().replace(/\s+/g, " ")
      .replace(/\b[a-z]/g, function (c) { return c.toUpperCase(); })
      .replace(/\b[A-Za-z]{1,3}\b/g, function (w) {
        return KEEP_UPPER[w.toUpperCase()] ? w.toUpperCase() : w;
      });
  }
  function money(n) {
    var v = num(n);
    if (v == null || v <= 0) return null;
    if (v >= 1000000) return "$" + (v / 1000000).toFixed(v >= 10000000 ? 0 : 1).replace(/\.0$/, "") + " million";
    if (v >= 1000) return "$" + Math.round(v / 1000) + ",000";
    return "$" + v.toLocaleString();
  }
  function inBroward(lat, lon) {
    return lat != null && lon != null &&
      lat >= BROWARD_BOX.minLat && lat <= BROWARD_BOX.maxLat &&
      lon >= BROWARD_BOX.minLon && lon <= BROWARD_BOX.maxLon;
  }
  function fmtDate(iso) {
    if (!iso) return null;
    var p = String(iso).slice(0, 10).split("-");
    if (p.length !== 3) return null;
    var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return months[Number(p[1]) - 1] + " " + Number(p[2]) + ", " + p[0];
  }

  var STORM_RE = /(roof|shutter|window|impact|generator|seawall|sea wall|drainage|storm|hurricane|flood|elevat)/i;
  var DEMO_RE = /\b(demo|demolition|demolish)\b/i;

  // ---------- SignalV1 factory ----------
  function makeSignal(base) {
    var conflicts = base.conflicts || [];
    var status = base.verification_status || STATUS.PRELIMINARY;
    if (conflicts.length) status = STATUS.CONFLICT;
    return {
      // IDENTITY
      signal_id: base.signal_id,
      signal_version: SIGNAL_VERSION,
      source_name: base.source_name,
      source_record_id: base.source_record_id,
      source_record_url: base.source_record_url || null,
      source_table: base.source_table,
      source_record_date: base.source_record_date || null,
      first_detected_at: base.first_detected_at || null,
      last_seen_at: base.last_seen_at || null,
      // CLASSIFICATION
      signal_type: base.signal_type,
      signal_subtype: base.signal_subtype || null,
      category: base.category,
      public_label: base.public_label,
      verification_status: status,
      confidence: base.confidence == null ? 0.5 : base.confidence,
      editorial_priority: base.editorial_priority == null ? 0 : base.editorial_priority,
      public_eligibility: false,      // set by applyEligibility()
      review_status: REVIEW.NEW,
      // LOCATION
      latitude: base.latitude,
      longitude: base.longitude,
      address: base.address || null,
      municipality: base.municipality || null,
      neighborhood: base.neighborhood || null,
      verified_parcel_id: base.verified_parcel_id || null,
      geographic_precision: base.geographic_precision || "unknown",
      location_source: base.location_source || null,
      // PROJECT CONTEXT
      project_name: base.project_name || null,
      owner_or_applicant: base.owner_or_applicant || null,
      contractor_or_sponsor: base.contractor_or_sponsor || null,
      valuation_or_amount: base.valuation_or_amount == null ? null : base.valuation_or_amount,
      project_scale: base.project_scale || null,
      related_record_count: base.related_record_count == null ? 0 : base.related_record_count,
      related_signal_ids: base.related_signal_ids || [],
      related_source_records: base.related_source_records || [],
      // EDITORIAL CONTENT (filled by intelligence pass)
      headline: base.headline || null,
      summary: base.summary || null,
      what_happened: base.what_happened || null,
      why_it_matters: base.why_it_matters || null,
      what_changed: base.what_changed || null,
      what_to_watch: base.what_to_watch || null,
      caveat: base.caveat || null,
      what_it_does_not_prove: base.what_it_does_not_prove || null,
      evidence_summary: base.evidence_summary || null,
      source_attribution: base.source_attribution || null,
      // STATE
      conflicts: conflicts,
      exclusion_reasons: [],
      layer: base.layer
    };
  }

  // ---------- PERMIT ADAPTER ----------
  // Only meaningful activity becomes a Signal: $500k+, demolition, storm-related work.
  // Routine minor permits are intentionally excluded (documented in exclusion_reasons).
  function fromPermit(r) {
    var lat = num(r.lat), lon = num(r.lon);
    var value = num(r.valuation_usd_clean);
    var text = [r.permit_type, r.description, r.work_type].join(" ");
    var isDemo = DEMO_RE.test(text);
    var isStorm = STORM_RE.test(text);
    var isHighValue = value != null && value >= 500000;

    var layer = LAYER.DEVELOPMENT, subtype = "application";
    if (isDemo) { layer = LAYER.DEMOLITION; subtype = "demolition"; }
    else if (isStorm) { layer = LAYER.STORM; subtype = "storm-related"; }
    else if (isHighValue) { layer = LAYER.HIGH_VALUE; subtype = "high-value"; }

    var meaningful = isDemo || isStorm || isHighValue;
    var recordDate = isoDate(r.applied_date);

    var s = makeSignal({
      signal_id: "permit:" + txt(r.permit_number),
      source_name: "City of Fort Lauderdale permits (Accela)",
      source_record_id: txt(r.permit_number),
      source_table: "permits",
      source_record_date: recordDate,
      first_detected_at: isoDate(r.last_seen_at) || recordDate,
      last_seen_at: isoDate(r.last_seen_at),
      signal_type: "development",
      signal_subtype: subtype,
      category: "Permit application",
      public_label: LAYER_LABEL[layer],
      verification_status: STATUS.VERIFIED,   // official municipal record
      confidence: lat != null && lon != null ? 0.9 : 0.4,
      editorial_priority: isHighValue ? (value >= 2000000 ? 90 : 70) : (isDemo ? 60 : (isStorm ? 50 : 20)),
      latitude: lat, longitude: lon,
      address: titleish(r.address) || null,
      municipality: "Fort Lauderdale",
      neighborhood: r.region || null,
      geographic_precision: lat != null && lon != null ? "point" : "none",
      location_source: "permit geocode",
      owner_or_applicant: titleish(r.owner_name || r.applicant_name) || null,
      contractor_or_sponsor: titleish(r.contractor_name) || null,
      valuation_or_amount: value,
      project_scale: isHighValue ? "major" : "standard",
      layer: layer,
      source_attribution: "City of Fort Lauderdale public permit record " + txt(r.permit_number)
    });
    if (!meaningful) s.exclusion_reasons.push("routine permit: below $500k, not demolition, not storm-related");
    s._meaningful = meaningful;
    s._raw = r;
    return s;
  }

  // ---------- FAA ADAPTER (Broward only) ----------
  function fromFaa(r) {
    var lat = num(r.lat), lon = num(r.lon);
    var st = txt(r.structure_type);
    var isCrane = /^CRANE/i.test(st);
    var height = num(r.agl_height);
    var recordDate = isoDate(r.date_entered);

    var s = makeSignal({
      signal_id: "faa:" + txt(r.asn),
      source_name: "FAA Obstruction Evaluation (OE/AAA)",
      source_record_id: txt(r.asn),
      source_record_url: r.asn ? "https://oeaaa.faa.gov/oeaaa/external/searchAction.jsp?action=displayOECase&oeCaseID=" + encodeURIComponent(txt(r.asn)) : null,
      source_table: "faa_oeaaa",
      source_record_date: recordDate,
      first_detected_at: isoDate(r.first_fetched_at) || recordDate,
      last_seen_at: isoDate(r.last_fetched_at),
      signal_type: "aviation-obstruction",
      signal_subtype: isCrane ? "crane" : "tall-structure",
      category: "FAA obstruction case",
      public_label: LAYER_LABEL[LAYER.FAA],
      verification_status: STATUS.VERIFIED,   // federal case record
      confidence: lat != null && lon != null ? 0.85 : 0.3,
      editorial_priority: isCrane ? 80 : (height != null && height >= 200 ? 70 : 40),
      latitude: lat, longitude: lon,
      address: null,
      municipality: titleish(r.nearest_city) || null,
      geographic_precision: lat != null && lon != null ? "point" : "none",
      location_source: "FAA filed coordinates",
      project_name: titleish(r.structure_description) || null,
      owner_or_applicant: titleish(r.sponsor) || null,
      valuation_or_amount: null,
      project_scale: height != null ? height + " ft AGL proposed" : null,
      layer: LAYER.FAA,
      source_attribution: "FAA OE/AAA case " + txt(r.asn)
    });
    s._meaningful = true;
    s._height = height;
    s._status_code = txt(r.status_code);
    s._structure_type = st;
    s._raw = r;
    if (!inBroward(lat, lon)) s.exclusion_reasons.push("outside Broward County bounds");
    return s;
  }

  // ---------- FDEP ADAPTER ----------
  function fromFdep(r) {
    var lat = num(r.lat), lon = num(r.lon);
    var permitType = txt(r.permit_type);
    var status = txt(r.permit_status);
    var recordDate = isoDate(r.received_date);
    var action = txt(r.agency_action);

    var s = makeSignal({
      signal_id: "fdep:" + txt(r.permit_id || r.objectid),
      source_name: "Florida DEP Environmental Resource Permits",
      source_record_id: txt(r.permit_id || r.objectid),
      source_record_url: txt(r.documents_url) || null,
      source_table: "fdep_erp",
      source_record_date: recordDate,
      first_detected_at: isoDate(r.first_fetched_at) || recordDate,
      last_seen_at: isoDate(r.last_fetched_at),
      signal_type: "environmental",
      signal_subtype: action ? "agency-action" : "application",
      category: "Environmental resource permit",
      public_label: LAYER_LABEL[LAYER.ENVIRONMENTAL],
      verification_status: STATUS.VERIFIED,   // state agency record
      confidence: lat != null && lon != null ? 0.85 : 0.3,
      editorial_priority: /issued/i.test(status) ? 55 : 45,
      latitude: lat, longitude: lon,
      address: titleish(r.street_address) || null,
      municipality: titleish(r.city) || null,
      geographic_precision: lat != null && lon != null ? "point" : "none",
      location_source: "FDEP filed coordinates",
      project_name: titleish(r.project_name) || null,
      owner_or_applicant: titleish(r.applicant_company || r.applicant_name) || null,
      valuation_or_amount: null,
      project_scale: null,
      layer: LAYER.ENVIRONMENTAL,
      source_attribution: "FDEP ERP record " + txt(r.permit_id || r.objectid)
    });
    s._meaningful = true;
    s._permit_type = permitType;
    s._status = status;
    s._action = action;
    s._raw = r;
    if (!inBroward(lat, lon)) s.exclusion_reasons.push("outside Broward County bounds");
    return s;
  }

  // ---------- CLERK ADAPTER (deferred interface — never manufactures coordinates) ----------
  // Preliminary Clerk records currently carry no coordinates and no verified parcel link.
  // This interface accepts an OPTIONAL resolver that must return a verified {lat, lon, parcel_id,
  // location_source}. Without a resolver result the Signal is produced but explicitly excluded
  // from the map. No geocoding of names or legal descriptions. No text-similarity parcel guessing.
  var CLERK_TYPES = { D: "deed", M: "mortgage", NOC: "notice of commencement", LIE: "lien", LP: "lis pendens", FJ: "judgment" };
  function fromClerk(r, resolveLocation) {
    var loc = typeof resolveLocation === "function" ? resolveLocation(r) : null;
    var isVerifiedLoc = !!(loc && num(loc.lat) != null && num(loc.lon) != null && loc.parcel_id);
    var docCode = txt(r.doc_type || r.doc_type_code).toUpperCase();
    var recordDate = isoDate(r.record_date || r.recording_date_iso);
    var preliminary = txt(r.source) === "acclaimweb-public-search" || txt(r.verification_status) === "preliminary";

    var s = makeSignal({
      signal_id: "clerk:" + txt(r.instrument_number),
      source_name: preliminary ? "Broward Clerk (preliminary public search)" : "Broward Clerk official records",
      source_record_id: txt(r.instrument_number),
      source_table: preliminary ? "broward_clerk_preliminary" : "broward_clerk_records_doc",
      source_record_date: recordDate,
      first_detected_at: isoDate(r.preliminary_first_seen_at) || recordDate,
      signal_type: "property-record",
      signal_subtype: CLERK_TYPES[docCode] || (txt(r.doc_type) || "recording").toLowerCase(),
      category: "Recorded instrument",
      public_label: "Property record",
      verification_status: preliminary ? STATUS.PRELIMINARY : STATUS.VERIFIED,
      confidence: isVerifiedLoc ? 0.7 : 0.2,
      editorial_priority: docCode === "NOC" ? 65 : 35,
      latitude: isVerifiedLoc ? num(loc.lat) : null,
      longitude: isVerifiedLoc ? num(loc.lon) : null,
      verified_parcel_id: isVerifiedLoc ? loc.parcel_id : null,
      geographic_precision: isVerifiedLoc ? "parcel" : "none",
      location_source: isVerifiedLoc ? loc.location_source || "verified parcel link" : null,
      owner_or_applicant: titleish(r.first_direct_name) || null,
      layer: LAYER.DEVELOPMENT,
      source_attribution: "Broward Clerk instrument " + txt(r.instrument_number)
    });
    s._meaningful = docCode === "NOC" || docCode === "LIE" || docCode === "LP";
    s._raw = r;
    if (!isVerifiedLoc) s.exclusion_reasons.push("no verified parcel or coordinate link — Clerk mapping deferred by policy");
    return s;
  }

  // ---------- PROPERTY TRANSFER ADAPTER (deeds + easements) ----------
  // Input rows come from the read-only view broward_property_transfer_links, which links a Clerk
  // instrument to an official county parcel by EXACT canonical folio and nothing else.
  //
  // Scope is deliberately narrow. Mortgages, liens, lis pendens and judgments are NOT handled here:
  // the Clerk's public files carry no parcel identifier for those instrument types, and the Clerk's
  // own instrument-link file does not reach a parcel-bearing instrument for them (audited 2026-07-19).
  // An instrument-to-instrument link is not evidence of shared property.
  var TRANSFER_TYPE = {
    PROPERTY_TRANSFER: "PROPERTY_TRANSFER",
    OWNERSHIP_CHANGE: "OWNERSHIP_CHANGE",
    EASEMENT_RECORDED: "EASEMENT_RECORDED"
  };

  // Deed subtypes that state a conveyance of title on their face. The Clerk's doc file uses the
  // generic code "D" and does not publish the subtype, so this stays empty in practice and the
  // adapter falls back to PROPERTY_TRANSFER rather than asserting that ownership changed.
  var OWNERSHIP_SUBTYPES = { WD: 1, "WD*": 1, SWD: 1, GWD: 1, TRD: 1 };

  function fromPropertyTransfer(r) {
    var isEasement = txt(r.doc_type_code).toUpperCase() === "EAS" || txt(r.instrument_kind) === "easement";
    var lat = num(r.latitude), lon = num(r.longitude);
    var amount = num(r.consideration_amount);
    var recordDate = isoDate(r.recording_date);
    var subtype = txt(r.deed_subtype).toUpperCase();
    var instrument = txt(r.instrument_number);
    var official = txt(r.record_source) !== "preliminary";

    var signalType = isEasement ? TRANSFER_TYPE.EASEMENT_RECORDED
      : (OWNERSHIP_SUBTYPES[subtype] ? TRANSFER_TYPE.OWNERSHIP_CHANGE : TRANSFER_TYPE.PROPERTY_TRANSFER);

    var s = makeSignal({
      signal_id: "transfer:" + instrument + ":" + txt(r.folio_canonical),
      source_name: official ? "Broward Clerk official records" : "Broward Clerk (preliminary public search)",
      source_record_id: instrument,
      source_table: "broward_property_transfer_links",
      source_record_date: recordDate,
      signal_type: signalType,
      signal_subtype: isEasement ? "easement" : "deed",
      category: isEasement ? "Recorded easement" : "Recorded deed",
      public_label: LAYER_LABEL[isEasement ? LAYER.EASEMENT : LAYER.DEED],
      verification_status: official ? STATUS.VERIFIED : STATUS.PRELIMINARY,
      confidence: lat != null && lon != null ? 0.9 : 0.2,
      editorial_priority: isEasement ? 40 : (amount != null && amount >= 5000000 ? 90 : (amount != null && amount >= 1000000 ? 70 : 45)),
      latitude: lat, longitude: lon,
      address: titleish(r.address) || null,
      municipality: null,               // the county layer publishes no municipality value; see caveat
      verified_parcel_id: txt(r.folio_canonical) || null,
      geographic_precision: lat != null && lon != null ? "parcel" : "none",
      location_source: "official county parcel centroid, matched by exact canonical folio",
      owner_or_applicant: titleish(r.parties) || null,
      valuation_or_amount: amount,
      layer: isEasement ? LAYER.EASEMENT : LAYER.DEED,
      source_attribution: "Broward Clerk instrument " + instrument + " · county parcel " + txt(r.folio_canonical)
    });

    // A record the linkage view could not resolve to exactly one parcel never reaches the map.
    var state = txt(r.verification_state).toUpperCase();
    if (state === "CONFLICT") {
      s.verification_status = STATUS.CONFLICT;
      s.conflicts = [{ field: "parcel", values: [r.folio_canonical], sources: ["clerk lgl-ver", "county parcel layer"] }];
      s.exclusion_reasons.push("instrument references more than one parcel; a single point would misstate it");
    } else if (state === "UNRESOLVED") {
      s.exclusion_reasons.push("clerk folio is not present in the official county parcel layer");
    }

    s._meaningful = true;
    s._is_easement = isEasement;
    s._raw = r;
    return s;
  }

  // ---------- PHASE 8: PUBLIC-ELIGIBILITY RULESET ----------
  function applyEligibility(s) {
    var reasons = s.exclusion_reasons;
    if (s.latitude == null || s.longitude == null) reasons.push("no reliable location");
    else if (!inBroward(s.latitude, s.longitude)) reasons.push("location outside Broward bounds");
    if (!s.source_name || !s.source_record_id) reasons.push("missing source identification");
    if (!s.source_record_date) reasons.push("missing source record date");
    if (s.verification_status === STATUS.CONFLICT) reasons.push("unresolved source conflict");
    if (s.verification_status === STATUS.NEEDS_REVIEW) reasons.push("needs review before public display");
    if (s._meaningful === false) { /* already recorded a routine-permit reason */ }
    s.public_eligibility = reasons.length === 0 && s._meaningful !== false;
    return s;
  }

  // ---------- PHASE 9: INTELLIGENCE PASS (deterministic facts, prose as presentation) ----------
  function applyIntelligence(s) {
    var where = s.address || s.neighborhood || s.municipality || "Broward County";
    var dateStr = fmtDate(s.source_record_date);
    var amt = money(s.valuation_or_amount);

    if (s.source_table === "permits") {
      var kind = s.signal_subtype;
      if (kind === "demolition") {
        s.headline = "Demolition permit filed at " + where;
        s.what_happened = "A demolition permit application was filed.";
        s.why_it_matters = "A demolition filing makes the parcel worth reviewing for a possible physical change; it does not establish redevelopment intent.";
        s.what_to_watch = "Watch for a separately sourced, later application at the same parcel. Do not assume the filings are connected without record evidence.";
      } else if (kind === "storm-related") {
        s.headline = "Storm-related work filed at " + where;
        s.why_it_matters = "The filing describes hardening or repair-type work (roofing, openings, drainage, seawall or generator).";
        s.what_to_watch = "Watch whether similar filings cluster on nearby blocks.";
      } else if (kind === "high-value") {
        s.headline = (amt ? amt + " " : "High-value ") + "permit application filed at " + where;
        s.why_it_matters = "The applicant-declared amount of " + (amt || "$500,000 or more") + " makes this a higher-priority filing to review; it is not audited project cost or economic impact.";
        s.what_to_watch = "Watch for issuance, contractor changes and related sub-permits.";
      } else {
        s.headline = "Permit application filed at " + where;
        s.why_it_matters = "Routine filing; retained for context.";
        s.what_to_watch = null;
      }
      s.caveat = "This is a permit APPLICATION on the public record. It does not prove work has started, been approved, or been completed. Declared values are applicant-supplied.";
      s.evidence_summary = "Permit " + s.source_record_id + (dateStr ? " · applied " + dateStr : "") + (amt ? " · declared " + amt : "");
    } else if (s.source_table === "faa_oeaaa") {
      var isCrane = s.signal_subtype === "crane";
      var ht = s._height != null ? s._height + " ft above ground level" : null;
      s.headline = isCrane
        ? "Crane proposal enters FAA review near " + (s.municipality || "Broward")
        : "Tall-structure filing appears near " + (s.municipality || "Broward");
      s.why_it_matters = isCrane
        ? "A crane filing can identify proposed tall equipment before installation, but the federal case alone does not establish a local project, approval or construction schedule."
        : "Tall-structure cases indicate a proposed height that requires federal airspace review.";
      s.what_changed = s._status_code ? "FAA case status: " + s._status_code + "." : null;
      s.what_to_watch = "Watch for a determination and for matching local permit activity at the same location.";
      s.caveat = "An FAA case is an airspace filing under federal review. It does NOT mean construction has started or been approved locally.";
      s.evidence_summary = "FAA case " + s.source_record_id + (dateStr ? " · entered " + dateStr : "") + (ht ? " · " + ht : "");
    } else if (s.source_table === "fdep_erp") {
      var act = s._action;
      s.headline = act
        ? "State agency action recorded for " + (s.project_name || "Broward project")
        : "Environmental permit application filed" + (s.municipality ? " in " + s.municipality : "");
      s.why_it_matters = "The filing identifies a state environmental-review category such as docks, seawalls, stormwater or wetlands. It does not establish impact, approval, timing or a causal link to another filing.";
      s.what_changed = act ? "Agency action: " + act + "." : null;
      s.what_to_watch = "Watch for a status change and for related local permits at the same site.";
      s.caveat = "This is a state environmental permit record. It does not establish environmental impact, approval, or that work has begun. Source permit type: " + (s._permit_type || "not stated") + ".";
      s.evidence_summary = "FDEP " + s.source_record_id + (dateStr ? " · received " + dateStr : "") + (s._status ? " · " + s._status : "");
    } else if (s.source_table === "broward_property_transfer_links") {
      // Wording rule: a recording is a recording. State only what the instrument itself establishes.
      if (s._is_easement) {
        s.headline = "Easement recorded affecting " + where;
        s.what_happened = "An easement was recorded affecting this parcel.";
        s.why_it_matters = "An easement is a recorded interest in the parcel held by someone other than the owner.";
        s.what_to_watch = "Watch for permits or utility work on the same parcel.";
        s.caveat = "This is the fact of a recorded easement. It does not establish what the easement permits, who benefits from it, or how it affects use of the property. Read the recorded instrument for its terms.";
      } else {
        s.headline = (amt ? amt + " deed recorded at " : "Deed recorded at ") + where;
        s.what_happened = amt
          ? "A deed with a stated amount of " + amt + " was recorded."
          : "A deed was recorded for this parcel.";
        s.why_it_matters = "The recorded deed supplies a dated instrument, stated parties and parcel trail worth reviewing; the index alone does not establish beneficial ownership, deal purpose or development intent.";
        s.what_to_watch = "If later permit, demolition or FAA records appear on the same parcel, treat each as a separate event. Sequence and shared location do not prove causation.";
        s.caveat = "This is a recorded deed on the public record, matched to the county parcel by exact folio. " +
          "The stated amount is what the instrument declares — it is not an appraisal, not a market value, and not proof the sale was arm's length. " +
          "A recorded deed does not prove that ownership changed in the way you might assume, that development is planned, or that any construction will occur.";
      }
      s.what_it_does_not_prove = s.caveat;
      s.evidence_summary = "Clerk instrument " + s.source_record_id +
        (dateStr ? " · recorded " + dateStr : "") +
        (s.verified_parcel_id ? " · parcel " + s.verified_parcel_id : "") +
        (amt ? " · stated " + amt : "");
    } else if (String(s.source_table).indexOf("clerk") > -1) {
      s.headline = titleish(s.signal_subtype) + " recorded";
      s.why_it_matters = "The instrument type can direct a reader to a recorded document worth reviewing; its legal effect and relationship to other activity cannot be inferred from the index alone.";
      s.caveat = s.verification_status === STATUS.PRELIMINARY
        ? "PRELIMINARY: read from the Clerk's public search ahead of the verified county feed. Not yet reconciled to the official record."
        : "Official recorded instrument.";
      s.evidence_summary = "Instrument " + s.source_record_id + (dateStr ? " · recorded " + dateStr : "");
    }

    s.summary = [s.why_it_matters, s.what_changed].filter(Boolean).join(" ");
    s.source_attribution = s.source_attribution || s.source_name;
    return s;
  }

  function build(record, kind, opts) {
    var s;
    if (kind === "permit") s = fromPermit(record);
    else if (kind === "faa") s = fromFaa(record);
    else if (kind === "fdep") s = fromFdep(record);
    else if (kind === "clerk") s = fromClerk(record, opts && opts.resolveLocation);
    else if (kind === "transfer") s = fromPropertyTransfer(record);
    else return null;
    applyEligibility(s);
    applyIntelligence(s);
    return s;
  }

  // ---------- Bounded, viewport-aware retrieval service ----------
  // Complete-data support = every eligible record is DISCOVERABLE through bounded, filterable
  // queries. It never means loading whole tables into the browser. Each request is capped,
  // deterministically ordered, geographically bounded, and cancellable.
  var PERMIT_ELIGIBLE_OR = "(valuation_usd_clean.gte.500000,description.ilike.*demol*,permit_type.ilike.*demol*," +
    "description.ilike.*roof*,permit_type.ilike.*roof*,description.ilike.*seawall*,description.ilike.*shutter*," +
    "description.ilike.*window*,description.ilike.*generator*,description.ilike.*drainage*,description.ilike.*storm*)";

  function createService(cfg) {
    var SB = cfg.supabaseUrl.replace(/\/$/, "") + "/rest/v1/";
    var KEY = cfg.key;
    var PAGE_CAP = cfg.pageCap || 600;      // hard per-request ceiling
    var seq = 0;                            // stale-response guard

    var SOURCES = {
      permits: {
        table: "permits", latCol: "lat", lonCol: "lon", dateCol: "applied_date", kind: "permit",
        select: "permit_number,address,permit_type,description,valuation_usd_clean,applied_date,last_seen_at,lat,lon,region,contractor_name,applicant_name,owner_name,work_type",
        order: "applied_date.desc.nullslast", extra: { or: PERMIT_ELIGIBLE_OR }
      },
      faa: {
        table: "faa_oeaaa", latCol: "lat", lonCol: "lon", dateCol: "date_entered", kind: "faa",
        select: "asn,date_entered,structure_type,structure_description,agl_height,status_code,sponsor,nearest_city,lat,lon,in_broward,first_fetched_at,last_fetched_at",
        order: "date_entered.desc.nullslast", extra: { in_broward: "eq.true" }
      },
      fdep: {
        table: "fdep_erp", latCol: "lat", lonCol: "lon", dateCol: "received_date", kind: "fdep",
        select: "permit_id,objectid,project_name,applicant_company,applicant_name,permit_type,permit_status,agency_action,received_date,street_address,city,lat,lon,documents_url,first_fetched_at,last_fetched_at",
        order: "received_date.desc.nullslast", extra: {}
      },
      // Only map_eligible rows are ever requested: the view marks an instrument eligible solely when
      // its canonical folio resolves to exactly one official county parcel.
      deeds: {
        table: "broward_property_transfer_map", latCol: "latitude", lonCol: "longitude",
        dateCol: "recording_date", amountCol: "consideration_amount", cityCol: "situs_city", kind: "transfer",
        select: "instrument_number,doc_type_code,instrument_kind,recording_date,consideration_amount,verified_flag,folio_canonical,source_object_id,latitude,longitude,address,situs_city,property_type,matched_parcel_count,verification_state,linkage_method",
        order: "recording_date.desc.nullslast", extra: { map_eligible: "is.true", doc_type_code: "eq.D" }
      },
      easements: {
        table: "broward_property_transfer_map", latCol: "latitude", lonCol: "longitude",
        dateCol: "recording_date", amountCol: "consideration_amount", cityCol: "situs_city", kind: "transfer",
        select: "instrument_number,doc_type_code,instrument_kind,recording_date,consideration_amount,verified_flag,folio_canonical,source_object_id,latitude,longitude,address,situs_city,property_type,matched_parcel_count,verification_state,linkage_method",
        order: "recording_date.desc.nullslast", extra: { map_eligible: "is.true", doc_type_code: "eq.EAS" }
      }
    };

    function buildParams(src, o) {
      var p = {};
      Object.keys(src.extra).forEach(function (k) { p[k] = src.extra[k]; });
      p[src.latCol] = "not.is.null";
      if (o.bounds) {
        p[src.latCol] = "gte." + o.bounds.south;
        p[src.latCol + ".lte"] = null; // placeholder removed below
      }
      return p;
    }

    // PostgREST needs repeated keys for ranges, so build the query string manually.
    function urlFor(src, o, opts) {
      var u = new URL(SB + src.table);
      var q = u.searchParams;
      Object.keys(src.extra).forEach(function (k) { q.set(k, src.extra[k]); });
      if (o.bounds) {
        q.append(src.latCol, "gte." + o.bounds.south);
        q.append(src.latCol, "lte." + o.bounds.north);
        q.append(src.lonCol, "gte." + o.bounds.west);
        q.append(src.lonCol, "lte." + o.bounds.east);
      } else {
        q.append(src.latCol, "not.is.null");
        q.append(src.lonCol, "not.is.null");
      }
      if (o.startDate) q.append(src.dateCol, "gte." + o.startDate);
      if (o.endDate) q.append(src.dateCol, "lte." + o.endDate);
      if (o.minValuation && src.kind === "permit") q.append("valuation_usd_clean", "gte." + o.minValuation);
      if (o.minAmount && src.amountCol) q.append(src.amountCol, "gte." + o.minAmount);
      if (o.municipality && src.cityCol) q.append(src.cityCol, "eq." + o.municipality);
      if (o.instrument && src.kind === "transfer") q.append("instrument_number", "eq." + o.instrument);
      if (o.folio && src.kind === "transfer") q.append("folio_canonical", "eq." + o.folio);
      if (opts && opts.countOnly) { q.set("select", src.latCol); q.set("limit", "1"); }
      else {
        q.set("select", src.select);
        q.set("order", src.order);
        q.set("limit", String(Math.min(o.limit || PAGE_CAP, PAGE_CAP)));
        q.set("offset", String(o.offset || 0));
      }
      return u;
    }

    function headers(countMode) {
      var h = { apikey: KEY, Accept: "application/json" };
      if (countMode) h.Prefer = "count=planned";   // exact count times out on permits (57014); planner estimate is instant
      return h;
    }

    function countFor(srcKey, o, signal) {
      var src = SOURCES[srcKey];
      return fetch(urlFor(src, o, { countOnly: true }), { headers: headers(true), signal: signal })
        .then(function (r) {
          var cr = r.headers.get("content-range") || "";
          var total = cr.split("/")[1];
          return total && total !== "*" ? Number(total) : null;
        }).catch(function () { return null; });
    }

    function fetchSource(srcKey, o, signal) {
      var src = SOURCES[srcKey];
      return fetch(urlFor(src, o), { headers: headers(false), signal: signal }).then(function (r) {
        if (!r.ok) throw new Error(srcKey + " HTTP " + r.status);
        return r.json();
      }).then(function (rows) { return { kind: src.kind, key: srcKey, rows: rows }; });
    }

    return {
      PAGE_CAP: PAGE_CAP,
      // Unbounded eligible totals (server-side counts, no rows transferred).
      SOURCE_KEYS: Object.keys(SOURCES),
      totals: function (o) {
        var opt = o || {};
        var keys = (o && o.sources && o.sources.length) ? o.sources : Object.keys(SOURCES);
        return Promise.all(keys.map(function (k) { return countFor(k, opt); })).then(function (c) {
          var out = { all: 0 };
          keys.forEach(function (k, i) { out[k] = c[i]; out.all += (c[i] || 0); });
          return out;
        });
      },
      // Viewport/filter load. Returns signals + counts + per-source errors; stale calls resolve stale:true.
      load: function (options) {
        var o = options || {};
        var mySeq = ++seq;
        var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
        var sig = controller ? controller.signal : undefined;
        var wanted = o.sources && o.sources.length ? o.sources : ["permits", "faa", "fdep", "deeds", "easements"];
        var jobs = wanted.map(function (k) { return fetchSource(k, o, sig); });
        var countJobs = wanted.map(function (k) { return countFor(k, o, sig); });

        return Promise.all([Promise.allSettled(jobs), Promise.allSettled(countJobs)]).then(function (both) {
          if (mySeq !== seq) return { stale: true, signals: [], counts: {}, errors: [] };
          var signals = [], counts = {}, errors = [], seen = {};
          both[0].forEach(function (res, i) {
            var key = wanted[i];
            var filtered = both[1][i].status === "fulfilled" ? both[1][i].value : null;
            if (res.status !== "fulfilled") {
              // A failed request is an ERROR, never a zero-record claim.
              errors.push({ source: key, message: String(res.reason && res.reason.message || res.reason) });
              counts[key] = { eligible: null, loaded: 0, filteredTotal: filtered, failed: true };
              return;
            }
            var loaded = 0, excluded = 0;
            res.value.rows.forEach(function (row) {
              var s = build(row, res.value.kind);
              if (!s || seen[s.signal_id]) return;
              seen[s.signal_id] = 1;
              if (s.public_eligibility) { loaded++; signals.push(s); } else excluded++;
            });
            counts[key] = { loaded: loaded, excluded: excluded, fetched: res.value.rows.length,
                            filteredTotal: filtered, failed: false,
                            hasMore: res.value.rows.length >= Math.min(o.limit || PAGE_CAP, PAGE_CAP) };
          });
          return { stale: false, signals: signals, counts: counts, errors: errors,
                   offset: o.offset || 0, generated_at: new Date().toISOString() };
        });
      }
    };
  }

  global.FloridaSignalV1 = {
    VERSION: SIGNAL_VERSION,
    STATUS: STATUS, REVIEW: REVIEW, LAYER: LAYER,
    LAYER_LABEL: LAYER_LABEL, LAYER_COLOR: LAYER_COLOR,
    SOURCE_FAMILIES: SOURCE_FAMILIES, TRANSFER_TYPE: TRANSFER_TYPE,
    fromPermit: fromPermit, fromFaa: fromFaa, fromFdep: fromFdep, fromClerk: fromClerk,
    fromPropertyTransfer: fromPropertyTransfer,
    applyEligibility: applyEligibility, applyIntelligence: applyIntelligence,
    build: build, createService: createService,
    inBroward: inBroward, money: money, fmtDate: fmtDate
  };
})(typeof window !== "undefined" ? window : this);
