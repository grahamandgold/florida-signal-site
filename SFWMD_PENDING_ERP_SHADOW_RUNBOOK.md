# SFWMD pending-ERP shadow collector

**State:** code, fixture tests and two bounded manual file-only observations of
the official services. This runbook does not authorize deployment, a timer,
database table, Supabase write, Candidate, Desk `connected` label, score,
promotion or publication.

**Collector:** `ops/droplet/sfwmd_pending_erp_shadow.py`

## What this collector proves

The collector creates a read-only, file-only evidence bundle for the official
South Florida Water Management District population named **Pending
Environmental Resource Applications (All Types)**. It is a shadow source, not
a production detector.

The collector pins and preflights:

- SFWMD ArcGIS layer `14`,
  `https://geoweb.sfwmd.gov/agsext1/rest/services/Regulation_ApplicationPermits/EnvironmentalResourceApplications_RegPermitting/MapServer/14`;
- exact layer name, polygon geometry, native WKID `2881`,
  `maxRecordCount=2000`, ordered pagination support, non-versioned state and
  the reviewed 36-field schema;
- `GlobalID + APP_NO` as business identity and `OBJECTID` only as the
  deterministic pagination/debug key;
- source date semantics pinned to `Eastern Standard Time` plus IANA
  `America/New_York`, with daylight-saving behavior explicit; and
- the absence of a source edit/modified clock and historic-moment support.

The SFWMD layer itself defines the pending population. `AppStatus` may vary
inside that population and is retained verbatim. The collector does not guess
or silently filter an `AppStatus` allowlist.

## Fort Lauderdale scope

Mailing `City` and `FullAddress` are never used to decide scope. Each run also
preflights and queries the official City of Fort Lauderdale polygon:

- layer `44`, **Fort Lauderdale Municipal Boundary - Administrative Area**;
- `https://gis.fortlauderdale.gov/arcgis/rest/services/GeneralPurpose/gisdata/MapServer/44`;
- exact query `NAME = 'Fort Lauderdale' AND TYPE = 'City'`; and
- GeoJSON output in WKID `4326`.

The City publishes Fort Lauderdale as multiple polygon components. The query
must return one or more (maximum 32) exact `Fort Lauderdale` / `City` /
`LOCALFIPS=12011` features with unique valid `OBJECTID` and `GlobalID` values
and Polygon/MultiPolygon geometry in exact GeoJSON `EPSG:4326`. Overlapping
components retain separate polygon/hole parity and are combined with union
semantics; they are never flattened into an XOR ring set. All component
identities, raw response,
and schema hashes are bound into the run receipt. Source application polygons
are requested in the same WKID and included only when they intersect that
official multipart boundary. An
application whose mailing city says Fort Lauderdale but whose polygon is
outside is excluded; one whose mailing city says something else but whose
polygon intersects is included.

## Read-only execution contract

The command requires an explicit absolute `--output-dir` and one explicit
transport:

- `--fixture-dir ABSOLUTE_OR_RELATIVE_PATH` for offline replay; or
- `--allow-network` for bounded GET requests to the four pinned official URLs
  only.

There is no database or API write implementation and no wet-mode flag. The
result always says `mode=shadow_file_only`, `promotion_eligible=false` and
`connected_label_allowed=false`.

Offline fixture replay:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 ops/droplet/sfwmd_pending_erp_shadow.py \
  --output-dir /private/tmp/florida-signal-sfwmd-shadow \
  --fixture-dir tests/fixtures/sfwmd_shadow \
  --page-size 2 \
  --run-id sfwmd-shadow-fixture-review
```

Use `--allow-network` only for a separately approved, bounded shadow
observation. A network invocation still writes only the local bundle; it does
not authorize any stage or production write.

Network safeguards are a 30-second default timeout, three retries with bounded
exponential backoff, retry only for HTTP 429/500/502/503/504 and transport
timeouts, a 64 MiB per-response ceiling (configurably lower for tests), and an
allowlist that refuses every URL outside the two official
layers and their query endpoints. Redirects fail closed rather than following
the source request to another host. Every within-cap HTTP response body from
every retry is retained and hashed. An oversized response fails closed,
retains and hashes only its bounded prefix, and sets
`error_class=ResponseTooLarge` plus `truncated=true`; a no-response failure
receives an explicit empty-body hash and sanitized error class.

## Deterministic pagination

1. Fetch and validate SFWMD layer metadata.
2. Fetch the complete `OBJECTID` set with `returnIdsOnly=true`.
3. Sort it ascending and divide that frozen set into chunks no larger than
   `2000`.
4. Fetch each chunk's inclusive first/last `OBJECTID` range with
   `orderByFields=OBJECTID ASC` (avoiding an oversized ID-list URL) and require
   the returned IDs to equal the frozen chunk exactly in that order. Each page
   must also expose the exact 35 query fields (all layer fields except the
   separate geometry field `Shape`), and every feature must contain that exact
   attribute set.
5. Fetch the complete `OBJECTID` set again.

An object-ID change during the run produces `partial`, never green. The ArcGIS
layer is not versioned and exposes no `historicMoment`; therefore even a stable
ID set is an observed shadow snapshot, not a transactionally frozen source.
The limitation is explicit in the receipt and is one reason production
promotion is unavailable.

## Evidence bundle

Each create-only run directory contains:

| File | Purpose |
|---|---|
| `raw/*.json` | Exact official response bytes when within the cap; bounded prefix evidence for a fail-closed oversized response |
| `raw-manifest.json` | Request parameters, status, attempts, byte counts and SHA-256 for every raw response |
| `boundary-reference.json` | Exact city layer, query, record identity, schema hash and polygon response hash |
| `shadow-records.jsonl` | Deterministically normalized, OBJECTID-sorted Fort Lauderdale shadow rows |
| `shadow-content-index.jsonl` | Identity-sorted stable `GlobalID + APP_NO` content hashes excluding collector clocks and paging-only `OBJECTID` |
| `receipt.json` | Terminal status, counts, clocks, versions, hashes and safety assertions |
| `bundle-manifest.json` | Top-level hashes binding the bundle together |

The run directory is never overwritten. Reusing a `run_id` fails.

Accounting is exact:

```text
rows_observed = rows_shadow_included
              + rows_test_excluded
              + rows_outside_boundary
              + rows_rejected
```

Explicit `IsTestData=true` values are excluded. Known false/null values are
accepted; an unknown representation is rejected and forces `partial`.
Duplicate `GlobalID + APP_NO`, malformed identity, geometry or date values also
block green status.

Each included row has a deterministic source-content hash over its source
attributes (excluding paging-only `OBJECTID`) plus geometry. The sorted content
index can distinguish unchanged source content across runs even though the
full shadow-row file correctly changes when its observation clock changes.

## Clocks

- `run_started_at`, `observed_at` and `source_checked_at` are collector/system
  clocks.
- `source_modified_at` is always `null` with
  `UNKNOWN_NOT_EXPOSED`; collector time is never substituted for it.
- `AppReceivedDate`, `LegalCompDate`, `AppFinalActionDate`, `IssueDate` and
  `PermitExpirationDate` remain five separate event clocks.
- `event_through` is explicitly the maximum `AppReceivedDate` among included
  Fort Lauderdale shadow rows. It is not a source-modified or publication
  clock.
- The official city boundary's `created_date` and `last_edited_date` remain
  bound to the boundary reference and are not application event clocks.

## Statuses

| Status | Meaning |
|---|---|
| `ok` | Exact source/page/accounting contracts passed; may still contain zero new changes relative to another run. |
| `empty` | The official pending layer returned a stable empty ID set. |
| `partial` | ID set changed, row rejection/duplicate occurred, or accounting failed. Never green. |
| `failed` | Boundary, schema, transport, JSON or another collector contract failed. |

No status makes the output promotion eligible.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_sfwmd_pending_erp_shadow -v
python3 -c "import ast,pathlib; ast.parse(pathlib.Path('ops/droplet/sfwmd_pending_erp_shadow.py').read_text()); print('AST_OK')"
git diff --check
```

The fixtures deliberately prove that geometry, not mailing-city text, controls
scope, and that explicit test data is excluded. They make no claim about the
current live source contents.

## First bounded official observations

Two initial manual attempts failed closed and preserved receipts while the
official City boundary contract was calibrated: the layer omits an
`objectIdField` property but exposes one unambiguous `OBJECTID` OID field, and
Fort Lauderdale is seven title-case polygon components rather than one
uppercase feature. Layer 14 likewise exposes its OID through the exact field
schema and publishes both Windows `Eastern Standard Time` and IANA
`America/New_York` time-zone identifiers. The collector now pins those exact
representations without guessing among fields or boundary records.

After the final CRS, exact-page-schema, bounded-response and component-union
guards were added, two manual observations passed at source-check clocks
`2026-08-31T11:10:18.722134Z` and `2026-08-31T11:10:37.193176Z`:

- 1,100 official pending rows, one complete ordered page and stable start/end
  OBJECTID set;
- three polygons intersecting the official Fort Lauderdale multipart boundary,
  1,097 outside, zero rejected, zero duplicate identities and zero test rows;
- exact accounting, schema, pagination, identity and page checks green;
- event-through `2026-07-07T04:00:00Z` from `AppReceivedDate`, while the source
  modified clock remains `UNKNOWN_NOT_EXPOSED`; and
- identical source-content index SHA-256
  `84b79506efa274e50b342158992dcc33983212c403d44d38f1c7ca7443514459`
  across both observations even though clock-bearing record bundles differ.

Receipt SHA-256 values are
`8d2d9821869247d0ec4d85d075beaa8a8a7fd200f02f9086761dfd5b70191609`
and `873e84793a64371381b5246dc326820f2751bca8f5b62da97508f797f3da5793`.
These are manual shadow observations, not two natural scheduled runs, and they
do not make the lane connected or promotion eligible.

## Gates before any connection

The following require separate design, review and owner approval; none exists
in this change:

1. **Closed manually:** a bounded first network shadow observation with complete
   raw/hash receipt;
2. at least two natural observations proving unchanged/changed diff behavior;
3. a versioned stage schema in the canonical DigitalOcean SQLite authority,
   immutable raw storage and transactional receipt/outbox design;
4. replay-stable change/version logic and a whole-stage quality manifest;
5. security, retention, monitoring, daily-at-most cadence and recovery review;
6. a separate production admission and, later, private Supabase mirror; and
7. only after those gates, a separately reviewed Candidate/Desk integration.

Until then, the Desk label remains **planned / not connected**.
