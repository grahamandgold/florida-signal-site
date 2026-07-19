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

section("PROPERTY TRANSFER ADAPTER (deeds + easements)");
const deedRow = { instrument_number: "120843560", doc_type_code: "D", instrument_kind: "deed", recording_date: "2026-05-01", consideration_amount: 180000000, folio_canonical: "504210460010", source_object_id: 257808, latitude: 26.11788, longitude: -80.14489, address: "401 SW 1 AVE", situs_city: "FL", property_type: "10", matched_parcel_count: 1, verification_state: "VERIFIED", linkage_method: "DIRECT_EXACT_FOLIO", parties: "ACME HOLDINGS LLC (G) · RIVERSIDE PARTNERS LP (E)" };
const deedNoAmount = Object.assign({}, deedRow, { instrument_number: "120900000", consideration_amount: null });
const easementRow = { instrument_number: "120912345", doc_type_code: "EAS", instrument_kind: "easement", recording_date: "2026-06-18", consideration_amount: 10, folio_canonical: "494110AJ0050", source_object_id: 800548, latitude: 26.20045, longitude: -80.23706, address: "2309 SW 81 TER # 5", situs_city: "NL", property_type: "04", matched_parcel_count: 1, verification_state: "VERIFIED", linkage_method: "DIRECT_EXACT_FOLIO" };
const deedConflict = Object.assign({}, deedRow, { instrument_number: "120800001", matched_parcel_count: 3, verification_state: "CONFLICT" });
const deedUnresolved = Object.assign({}, deedRow, { instrument_number: "120800002", source_object_id: null, latitude: null, longitude: null, verification_state: "UNRESOLVED" });

const deed = V.build(deedRow, "transfer");
ok("deed → deed layer", deed.layer === V.LAYER.DEED, deed.layer);
ok("deed is public-eligible", deed.public_eligibility === true, JSON.stringify(deed.exclusion_reasons));
ok("signal_type is PROPERTY_TRANSFER when subtype unknown", deed.signal_type === V.TRANSFER_TYPE.PROPERTY_TRANSFER, deed.signal_type);
ok("does NOT claim ownership changed", deed.signal_type !== V.TRANSFER_TYPE.OWNERSHIP_CHANGE);
ok("carries the exact parcel", deed.verified_parcel_id === "504210460010");
ok("parcel-precision location", deed.geographic_precision === "parcel" && /exact canonical folio/.test(deed.location_source));
ok("uses recording date, not pull date", deed.source_record_date === "2026-05-01", deed.source_record_date);
ok("stated amount surfaced in what_happened", /stated amount of \$180 million/.test(deed.what_happened), deed.what_happened);
ok("no-amount deed still states the recording", /A deed was recorded for this parcel\./.test(V.build(deedNoAmount, "transfer").what_happened));
ok("caveat denies market value", /not an appraisal, not a market value/.test(deed.caveat));
ok("caveat denies arm's length", /arm's length/.test(deed.caveat));
ok("caveat denies development/construction", /development is planned, or that any construction will occur/.test(deed.caveat));
ok("headline never claims construction", !/construction|development will|breaks ground/i.test(deed.headline), deed.headline);
ok("what_it_does_not_prove is populated", !!deed.what_it_does_not_prove);
ok("evidence names instrument and parcel", /Clerk instrument 120843560/.test(deed.evidence_summary) && /parcel 504210460010/.test(deed.evidence_summary), deed.evidence_summary);
ok("deterministic id includes folio", deed.signal_id === "transfer:120843560:504210460010", deed.signal_id);
ok("high-value deed gets top priority", deed.editorial_priority === 90, String(deed.editorial_priority));
ok("parties carried", /Acme Holdings/i.test(deed.owner_or_applicant || ""), deed.owner_or_applicant);
ok("municipality left null (county publishes none)", deed.municipality === null);

const eas = V.build(easementRow, "transfer");
ok("easement → easement layer", eas.layer === V.LAYER.EASEMENT, eas.layer);
ok("easement signal type", eas.signal_type === V.TRANSFER_TYPE.EASEMENT_RECORDED, eas.signal_type);
ok("easement wording is bounded", /An easement was recorded affecting this parcel\./.test(eas.what_happened), eas.what_happened);
ok("easement does not infer impact", /does not establish what the easement permits/.test(eas.caveat));
ok("easement eligible", eas.public_eligibility === true, JSON.stringify(eas.exclusion_reasons));

const dc = V.build(deedConflict, "transfer");
ok("multi-parcel deed is CONFLICT", dc.verification_status === V.STATUS.CONFLICT, dc.verification_status);
ok("multi-parcel deed NOT map-eligible", dc.public_eligibility === false);
ok("multi-parcel reason recorded", dc.exclusion_reasons.some(r => /more than one parcel/i.test(r)), JSON.stringify(dc.exclusion_reasons));

const du = V.build(deedUnresolved, "transfer");
ok("unmatched folio NOT map-eligible", du.public_eligibility === false);
ok("unmatched reason recorded", du.exclusion_reasons.some(r => /not present in the official county parcel layer/i.test(r)), JSON.stringify(du.exclusion_reasons));
ok("unmatched deed manufactures no coordinates", du.latitude === null && du.longitude === null);

section("UNSUPPORTED CLERK CATEGORIES STAY OFF THE MAP");
["M", "LIE", "LP", "FJ"].forEach(function (code) {
  const s = V.build({ instrument_number: "9990" + code, doc_type: code, record_date: "2026-07-01", source: "acclaimweb-public-search" }, "clerk");
  ok(code + " is not map-eligible", s.public_eligibility === false, JSON.stringify(s.exclusion_reasons));
  ok(code + " has no manufactured coordinates", s.latitude === null && s.longitude === null);
});
const riskFamily = V.SOURCE_FAMILIES.filter(f => f.key === "risk-legal")[0];
ok("Risk & Legal family is declared planned, not live", riskFamily && riskFamily.status === "planned", JSON.stringify(riskFamily));
ok("Risk & Legal explains why it is empty", /no parcel identifier/i.test(riskFamily.note || ""), riskFamily && riskFamily.note);
ok("Property & Money family carries only deeds + easements",
   JSON.stringify(V.SOURCE_FAMILIES.filter(f => f.key === "property-money")[0].layers) === '["deed","easement"]');

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
ok("8 product layers defined", Object.keys(V.LAYER_LABEL).length === 8, JSON.stringify(Object.keys(V.LAYER_LABEL)));
ok("every layer has a colour", Object.keys(V.LAYER_LABEL).every(k => !!V.LAYER_COLOR[k]));
ok("every live family maps to defined layers",
   V.SOURCE_FAMILIES.filter(f => f.status === "live").every(f => f.layers.length > 0 && f.layers.every(l => !!V.LAYER_LABEL[l])));
ok("every planned family is empty and explained",
   V.SOURCE_FAMILIES.filter(f => f.status === "planned").every(f => f.layers.length === 0 && !!f.note));

console.log("\n================ RESULT ================");
console.log("  passed: " + pass + "   failed: " + fail);
console.log("========================================");
if (fail > 0) process.exit(1);
