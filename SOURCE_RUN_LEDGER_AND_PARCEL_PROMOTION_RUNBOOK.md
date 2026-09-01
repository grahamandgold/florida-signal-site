# FDEP / FAA run receipts and Broward parcel generation promotion

**State (2026-08-31):** the isolated receipt/generation foundation migration is
applied live and remains empty/default-off. It did not invoke a collector,
change a schedule, stage a parcel, or promote a generation. The atomic
FDEP/FAA staging/RPC migration and tracked Edge replacements remain code-only
pending exact service-role privilege approval. Nothing here authorizes a
parcel import or promotion.
Nothing in this runbook authorizes the remaining atomic migration, Edge
deployment, collector call, schedule change, parcel import, or promotion.

**Migration:**
`supabase/migrations/20260831052701_source_run_ledgers_and_parcel_generations.sql`

**Pending collector migrations (both newer than live `20260901052118`):**

- `supabase/migrations/20260901173100_external_source_atomic_commit.sql`
- `supabase/migrations/20260901173200_external_source_collector_cron_cutover.sql`

The second migration creates private scheduling/alert infrastructure but is
default-off: only the explicit owner-only activation function changes cron.

## 2026-08-31 production evidence

- Exact deployed bundles were exported before adaptation: `fdep-erp-sync` v1
  SHA-256 `2af13893e13a1cf48cb5f0ddf33320d6f5f30f3a944a56cfaefba2309c9529db`;
  `faa-oeaaa-sync` v1
  `822ef83ce58a08fd9defa1ccbc4ba5ce512f879f6eec72f2ba83cbd996211a22`;
  `broward-parcel-sync` v5
  `124294349fe1e859e0bcb7438df71facecf649b373bdd76e0e0a962bcc49eb9d`;
  `broward-parcel-fill` v1
  `e60831c324ef0276e93c8811d3345566ff2b66a9a9e40bda12b73844f4b07f24`.
- Calling cron SQL was exported with secrets redacted and hashed. FDEP runs at
  `20 9 * * *` UTC (command SHA-256 `3158256687b833d034e795bf6d6e1d2879dc91397ca728f7112235f5038a13cf`);
  FAA runs at `40 9 * * *` with retries at `10 10,11 * * *` (command SHA-256
  `a97f2550fe2b2306fdeb70e3694edc5ee2a3658f24dc94ff05de58fee241f0a0`).
  There is no active parcel cron.
- The pre-migration parcel export contains 532,470 rows and 25 columns across
  110 disjoint OID ranges. CSV SHA-256 is
  `bb28e4e74c32de218348db2b7598348e3f7b9aa479857f691366d0eeb81ec169`;
  deterministic gzip SHA-256 is
  `7c3a27d220877a391f949299f8e1cd4009949d7e09c5202cb120cc61ea21a62c`.
  Schema snapshot SHA-256 is
  `ad19b2dfc0d6fe576aa2aa421538fe6e3b985c3c65eda4eaa6da075978f42f4c`.
- Independent live set hashes after export remained
  `3c90f331f6a590ee9e396deb0f21a839d98cb8ecc5e303ec4201dcff21e614ca`
  for normalized folios and
  `816cccf550590a35e98f8f49558a7d1bd48c8d45b913b3256b785b3fb5a70681`
  for source object IDs. All 532,470 legacy rows still have a null generation
  ID and no new generation/receipt rows existed immediately after migration.
- The unbound legacy range ledger is not promotable: it reports 539,213
  accepted rows, while the live unique set is 532,470. Its page/range-local
  duplicate accounting misses 6,743 cross-page/range duplicate source rows.
- A read-only FDEP audit found 109,456 live layer-0 rows whose normalized
  `application_id`, `permit_id`, and `received_date` are null even though the
  preserved raw payload supplies `APPLICATION_NUMBER` and `RECEIVE_DATE`.
  Layer 0 and layer 1 expose different public schemas; applying the layer-1
  mapper to both caused that defect. The corrected collector maps and validates
  each layer separately. It intentionally repairs only rows observed in its
  bounded current window.
- The 2026-08-31 public-source preview for the 90-day default beginning
  2026-06-02 was 94 layer-0 rows plus 40 layer-1 rows (134 total). Counts are a
  preview, not an execution guarantee, and must be re-read immediately before
  the canary. Repair of the older 109,456-row layer-0 corpus is a separate
  historical operation: preview exact affected keys and classifications,
  preserve raw evidence, obtain explicit approval for that exact scope, and
  use bounded resumable batches. It is not admitted by this runbook or by a
  normal scheduled run.
- The live FAA `in_broward` field is stored/generated from latitude and
  longitude. The corrected atomic path never stages or writes it; PostgreSQL
  computes it. The earlier pending SQL and collector must not be deployed.
- The official FAA case identifier is `<caseId>`, not `<id>`. The reviewed
  parser uses a pinned XML implementation with entity decoding and validates
  the XML media type plus exact `caseList` envelope. A well-formed empty
  `<caseList/>` is admissible; error HTML, malformed XML, DTDs, wrong case
  families and missing/unknown required schema fields terminate the run as a
  failure with preserved raw evidence. FAA deployment must include its tracked
  `index.ts`, `parser.ts`, and function-local `deno.json` together.
- The audited 2026-08-31 OE response contained 1,627 valid entity references.
  Parser v4 admits that live response under a hard 4,096-reference ceiling,
  retains the 25 MB per-response, 100 MB per-run and eight-level nesting
  ceilings, and recognizes the five additional current FAA fields recorded in
  the parser contract. Those fields remain raw evidence only.

## Purpose

This package closes two evidence-contract gaps without pretending the deployed
collectors are tracked locally:

1. `external_source_run_receipts` records one immutable terminal receipt for
   every FDEP ERP or FAA OE/AAA run, including successful empty and unchanged
   runs.
2. Broward parcel imports are bound to one exact source generation. A range or
   staged parcel from another generation cannot satisfy the promotion gate.

The applied foundation creates no cron job, Edge function, collector
implementation, Desk status change, or service-role access to parcel
staging/promotion. The later tracked schedule migration remains default-off
until its owner-only activation function is explicitly invoked.

## Export-first prerequisite

The deployed sources for `fdep-erp-sync`, `faa-oeaaa-sync`, and
`broward-parcel-sync` are not present in this repository. Before adapting any
collector:

1. Under a separate production approval limited to read-only export, export the exact deployed
   source, dependency/lock files, function configuration, JWT setting, and the
   calling `pg_cron` SQL.
2. Record SHA-256 hashes and the export timestamp without copying secrets into
   Git, command output, raw manifests, or receipt fields.
3. Compare the exports with the live table schemas and document pagination,
   retry, transaction, empty-result, and error-response behavior.
4. Review the receipt mapping against actual collector branches. Do not invent
   response fields, page semantics, or a collector version from old notes.
5. Build and test the collector changes in a separate branch. Applying this
   schema does not authorize deploying those changes.

Stop if the deployed source cannot be exported exactly. Row timestamps alone
remain insufficient evidence, but an imagined replacement collector is not a
safe remedy.

## Receipt contract

### Privacy and privileges

`external_source_run_receipts` is in `public` for future service-role Data API
insertion, but it is private:

- RLS and `FORCE ROW LEVEL SECURITY` are enabled;
- `anon` and `authenticated` receive no grants or policies;
- `service_role` receives only `SELECT` and `INSERT` plus minimum identity
  sequence privileges;
- row update, delete, and table truncate are rejected by triggers; and
- raw evidence is referenced by opaque private object key, never a signed URL
  or query-secret-bearing URL.

The foundation migration creates no bucket or storage policy. The pending
tracked Edge replacements create or verify the private
`fl-signal-source-evidence` bucket before a run, reject a public bucket, use
UUID-bound object keys, and upload with overwrite disabled. That storage action
is part of the still-pending collector deployment approval. The replacements
read `FL_SIGNAL_SYNC_KEY` only from Supabase Edge Function secrets and return
HTTP 503 when it is unset or still contains the rejected deployment
placeholder.

### Status meanings

| Status | Meaning |
|---|---|
| `ok` | The requested source scope was observed and deterministically accounted for. It may contain only unchanged rows. |
| `empty` | The requested source scope was authoritatively observed with zero source rows. All row counts are zero. |
| `source_wait` | The source did not yet provide an authoritative result. All row counts are zero and `reason_code` is required. |
| `partial` | Some requested scope was observed but the run did not completely account for it. `reason_code` is required; never show green. |
| `failed` | The run failed before producing a complete admissible result. `reason_code` is required; never relabel it empty. |

An `ok` receipt cannot contain rejected rows. A `failed` receipt cannot claim
committed inserts or updates; if some requested scope committed while another
part failed, the terminal status is `partial` with explicit accounting.

Every terminal receipt has separate run, observation, attempted-event, and
real-world event clocks. `event_through` advances only from accepted source
evidence, never merely because the collector ran.

The accounting identities are enforced:

```text
pages_succeeded <= pages_attempted
rows_observed = rows_accepted + rows_rejected
rows_accepted = rows_inserted + rows_updated + rows_unchanged
```

`schema_contract_sha256` binds every run to its expected versioned schema,
including source waits and failures. `source_schema_sha256` separately hashes
what the remote source actually exposed and is required for `ok`, `empty`, and
`partial` receipts.
`raw_manifest_sha256` and a private object key are required for every status.
The atomic RPC requires the exact
`<source_id>/<run_id>/(failure-)manifest.json` key, validates that every raw
object named by the manifest exists under that same source/run prefix, stores
a database-owned canonical manifest copy in the immutable receipt, and
computes `raw_manifest_sha256` from that canonical JSONB itself. A failure with
no HTTP response still needs a local manifest describing the attempt,
timestamps, sanitized error class, and zero response bytes.

### Collector write order

After the deployed source is exported and mapped, the future collector change
must use this order:

1. Build the sanitized page/response manifest and hash every retained raw
   object.
2. Persist the immutable raw objects and final manifest privately.
3. Admit source-table writes and the terminal receipt through one reviewed
   transactional database RPC, or durably persist an outbox record in that
   same write transaction.
4. Insert exactly one terminal receipt using a preallocated UUID, then retry
   delivery idempotently on `run_id`; never update an existing receipt.

The RPC serializes the classify/upsert sequence by `source_id`, so concurrent
distinct run IDs cannot both misclassify one absent source row as inserted.
An idempotent replay must present every caller-owned immutable receipt field
exactly as committed, including versions, reasons, clocks, input counts,
schema hashes, outcomes, source metadata, manifest key, and manifest content.

The service-role collector is a trusted evidence writer. The RPC verifies raw
object names, source/run prefixes, hashes' format, and object existence, but it
does not download and re-hash Storage bytes. The database-owned canonical
manifest and its database-computed digest are the audit truth for what that
trusted collector asserted. Compromise of `service_role` remains outside this
receipt's proof boundary.

The applied foundation schema alone does **not** make existing source-table
writes atomic with the new receipt insert. The pending
`20260901173100_external_source_atomic_commit.sql` adds private recoverable
staging and a service-role-only `SECURITY INVOKER` RPC that derives write counts
and commits source rows plus the terminal receipt together. A collector canary
remains blocked until that exact privilege migration is approved and applied;
committing source rows first and merely hoping the later receipt insert succeeds
is not an admissible design.

## Parcel generation contract

### Objects

| Object | Purpose |
|---|---|
| `broward_parcel_import_generations` | One exact dataset vintage, declared OBJECTID coverage, aggregate counts, versions, schema hash and source manifest. |
| `broward_parcel_generation_ranges` | Inclusive OBJECTID range receipts bound by foreign key to exactly one generation. Overlaps are rejected during staging. |
| `broward_parcel_geography_stage` | Private rows keyed by `(generation_id, parcel_id_normalized)` with unique source OBJECTID and strict folio/bbox checks. |
| `fs_promote_broward_parcel_generation(uuid)` | Locked atomic gate that replaces the live countywide table only after all receipts and rows reconcile. |

The old `broward_parcel_import_runs` and `broward_parcel_range_ledger` remain
historical evidence. They are explicitly non-promotable because they do not
bind ranges to a source generation/vintage.

### Access boundary

No Data API role, including `service_role`, receives access to parcel
generation, range, staging, or promotion objects in this migration. The
promotion function is `SECURITY DEFINER` with an empty search path and fully
qualified relations, but execute is revoked from `PUBLIC`, `anon`,
`authenticated`, and `service_role`.

After the exact deployed parcel collector is exported, a separate reviewed
integration migration may grant only the operations it demonstrably needs.
Do not grant direct writes to the live countywide parcel table as a shortcut.

### Staging lifecycle

1. Generate a UUID before the pull and freeze a source dataset vintage. If the
   source exposes no named vintage, use a deterministic metadata/content
   fingerprint and document that derivation.
2. Insert one generation in `staging` with immutable source URL, collector,
   parser, normalizer, source count, declared inclusive OBJECTID bounds, and
   expected number of ranges. Also bind reviewed minimum-accepted,
   maximum-rejected, and maximum-duplicate limits to
   `quality_contract_sha256`; collectors may not choose those limits from the
   just-observed result.
3. Insert all disjoint range definitions for that generation. Empty ranges are
   valid but must be queried and receipted with expected count zero.
4. For every range, retain private raw evidence and reconcile:

   ```text
   expected_source_count = rows_received
   rows_received = rows_accepted + rows_rejected + duplicate_folios
   rows_rejected = every named rejection category summed exactly
   ```

   Here `rows_accepted` means the final deterministic winner rows staged from
   that OBJECTID range. `duplicate_folios` means raw source rows omitted by the
   reviewed duplicate-folio winner rule, not the number of duplicate groups.
   The raw manifest must preserve every rejected/duplicate decision.
5. Insert accepted winner rows only into the matching generation's staging
   table. Folios must normalize to the exact 12-character alphanumeric value;
   source OBJECTIDs and normalized folios must each be unique within the
   generation. Promotion independently proves that each range's staged
   OBJECTIDs equal that range's accepted count and that none lie outside the
   declared coverage.
6. Recompute aggregate counts from the range ledger and staged rows. Do not
   copy counters from logs by hand.
7. Set the generation to `ready` only with terminal clocks, schema hash, raw
   manifest hash/object key, and exact aggregate counts.

Range and staged rows become immutable when the generation leaves `staging`.
A generation identity, vintage, versions, source count, and coverage bounds
cannot be rewritten in place.

### Verified-source feasibility constraint

The last tracked verified baseline is not a zero-rejection/zero-duplicate
source: `FLORIDA_SIGNAL_VERIFIED_CHECKPOINT_2026-07-19.md` records 554,358 raw
rows, 50 out-of-bounds centroids, 21,838 duplicate-folio source rows collapsed
under the prior import, and 532,470 final unique parcels. Therefore:

- do not configure this gate as if every raw polygon must become a unique
  parcel row;
- do not copy the historical numbers into a new receipt without re-observing
  and hashing the current source;
- the export-first audit must recover and review the exact deterministic
  duplicate winner behavior before setting the quality contract; and
- any unexplained drift beyond approved contract bounds blocks promotion.

This migration accounts for legitimate, explicitly bounded rejections and
duplicate collapses; it does not silently waive them.

### Promotion gate

Promotion refuses the generation unless all of these are true:

- generation status is `ready`;
- the countywide source-reported count is nonzero;
- actual range count equals `expected_range_count`;
- every range is `complete` with a private raw-manifest receipt;
- sorted ranges start/end at the declared bounds and are exactly adjacent;
- no range overlap or gap exists;
- raw range count identities, rejection categories, and duplicate-collapse
  counts equal the generation totals;
- source-reported and received counts are identical;
- staged rows equal final accepted rows, meet the reviewed minimum, and each
  staged OBJECTID reconciles to the one range that claims it;
- rejection and duplicate-collapse counts stay within the separately reviewed
  quality-contract ceilings;
- staged folios and source OBJECTIDs are unique;
- every normalized/raw folio pairing is valid;
- every centroid lies within the declared Broward bounding box; and
- the live table has no unreviewed user trigger or inbound foreign key that a
  full atomic replacement could fire or cascade through.

The function shares the scheduled deed/parcel refresh advisory lock, uses one
lock order for child tables and the parent generation, then takes an
access-exclusive lock on `broward_parcel_geography` before inspecting live
triggers/FKs. It supersedes the prior promoted receipt, replaces the live rows,
stamps every row with one `import_generation_id`, verifies exact count plus
single-generation readback, and refreshes
`broward_property_transfer_map` before the same transaction commits. Any
exception rolls the parcel replacement, materialized-view refresh, and status
transition back.

## Approval-gated production sequence

The following is a future operator checklist, not permission to execute it.

### A. Before schema application

1. Complete the export-first prerequisite.
2. Obtain explicit approval for the migration and its RLS/grant changes.
3. Take and hash a schema-only backup covering every object touched.
4. Export and hash the complete current `broward_parcel_geography` table plus
   its count, normalized-folio set hash, source-object set hash, and bbox
   extrema. This is the only recovery source after a promotion.
5. Inventory every live-table trigger, inbound/outbound foreign key, dependent
   view/function and intentional Data API grant. The promotion gate refuses
   unreviewed user triggers and inbound foreign keys.
6. Confirm the existing deployed parcel collector and every role capable of
   writing `broward_parcel_geography` will be disabled/revoked before the first
   generation promotion. An old direct-to-live upsert can otherwise create a
   mixed/NULL generation after the gate commits.
7. Record current FDEP/FAA counts and run/event clocks as baseline evidence,
   without calling either collector.

### B. Apply and verify schema only

Apply the tracked migration through the approved migration process. Do not
invoke collectors or promotion during schema verification.

Verify:

```sql
select relname, relrowsecurity, relforcerowsecurity
from pg_class
where oid in (
  'public.external_source_run_receipts'::regclass,
  'public.broward_parcel_import_generations'::regclass,
  'public.broward_parcel_generation_ranges'::regclass,
  'public.broward_parcel_geography_stage'::regclass
)
order by relname;

select
  has_table_privilege('anon', 'public.external_source_run_receipts', 'select')
    as anon_can_read,
  has_table_privilege('authenticated', 'public.external_source_run_receipts', 'select')
    as authenticated_can_read,
  has_table_privilege('service_role', 'public.external_source_run_receipts', 'insert')
    as service_can_insert,
  has_table_privilege('service_role', 'public.external_source_run_receipts', 'update')
    as service_can_update;

select
  has_function_privilege(
    'service_role',
    'public.fs_promote_broward_parcel_generation(uuid)',
    'execute'
  ) as service_can_promote;
```

Expected: all four tables have RLS and forced RLS; both client roles are
private; service role can insert but not update receipts; service role cannot
promote parcels.

### C. FDEP/FAA collector canaries

Only after collector-code review and the exact production approval. The two
new migrations sort after live version `20260901052118`; do not use
`--include-all` or migration-history repair to force an older filename.

```text
Approved: apply the production external-source atomic and default-off schedule
migrations,
granting service_role SELECT/INSERT/UPDATE/DELETE on the private RLS-forced
staging table and EXECUTE on the SECURITY INVOKER
fs_commit_external_source_run RPC; rotate the retired URL query secret,
configure FL_SIGNAL_SYNC_KEY and the matching Vault values; disable legacy
FDEP/FAA schedules; then deploy FDEP and FAA collectors one at a time, run
bounded live canaries, and activate only the tracked header-authenticated
schedules after both pass. No parcel backfill or promotion.
```

1. From the clean reviewed worktree, prove migration order before any write:

   ```bash
   export FL_SIGNAL_PROJECT_REF=jrjewmzkyluxdywyusrw
   supabase link --project-ref "$FL_SIGNAL_PROJECT_REF"
   supabase migration list --linked
   supabase db push --linked --dry-run
   ```

   Expected pending order is exactly `20260901173100` then `20260901173200`,
   both after live `20260901052118`. Stop on any additional/unexpected version.

2. Generate one new 64-character hex key in a private shell variable, install
   the same value as Edge secret `FL_SIGNAL_SYNC_KEY` and Vault secret
   `fl_signal_external_source_sync_key`, and set Vault
   `fl_signal_functions_base_url` to the project URL ending `/functions/v1`.
   Use the Supabase secret/Vault UI or a no-echo operator channel; never place
   the value in Git, a URL, a `curl` argument, cron SQL, or saved transcript.
   Verify by name/length only:

   ```sql
   select name, length(decrypted_secret) as secret_length
   from vault.decrypted_secrets
   where name in (
     'fl_signal_functions_base_url',
     'fl_signal_external_source_sync_key'
   )
   order by name;
   ```

   Expected: exactly two rows; sync-key length at least 32; base URL contains
   no query string. Rotate and remove the retired URL-query credential.

3. Apply both migrations. The schedule migration is default-off and must leave
   `cron.job` unchanged:

   ```bash
   supabase db push --linked
   supabase migration list --linked
   ```

4. Stop legacy source calls before changing either Edge bundle:

   ```sql
   select public.fs_disable_external_source_schedules();

   select jobid, jobname, schedule, command
   from cron.job
   where jobname in (
     'fdep-erp-daily', 'faa-oeaaa-daily', 'faa-oeaaa-retry',
     'fl-signal-external-source-health'
   )
      or command ilike '%fdep-erp-sync%'
      or command ilike '%faa-oeaaa-sync%';
   ```

   Expected: the disable result is retained as the operator receipt and the
   second query returns zero rows.

5. Deploy and canary FDEP first. Keep the exact pre-deploy bundle/hash as the
   private rollback copy. The function performs its own header authentication,
   so preserve the existing gateway setting explicitly:

   ```bash
   export FL_SIGNAL_FUNCTIONS_BASE_URL="https://${FL_SIGNAL_PROJECT_REF}.supabase.co/functions/v1"
   (
     set +x
     FL_SIGNAL_SYNC_KEY_INPUT=
     trap 'unset FL_SIGNAL_SYNC_KEY_INPUT' EXIT
     trap 'exit 129' HUP
     trap 'exit 130' INT
     trap 'exit 143' TERM
     IFS= read -r -s FL_SIGNAL_SYNC_KEY_INPUT
     printf '\n'

     supabase functions deploy fdep-erp-sync \
       --project-ref "$FL_SIGNAL_PROJECT_REF" \
       --no-verify-jwt

     CANARY_DATE="$(date -u +%F)"
     {
       printf 'silent\nshow-error\nfail-with-body\nrequest = "POST"\n'
       printf 'url = "%s/fdep-erp-sync?layers=0&since=%s"\n' \
         "$FL_SIGNAL_FUNCTIONS_BASE_URL" "$CANARY_DATE"
       printf 'header = "x-florida-signal-sync-key: %s"\n' \
         "$FL_SIGNAL_SYNC_KEY_INPUT"
     } | curl --config -
   )
   ```

   Invoke one bounded current-day/layer-0 canary through a secret-safe client
   (header value supplied from an unexported subshell variable/stdin, never the
   URL or a child-process environment). Verify
   private raw object(s), manifest `terminal_receipt`, exact source/run prefix,
   database canonical manifest/hash, count identities, schema hashes, terminal
   status, source rows, and exactly one immutable receipt. Do not test the
   append-only guard with production DML. Verify it read-only from the catalog:

   ```sql
   select t.tgname, t.tgenabled, pg_catalog.pg_get_triggerdef(t.oid) as definition,
          p.proname as trigger_function, p.prosecdef as security_definer
   from pg_catalog.pg_trigger t
   join pg_catalog.pg_proc p on p.oid = t.tgfoid
   where t.tgrelid = 'public.external_source_run_receipts'::regclass
     and not t.tgisinternal
   order by t.tgname;
   ```

   Expected: exactly the tracked row-mutation and truncate triggers, both
   enabled, both calling `fs_reject_external_source_receipt_mutation`, with the
   trigger function remaining `SECURITY INVOKER`. Exercise rejected
   UPDATE/DELETE/TRUNCATE only in the disposable pgTAP suite.

6. Repeat independently for FAA, deploying all three tracked files together:

   ```bash
   (
     set +x
     FL_SIGNAL_SYNC_KEY_INPUT=
     trap 'unset FL_SIGNAL_SYNC_KEY_INPUT' EXIT
     trap 'exit 129' HUP
     trap 'exit 130' INT
     trap 'exit 143' TERM
     IFS= read -r -s FL_SIGNAL_SYNC_KEY_INPUT
     printf '\n'

     supabase functions deploy faa-oeaaa-sync \
       --project-ref "$FL_SIGNAL_PROJECT_REF" \
       --no-verify-jwt

     CANARY_DATE="$(date -u +%F)"
     {
       printf 'silent\nshow-error\nfail-with-body\nrequest = "POST"\n'
       printf 'url = "%s/faa-oeaaa-sync?types=OE&since=%s"\n' \
         "$FL_SIGNAL_FUNCTIONS_BASE_URL" "$CANARY_DATE"
       printf 'header = "x-florida-signal-sync-key: %s"\n' \
         "$FL_SIGNAL_SYNC_KEY_INPUT"
     } | curl --config -
   )
   ```

   Use a current-day OE-only canary. Verify the same receipt/evidence contract,
   and verify PostgreSQL—not the collector—computed `in_broward`.

7. Activate the reviewed schedules only after both canaries pass:

   ```sql
   select public.fs_activate_external_source_schedules();

   select jobname, schedule, command
   from cron.job
   where jobname in (
     'fdep-erp-daily', 'faa-oeaaa-daily', 'faa-oeaaa-retry',
     'fl-signal-external-source-health'
   )
   order by jobname;
   ```

   Expected schedules are FDEP `20 9 * * *`, FAA `40 9 * * *`, FAA retries
   `10 10,11 * * *`, and watchdog `0 12 * * *` UTC. Collector job commands must
   contain only calls to `fs_dispatch_external_source`; they must contain no
   URL, Vault lookup, header name, query `key=`, or credential value.

8. Observe two ordinary scheduled runs per source. Correlate dispatches with
   short-lived pg_net responses and durable receipts/alerts:

   ```sql
   select dispatch_id, source_id, request_id, dispatched_at, dispatch_kind
   from public.external_source_collector_dispatches
   order by dispatched_at desc
   limit 20;

   select source_id, run_id, status, completed_at, rows_observed,
          rows_accepted, rows_inserted, rows_updated, rows_unchanged,
          rows_rejected, source_metadata ->> 'dispatch_id' as dispatch_id,
          raw_manifest_object_key
   from public.external_source_run_receipts
   order by completed_at desc
   limit 20;

   select source_id, alert_date, reason_code, receipt_run_id,
          receipt_status, checked_at, resolved_at
   from public.external_source_run_alerts
   where resolved_at is null
   order by checked_at desc;
   ```

   A natural run is proven only when the receipt carries the exact scheduled
   `dispatch_id`; an unrelated manual receipt from the same UTC day does not
   satisfy the watchdog. The watchdog creates a durable private database
   alert. It does not send an email, page or chat notification; that external
   notification route remains a separately reviewed connection and must not be
   claimed as configured.
   A `commit_state=unknown` response must never be rewritten as a failure.
   Replay only the exact `terminal_receipt` retained in that run's private
   manifest; the RPC/readback is idempotent. Investigate any run-bound stage
   rows left older than the collector budget.

9. Rollback is fail-closed: immediately call
   `fs_disable_external_source_schedules()`, verify zero matching jobs, and
   redeploy only the exact hashed private rollback bundle. Do not delete source
   rows, raw evidence, terminal receipts, dispatches, alerts, or the two schema
   migrations. Rotate the sync key if exposure is suspected; never restore the
   retired URL-query secret.

10. Change Desk health to receipt-backed `UNKNOWN`/attention/healthy semantics
    only after the two natural observations. Never infer a collector run from
    `MAX(last_fetched_at)` alone.

### D. Parcel staging canary and full generation

Only after a separate parcel-collector integration review:

1. Exercise one exact small range in a throwaway generation that will never be
   promoted; inspect every raw object and parsed row.
2. Build a brand-new full generation. Never add legacy unbound ranges to it.
3. Approve the exact quality-contract hash and its minimum accepted,
   maximum rejected, maximum duplicate-collapse, and deterministic winner
   rules from the current export—not from the result the collector wants to
   admit.
4. Recompute all summaries and perform independent SQL readback, including
   staged winner counts per OBJECTID range.
5. If any unexplained rejection, duplicate decision, or mismatch exists, leave
   the generation unpromoted and fix the source/parser contract in a new
   generation. Do not edit a `ready` receipt.
6. Stop the old direct-to-live parcel writer and verify its DML privilege/path
   cannot race or resume after promotion.
7. Take a fresh exact live-table backup immediately before promotion.
8. Obtain explicit approval naming the exact ready generation UUID, quality
   contract hash, and backup.
9. Invoke promotion once as the database owner through the reviewed SQL path.

```sql
select public.fs_promote_broward_parcel_generation(
  '<approved-generation-uuid>'::uuid
);
```

10. Verify exact live count, one generation ID, folio/object uniqueness, bbox,
   source vintage, refreshed deed/parcel snapshot count, and generation status.
   Preserve the returned JSON result as an operator receipt.
11. Validate the `broward_parcel_geography_generation_fk` only after exact
   promotion readback and under the same reviewed change window.

### E. Rollback

- Before any promotion, schema-only rollback may remove the new isolated
  objects under separate approval.
- After promotion, schema rollback cannot restore the prior parcel rows.
  Restore only from the exact pre-promotion backup, in one reviewed
  transaction, with count/hash/bbox readback.
- Never repopulate the old live state from the unbound legacy range ledger.
- Receipt rows remain immutable evidence even when a collector deployment is
  rolled back.

## Tests

Static contract tests:

```bash
python3 -m unittest \
  tests.test_source_run_ledger_migration \
  tests.test_external_source_atomic_commit
```

Database contract tests, when a disposable local Supabase/Postgres test stack
with pgTAP is available:

```bash
supabase test db
```

This includes
`supabase/tests/source_run_ledgers_and_parcel_generations.test.sql`. The atomic
RPC also has a self-contained disposable PostgreSQL harness that executes the
real migration against exact source/receipt/generated-column fixtures:

```bash
npm run test:external-source-sql
```

That command prefers an explicit `FL_SIGNAL_TEST_DATABASE_URL`, then a working
Docker daemon, then locally installed PostgreSQL 17 tools. An explicit DSN also
requires `FL_SIGNAL_DISPOSABLE_TEST_CONFIRM=YES` and is accepted only when
PostgreSQL reports version 17, superuser/writable state, a database name
beginning `fl_signal_atomic_test`, and no custom schema or public relation;
hosted Supabase endpoints are rejected. The local fallback creates
and destroys only a uniquely named temporary cluster, and the Docker path keeps
using a uniquely named disposable container. It covers actual RLS/EXECUTE
grants, service-role invocation, both
FDEP and FAA DML branches, generated-column omission, atomic rollback, exact
idempotent replay, failed-stage cleanup, default-off scheduling, exact cadence,
secret-safe dispatch correlation, watchdog alert transitions and schedule
rollback. Do not point the SQL test at production; this prohibition applies to
both harnesses. The pgTAP test uses transaction-local fixtures and rolls back.
