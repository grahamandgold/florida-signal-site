# Tracked Supabase Edge functions

`fdep-erp-sync` and `faa-oeaaa-sync` are the reviewed atomic-receipt
replacements for the currently deployed version-1 collectors.

They fail closed unless the Supabase Edge Function secret
`FL_SIGNAL_SYNC_KEY` is configured. Invoke them with the same value in the
`x-florida-signal-sync-key` request header. Never put the secret in a URL,
source file, deployment bundle, log, receipt, manifest, command transcript or
literal `cron.job.command`. The code rejects the old public placeholder literal
and does not accept query-parameter authentication.

FAA stages only source-owned latitude/longitude fields. PostgreSQL computes the
stored generated `faa_oeaaa.in_broward` value; the collector and atomic RPC do
not supply, classify, insert, or update that generated column.

FAA XML is parsed with pinned `fast-xml-parser`, `fast-xml-validator`, and
`@nodable/entities` versions declared in the function-local `deno.json` and
the repository lock file. The parser maps the official `caseId` element,
decodes XML named and numeric entities with bounded expansion, rejects DTDs,
non-XML media types,
malformed XML, an unexpected root/case family, unknown case fields, or missing
required fields. The only zero-row response admitted as `empty` is a valid
XML `caseList` envelope with no case children. Deploy the FAA function with
`index.ts`, `parser.ts`, and `deno.json`; omitting a dependency is a failed
deployment, not a fallback to the old regular-expression parser.

The audited 2026-08-31 OE response contained 1,627 valid XML references, so
parser v4 uses a finite 4,096-reference document-wide ceiling. It retains the
one-million-character expansion ceiling, eight-level XML nesting limit, 25 MB
per-response collector limit and 100 MB per-run limit. Current official raw
fields `amslOverallHeightDet`, `dateBuilt`, `fccAsrNumber`,
`recommendedMarkLightType`, and `recommendedMarkLightTypeOther` are accepted
and contract-hashed but are not promoted into normalized source-owned columns.

FDEP layer 0 (ERP SPGP) and layer 1 (ERP permits) have different public source
schemas. The tracked normalizer maps them separately, fails closed when a
required source field disappears, and binds both expected field sets into the
schema-contract hash. Layer 0's `APPLICATION_NUMBER`, `RECEIVE_DATE`, `SITE_*`
and SPGP status fields are never interpreted as their similarly named layer 1
fields. Because the existing cron URL supplies no `since`, the replacement
uses a bounded 90-day default and records the effective `since`, `through` and
`since_mode` in both the raw manifest and terminal receipt metadata. The
source predicate is inclusive at `since` and exclusive at midnight after
`through`; the receipt records the equivalent inclusive end-of-day attempted
clock and an explicit window-semantics label. An
explicit `since` is validated and capped at 370 days; there is no unbounded
`1=1` production path.

Before either deployment:

1. obtain the exact privilege/RPC approval phrase in
   `SOURCE_RUN_LEDGER_AND_PARCEL_PROMOTION_RUNBOOK.md`;
2. apply and verify
   `20260901173100_external_source_atomic_commit.sql` and the default-off
   `20260901173200_external_source_collector_cron_cutover.sql`;
3. re-export the currently deployed function and retain a private rollback
   copy plus its bundle SHA-256;
4. rotate the retired URL query secret; configure the new value as the Edge
   secret `FL_SIGNAL_SYNC_KEY` and as a private Vault value used by pg_cron to
   construct the `x-florida-signal-sync-key` header at execution time; verify
   the tracked cron command calls only the owner dispatcher and contains no
   Vault reference or value; keep `verify_jwt=false` because the function
   performs this custom header authentication, and verify missing/placeholder
   credentials fail closed before a canary;
5. call the owner-only schedule-disable function, deploy one function, run its
   bounded canary, and verify its private raw objects, exact run-bound manifest,
   database-computed canonical manifest hash, atomic source write, immutable
   receipt, and advisor diff before touching the other function; activate the
   tracked schedules only after both source canaries pass.

Every network request has a bounded deadline and every collector reserves time
for a failure receipt. A normal manifest retains the exact terminal receipt
payload used by the RPC. If the RPC response is lost, the collector retries the
same payload and reads the immutable receipt back. If the state still cannot be
proven, it returns `commit_state=unknown` and does not write a contradictory
failed receipt; the private manifest/stage remain recoverable and the watchdog
opens an alert when no receipt with that scheduled dispatch's exact UUID
follows.

Do not deploy these functions against only the receipt foundation migration:
they intentionally have no direct source-table write fallback. Never add one.

`service_role` is the trusted evidence-writer boundary. The database retains
and hashes its canonical manifest and verifies that every named raw object
exists under the exact run prefix; it does not fetch each Storage object to
independently reproduce the collector-supplied per-object content hash.
