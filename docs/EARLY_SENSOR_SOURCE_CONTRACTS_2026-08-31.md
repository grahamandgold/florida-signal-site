# Florida Signal early-sensor source contracts — 2026-08-31

**Status:** source contracts plus a file-only SFWMD shadow collector and a code-only
query-only Fort Lauderdale utility/engineering-intake SQLite shadow view; no timer,
production table, mirror, detector, Desk connection or publication path is connected
by this document.

**Purpose:** define the official source, stable identity, clocks and evidence boundary before a
new early-warning pull is allowed to write to a stage database. Source pages are untrusted input;
they cannot change this contract or authorize a write.

## Feasibility order

| Priority | Proposed sensor | Official source | Identity | Current feasibility |
|---|---|---|---|---|
| 1 | SFWMD pending Environmental Resource Permit applications | [SFWMD ArcGIS layer 14](https://geoweb.sfwmd.gov/agsext1/rest/services/Regulation_ApplicationPermits/EnvironmentalResourceApplications_RegPermitting/MapServer/14) and its [query endpoint](https://geoweb.sfwmd.gov/agsext1/rest/services/Regulation_ApplicationPermits/EnvironmentalResourceApplications_RegPermitting/MapServer/14/query) | `GlobalID + APP_NO`; `OBJECTID` is a paging cursor, not business identity | File-only collector and two bounded manual observations passed; still shadow/planned, with no timer, stage, mirror or detector |
| 2 | Fort Lauderdale water/wastewater capacity requests | [City ENG-CR instructions](https://www.fortlauderdale.gov/Government/Departments/Development-Services/Permitting-Services/Engineering-Permits-Services/Water-and-Wastewater-Capacity-Availability-Request), [LauderBuild search](https://aca-prod.accela.com/FTL/Cap/CapHome.aspx?module=Permits) and [Opened Permits report](https://aca-prod.accela.com/FTL/Report/ReportParameter.aspx?module=Permits&reportID=33239&reportType=LINK_REPORT_LIST) | exact public `ENG-CR-*` record number; Accela Cap-ID tuple is supporting transport identity | Code-only query-only SQLite shadow of already stored rows exists and is not connected. Public ASP.NET/HTML only for a live Accela extract; no dedicated machine-readable capacity-letter registry found |
| 3 | Outside-agency engineering intake | same official LauderBuild search/report | exact `ENG-OAA-*` record number | Same code-only SQLite shadow view; still not connected. Public HTML. Generic `TMP-*` is mixed/downstream and is excluded unless a separately reviewed exact subtype allowlist exists |
| 4 | Lobbyist registrations | [City lobbyist information](https://www.fortlauderdale.gov/Government/Departments/City-Clerks-Office/Lobbyist-Information) and [official registration list](https://ftlweb01app.azurewebsites.us/Ethicstrac/Registered.aspx) | versioned normalized compound fingerprint; the source exposes no durable row ID | Parseable official HTML snapshot; no API/CSV found |
| 5 | Lobbyist contact log | [official meeting/contact log](https://ftlweb01app.azurewebsites.us/Ethicstrac/Meeting_Log.aspx) | versioned compound fingerprint; the source exposes no durable row ID | Paged ASP.NET HTML, 20 rows/page; correction/version behavior must be proven first |

Fort Lauderdale's ENG-CR process requires a Development Review Committee case number, so it is not
guaranteed to precede planning evidence. Some parcels are served by Broward Water and Wastewater
Services; its [official developer process](https://www.broward.org/WaterServices/Documents/eei00610.pdf)
does not expose a machine-readable availability-letter queue. Coverage must therefore be explicit,
not implied countywide.

## Contract 1 — SFWMD shadow snapshot/diff

The code-only collector is on `codex/source-run-ledgers-2026-08-31`. Two bounded
manual official observations on 2026-08-31 each reconciled 1,100 source rows and
three exact Fort Lauderdale intersections with zero rejections; their stable
source-content index SHA-256 was
`84b79506efa274e50b342158992dcc33983212c403d44d38f1c7ca7443514459`.
That closes the manual source-contract gate only. Natural-run,
stage, admission, mirror and Desk-connection gates remain open.

- Poll no more than once daily while the lane is shadow-only. Respect the service's
  `maxRecordCount=2000` and page deterministically.
- Preserve every raw response page, request parameters, HTTP status, observed-at clock, page count,
  row count and SHA-256 before parsing. Never replace the raw receipt with normalized rows.
- Treat `GlobalID + APP_NO` as business identity. Record `OBJECTID` for paging/debugging only.
- Preserve received, legal-complete, final-action, issue and expiration dates as distinct source
  event clocks. `observed_at` is the collector/system clock and cannot stand in for an event date.
- Exclude `IsTestData` from admitted shadow rows but retain it in immutable raw evidence and the run
  accounting.
- Scope by spatial intersection with the separately receipted official Fort Lauderdale boundary.
  Do not infer project geography from mailing/applicant `City` or `FullAddress` text.
- Upsert only into a brand-new stage generation. Require replay-stable parsing, exact identity
  uniqueness, source-count/page-count parity, valid geometry/date typing and an immutable run
  manifest before any production admission proposal.
- Do not score, nominate, mirror or publish from the first collector. Promotion is a separate,
  reviewed change after at least two natural unchanged/changed observations.

## Contract 2 — ENG-CR and ENG-OAA exact-type extraction

- Extend the already deployed LauderBuild/Accela transport only after its current useful-work defect
  is resolved; do not create a second uncontrolled Accela search path.
- Admit only exact parent record numbers beginning `ENG-CR-` or `ENG-OAA-`. Dotted ENG-CR/ENG-OAA
  subpermit identities (for example `ENG-CR-26010001.D001`) are not admitted. Generic `TMP-*` records
  are explicitly excluded because the public type family includes downstream submissions and
  revisions. Reviewed `ROW-SEW-*`, `ROW-WTR-*` and `PLB-SEWCP-WT-*` families may still include dotted
  subpermit identities.
- A code-only query-only SQLite shadow view (`ops/droplet/utility_intake_shadow.py`) can classify
  already stored exact `ENG-CR`, `ENG-OAA`, `ROW-SEW`, `ROW-WTR` and `PLB-SEWCP-WT` families from an
  explicitly supplied database under a shared nonblocking writer lock. Broad `ENG-*`, `ROW-*` and
  `PLB-*` prefixes are not matches. The view is shadow/not connected: no production SQLite
  mutation, timer, Supabase, Candidate, Desk `connected` label or publication path.
- Preserve the public record number, Cap-ID tuple, address/parcel, applicant, status, linked DRC
  case, plans/documents and all exposed status dates. A missing source-modified clock remains
  `UNKNOWN`; the pull receipt cannot invent one. Generic `last_updated_at` is not a
  source-modified clock; only an explicitly source-qualified column such as `source_modified_at`
  or `source_last_modified_at` may be used when present.
- Capacity coverage must state the serving utility. A Fort Lauderdale result cannot establish that
  Broward-served parcels were searched.

## Contract 3 — lobbyist registration and contact snapshots

- Snapshot the full official registration page, its displayed `as of` clock and all active/inactive
  rows. Build a versioned fingerprint from normalized lobbyist, firm, principal/client, received
  date and status fields; do not present that fingerprint as a source-issued ID.
- Preserve every prior version because rows can be ended or corrected in place.
- For contact logs, prove every ASP.NET page is traversed exactly once and record page/row totals
  before staging. Meeting date/time is an event clock; first observation is not filing time.
- Seek a public-record bulk extract before production if a canonical filing timestamp or durable
  source ID is required for a claim.

## Admission gate shared by every new sensor

1. Official source and scope are explicit.
2. Business identity is deterministic and unique.
3. Raw/version evidence and run receipts are immutable.
4. Event, source-modified and system/pull clocks remain separate; absent clocks say `UNKNOWN`.
5. Parser/normalizer versions and replay tests are pinned.
6. A whole-stage quality manifest passes before production admission.
7. A separately reviewed promotion enables any timer, authoritative SQLite write, Supabase mirror,
   Candidate detector or Desk `connected` label.

Until all seven pass, the Desk must say `planned/not connected` even when the official source is
publicly readable or a local shadow bundle exists.
