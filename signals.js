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
    ENVIRONMENTAL: "environmental"
  };

  var LAYER_LABEL = {
    "development": "Development",
    "high-value": "High-value activity",
    "demolition": "Demolition",
    "storm": "Storm",
    "faa": "FAA / Cranes",
    "environmental": "Environmental"
  };

  var LAYER_COLOR = {
    "development": "#00b8dc",
    "high-value": "#071b32",
    "demolition": "#ff6d3a",
    "storm": "#1767ff",
    "faa": "#7d3cc4",
    "environmental": "#0f9d76"
  };

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
  function titleish(s) {
    return txt(s).toLowerCase().replace(/\s+/g, " ").replace(/\b[a-z]/g, function (c) { return c.toUpperCase(); });
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
      why_it_matters: base.why_it_matters || null,
      what_changed: base.what_changed || null,
      what_to_watch: base.what_to_watch || null,
      caveat: base.caveat || null,
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
        s.why_it_matters = "Demolition filings often precede redevelopment of a parcel.";
        s.what_to_watch = "Watch for a follow-on construction application at the same address.";
      } else if (kind === "storm-related") {
        s.headline = "Storm-related work filed at " + where;
        s.why_it_matters = "The filing describes hardening or repair-type work (roofing, openings, drainage, seawall or generator).";
        s.what_to_watch = "Watch whether similar filings cluster on nearby blocks.";
      } else if (kind === "high-value") {
        s.headline = (amt ? amt + " " : "High-value ") + "permit application filed at " + where;
        s.why_it_matters = "Declared value of " + (amt || "$500,000 or more") + " signals a substantial project on this parcel.";
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
        ? "Crane cases are filed before tall equipment goes up, so they can surface large projects earlier than local permits."
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
      s.why_it_matters = "Environmental resource permits cover work such as docks, seawalls, stormwater and wetland impacts, and are often filed ahead of visible construction.";
      s.what_changed = act ? "Agency action: " + act + "." : null;
      s.what_to_watch = "Watch for a status change and for related local permits at the same site.";
      s.caveat = "This is a state environmental permit record. It does not establish environmental impact, approval, or that work has begun. Source permit type: " + (s._permit_type || "not stated") + ".";
      s.evidence_summary = "FDEP " + s.source_record_id + (dateStr ? " · received " + dateStr : "") + (s._status ? " · " + s._status : "");
    } else if (String(s.source_table).indexOf("clerk") > -1) {
      s.headline = titleish(s.signal_subtype) + " recorded";
      s.why_it_matters = "Recorded instruments show ownership, financing and construction-notice activity.";
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
    else return null;
    applyEligibility(s);
    applyIntelligence(s);
    return s;
  }

  // ---------- PHASE 4: bounded read-only service ----------
  // Uses the site's existing Supabase REST convention. Never loads whole tables.
  function createService(cfg) {
    var SB = cfg.supabaseUrl.replace(/\/$/, "") + "/rest/v1/";
    var KEY = cfg.key;
    var LIMITS = { permits: 700, faa: 300, fdep: 400 };

    function q(table, params) {
      var url = new URL(SB + table);
      Object.keys(params).forEach(function (k) { url.searchParams.set(k, params[k]); });
      return fetch(url, { headers: { apikey: KEY, Accept: "application/json" } }).then(function (r) {
        if (!r.ok) throw new Error(table + " HTTP " + r.status);
        return r.json();
      });
    }

    function since(days) {
      var d = new Date(Date.now() - days * 86400000);
      return d.toISOString().slice(0, 10);
    }

    return {
      LIMITS: LIMITS,
      // Returns { signals, counts, errors } — never throws for a single-source failure.
      load: function (options) {
        var o = options || {};
        var windowDays = o.windowDays || 120;
        var jobs = [
          q("permits", {
            select: "permit_number,address,permit_type,description,valuation_usd_clean,applied_date,last_seen_at,lat,lon,region,contractor_name,applicant_name,owner_name,work_type",
            applied_date: "gte." + since(windowDays),
            lat: "not.is.null", lon: "not.is.null",
            order: "applied_date.desc.nullslast", limit: String(LIMITS.permits)
          }).then(function (rows) { return { kind: "permit", rows: rows }; }),
          q("faa_oeaaa", {
            select: "asn,date_entered,structure_type,structure_description,agl_height,status_code,sponsor,nearest_city,lat,lon,in_broward,first_fetched_at,last_fetched_at",
            in_broward: "eq.true", lat: "not.is.null",
            order: "date_entered.desc.nullslast", limit: String(LIMITS.faa)
          }).then(function (rows) { return { kind: "faa", rows: rows }; }),
          q("fdep_erp", {
            select: "permit_id,objectid,project_name,applicant_company,applicant_name,permit_type,permit_status,agency_action,received_date,street_address,city,lat,lon,documents_url,first_fetched_at,last_fetched_at",
            lat: "not.is.null",
            order: "received_date.desc.nullslast", limit: String(LIMITS.fdep)
          }).then(function (rows) { return { kind: "fdep", rows: rows }; })
        ];

        return Promise.allSettled(jobs).then(function (results) {
          var signals = [], counts = {}, errors = [], seen = {};
          results.forEach(function (res) {
            if (res.status !== "fulfilled") { errors.push(String(res.reason && res.reason.message || res.reason)); return; }
            var kind = res.value.kind, built = 0, excluded = 0;
            res.value.rows.forEach(function (row) {
              var s = build(row, kind);
              if (!s || seen[s.signal_id]) return;      // deterministic dedupe by signal_id
              seen[s.signal_id] = 1;
              if (s.public_eligibility) built++; else excluded++;
              signals.push(s);
            });
            counts[kind] = { eligible: built, excluded: excluded, fetched: res.value.rows.length };
          });
          return { signals: signals, counts: counts, errors: errors, generated_at: new Date().toISOString() };
        });
      }
    };
  }

  global.FloridaSignalV1 = {
    VERSION: SIGNAL_VERSION,
    STATUS: STATUS, REVIEW: REVIEW, LAYER: LAYER,
    LAYER_LABEL: LAYER_LABEL, LAYER_COLOR: LAYER_COLOR,
    fromPermit: fromPermit, fromFaa: fromFaa, fromFdep: fromFdep, fromClerk: fromClerk,
    applyEligibility: applyEligibility, applyIntelligence: applyIntelligence,
    build: build, createService: createService,
    inBroward: inBroward, money: money, fmtDate: fmtDate
  };
})(typeof window !== "undefined" ? window : this);
