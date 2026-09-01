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
   `20260831090000_external_source_atomic_commit.sql`;
3. re-export the currently deployed function and retain a private rollback
   copy plus its bundle SHA-256;
4. rotate the retired URL query secret; configure the new value as the Edge
   secret `FL_SIGNAL_SYNC_KEY` and as a private Vault value used by pg_cron to
   construct the `x-florida-signal-sync-key` header at execution time; verify
   the tracked cron command contains only the Vault secret name, never its
   value; keep `verify_jwt=false` because the function performs this custom
   header authentication, and verify missing/placeholder credentials fail
   closed before a canary;
5. deploy one function, run its bounded canary, and verify its private raw
   objects, exact run-bound manifest, database-computed canonical manifest
   hash, atomic source write, immutable receipt, and advisor diff before
   touching the other function.

Do not deploy these functions against only the receipt foundation migration:
they intentionally have no direct source-table write fallback. Never add one.

`service_role` is the trusted evidence-writer boundary. The database retains
and hashes its canonical manifest and verifies that every named raw object
exists under the exact run prefix; it does not fetch each Storage object to
independently reproduce the collector-supplied per-object content hash.
