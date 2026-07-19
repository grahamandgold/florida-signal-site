/* Florida Signal — SignalV1 adapter + eligibility + intelligence tests.
   Run:  node tests/signals.test.js     (no dependencies) */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const sandbox = { window: {}, console, fetch: function () { throw new Error("no network in tests"); }, URL, Promise };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "signals.js"), "utf8"), sandbox);
const V = sandbox.window.FloridaSignalV1;

let pass = 0, fail = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; console.log("  PASS  " + name); }
  else { fail++; console.log("  FAIL  " + name + (detail ? "  → " + detail : "")); }
}
function section(t) { console.log("\n" + t); }

// ---------- fixtures (shapes mirror the live tables) ----------
const permitHighValue = { permit_number: "BLD-GEN-26070372", address: "501 NW 7 AVE", permit_type: "Commercial", description: "Interior buildout of Sola Salons", valuation_usd_clean: 1111117, applied_date: "2026-07-17", last_seen_at: "2026-07-18", lat: 26.1298, lon: -80.1571, contractor_name: "Banyan Construction Services LLC", owner_name: "Stranahan House Inc", region: "Historical Dorsey-Riverbend" };
const permitDemo = { permit_number: "BLD-DEM-26070001", address: "1200 SE 2 ST", permit_type: "Demolition", description: "Demolition of commercial structure", valuation_usd_clean: 90000, applied_date: "2026-07-16", lat: 26.1201, lon: -80.1330 };
const permitStorm = { permit_number: "BLD-ROOF-26070099", address: "900 N BIRCH RD", permit_type: "Roofing", description: "Reroof with impact windows and shutters", valuation_usd_clean: 60000, applied_date: "2026-07-15", lat: 26.1401, lon: -80.1050 };
const permitRoutine = { permit_number: "BLD-MIN-26070500", address: "10 SW 1 AVE", permit_type: "Plumbing", description: "Water heater replacement", valuation_usd_clean: 3200, applied_date: "2026-07-15", lat: 26.1180, lon: -80.1440 };
const permitNoGeo = { permit_number: "BLD-NOGEO-1", address: "UNKNOWN", permit_type: "Commercial", description: "Major renovation", valuation_usd_clean: 900000, applied_date: "2026-07-14", lat: null, lon: null };
const faaCrane = { asn: "2026-ASO-12345-OE", date_entered: "2026-07-17", structure_type: "CRANE$TOWER", structure_description: "Tower Crane", agl_height: 240, status_code: "EVL-Pending", sponsor: "Coastal Development LLC", nearest_city: "Fort Lauderdale", lat: 26.0161, lon: -80.2139, in_broward: true };
const faaOutside = Object.assign({}, faaCrane, { asn: "2026-ASO-99999-OE", lat: 28.5, lon: -81.4 });
const fdepRec = { permit_id: "0123456-001-ERP", project_name: "Marina Seawall Repair", applicant_company: "Harbor Works Inc", permit_type: "Individual Environmental Resource Permit", permit_status: "Issued", agency_action: "Permit Issued", received_date: "2026-07-15", street_address: "1500 SE 17 ST", city: "FORT LAUDERDALE", lat: 26.0826, lon: -80.1163, documents_url: "https://depnexus.example/doc/1" };
const clerkPrelim = { instrument_number: "120977412", record_date: "2026-07-13", doc_type: "NOC", first_direct_name: "REESE,TAMMY M", source: "acclaimweb-public-search" };

// ---------- adapters ----------
section("PERMIT ADAPTER");
const hv = V.build(permitHighValue, "permit");
ok("high-value → high-value layer", hv.layer === V.LAYER.HIGH_VALUE, hv.layer);
ok("high-value is public-eligible", hv.public_eligibility === true, JSON.stringify(hv.exclusion_reasons));
ok("uses applied_date as source_record_date", hv.source_record_date === "2026-07-17", hv.source_record_date);
ok("headline states a filing, not construction", /permit application filed/i.test(hv.headline), hv.headline);
ok("caveat forbids overstating", /does not prove work has started/i.test(hv.caveat));
ok("deterministic signal_id", hv.signal_id === "permit:BLD-GEN-26070372", hv.signal_id);
ok("verification VERIFIED for municipal record", hv.verification_status === "VERIFIED");
ok("contractor carried", /Banyan/i.test(hv.contractor_or_sponsor || ""));

const demo = V.build(permitDemo, "permit");
ok("demolition → demolition layer", demo.layer === V.LAYER.DEMOLITION, demo.layer);
ok("demolition headline", /Demolition permit filed/i.test(demo.headline), demo.headline);

const storm = V.build(permitStorm, "permit");
ok("storm → storm layer", storm.layer === V.LAYER.STORM, storm.layer);
ok("storm wording does not claim damage", !/damage|destroyed/i.test(storm.headline + storm.why_it_matters));

const routine = V.build(permitRoutine, "permit");
ok("routine permit NOT public-eligible", routine.public_eligibility === false);
ok("routine exclusion reason recorded", routine.exclusion_reasons.some(r => /routine permit/i.test(r)), JSON.stringify(routine.exclusion_reasons));

const nogeo = V.build(permitNoGeo, "permit");
ok("no coordinates → excluded", nogeo.public_eligibility === false);
ok("no-location reason recorded", nogeo.exclusion_reasons.some(r => /no reliable location/i.test(r)), JSON.stringify(nogeo.exclusion_reasons));

section("FAA ADAPTER");
const crane = V.build(faaCrane, "faa");
ok("crane → FAA layer", crane.layer === V.LAYER.FAA, crane.layer);
ok("crane eligible", crane.public_eligibility === true, JSON.stringify(crane.exclusion_reasons));
ok("crane headline says review, not construction", /enters FAA review/i.test(crane.headline), crane.headline);
ok("caveat denies construction implication", /does NOT mean construction has started/i.test(crane.caveat));
ok("height surfaced", /240 ft/.test(crane.evidence_summary || ""), crane.evidence_summary);
ok("source url built", /oeaaa\.faa\.gov/.test(crane.source_record_url || ""));
const faaOut = V.build(faaOutside, "faa");
ok("outside Broward excluded", faaOut.public_eligibility === false, JSON.stringify(faaOut.exclusion_reasons));

section("FDEP ADAPTER");
const fdep = V.build(fdepRec, "fdep");
ok("fdep → environmental layer", fdep.layer === V.LAYER.ENVIRONMENTAL, fdep.layer);
ok("fdep eligible", fdep.public_eligibility === true, JSON.stringify(fdep.exclusion_reasons));
ok("agency action surfaced", /Agency action/i.test(fdep.what_changed || ""), fdep.what_changed);
ok("preserves original source category", /Individual Environmental Resource Permit/.test(fdep.caveat), fdep.caveat);
ok("does not assert environmental impact", !/harm|damage|pollut/i.test(fdep.why_it_matters + fdep.caveat));

section("CLERK ADAPTER (deferred)");
const clerk = V.build(clerkPrelim, "clerk");
ok("preliminary status", clerk.verification_status === "PRELIMINARY", clerk.verification_status);
ok("no manufactured coordinates", clerk.latitude === null && clerk.longitude === null);
ok("excluded from map with reason", clerk.public_eligibility === false && clerk.exclusion_reasons.some(r => /deferred by policy/i.test(r)), JSON.stringify(clerk.exclusion_reasons));
ok("preliminary caveat present", /PRELIMINARY/.test(clerk.caveat), clerk.caveat);
const clerkResolved = V.build(clerkPrelim, "clerk", { resolveLocation: () => ({ lat: 26.12, lon: -80.14, parcel_id: "504210010010", location_source: "verified parcel centroid" }) });
ok("resolver enables location + parcel", clerkResolved.latitude === 26.12 && clerkResolved.verified_parcel_id === "504210010010");
ok("resolved clerk still PRELIMINARY badge", clerkResolved.verification_status === "PRELIMINARY");

section("CONFLICT HANDLING");
const conflicted = V.applyEligibility(V.applyIntelligence(V.fromPermit(Object.assign({}, permitHighValue))));
conflicted.conflicts = [{ field: "valuation_or_amount", values: [1111117, 250000], sources: ["permits", "accela_details"] }];
conflicted.verification_status = "CONFLICT";
conflicted.exclusion_reasons = [];
V.applyEligibility(conflicted);
ok("CONFLICT is not public-eligible", conflicted.public_eligibility === false);
ok("conflict reason recorded", conflicted.exclusion_reasons.some(r => /conflict/i.test(r)), JSON.stringify(conflicted.exclusion_reasons));
ok("both conflicting values preserved", conflicted.conflicts[0].values.length === 2);

section("MARKER IDENTITY / CLUSTER INPUT");
const ids = [hv, demo, storm, crane, fdep].map(s => s.signal_id);
ok("marker ids unique", new Set(ids).size === ids.length);
ok("marker ids deterministic across rebuilds", V.build(permitHighValue, "permit").signal_id === hv.signal_id);
ok("all clusterable signals have numeric coords", [hv, demo, storm, crane, fdep].every(s => typeof s.latitude === "number" && typeof s.longitude === "number"));

section("EDITORIAL / PUBLICATION SAFETY");
ok("new signals start review_status NEW", hv.review_status === "NEW");
ok("no signal carries a published flag", [hv, crane, fdep].every(s => !("published" in s) && !("publish" in s)));
ok("versioned model", hv.signal_version === "SignalV1" && V.VERSION === "SignalV1");

section("LAYERS / LEGEND");
ok("6 product layers defined", Object.keys(V.LAYER_LABEL).length === 6, JSON.stringify(Object.keys(V.LAYER_LABEL)));
ok("every layer has a colour", Object.keys(V.LAYER_LABEL).every(k => !!V.LAYER_COLOR[k]));

console.log("\n================ RESULT ================");
console.log("  passed: " + pass + "   failed: " + fail);
console.log("========================================");
if (fail > 0) process.exit(1);
