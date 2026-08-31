# Tracked Supabase Edge functions

`fdep-erp-sync` and `faa-oeaaa-sync` are the reviewed atomic-receipt
replacements for the currently deployed version-1 collectors.

They fail closed unless the Supabase Edge Function secret
`FL_SIGNAL_SYNC_KEY` is configured. Set that secret to the exact query secret
recovered privately from the currently deployed function; never put it in
source, a deployment bundle, a log, a receipt, a manifest, or a command
transcript. The code also rejects the old public placeholder literal.

Before either deployment:

1. obtain the exact privilege/RPC approval phrase in
   `SOURCE_RUN_LEDGER_AND_PARCEL_PROMOTION_RUNBOOK.md`;
2. apply and verify
   `20260831090000_external_source_atomic_commit.sql`;
3. re-export the currently deployed function and retain a private rollback
   copy plus its bundle SHA-256;
4. configure `FL_SIGNAL_SYNC_KEY` through the approved Supabase secret path,
   verify an unset/placeholder value returns HTTP 503, and leave
   `verify_jwt=false` so the unchanged secret-bearing cron URL continues to
   authenticate;
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
