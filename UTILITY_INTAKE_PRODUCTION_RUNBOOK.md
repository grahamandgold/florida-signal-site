# Utility and engineering intake production runbook

## Scope and source contract

This lane exposes five exact Fort Lauderdale Accela record-number families in
the private Data Desk:

- `ENG-CR` — water/wastewater capacity requests
- `ENG-OAA` — outside-agency engineering intake
- `ROW-SEW` — sewer right-of-way work
- `ROW-WTR` — water right-of-way work
- `PLB-SEWCP-WT` — sewer-cap walk-through records

The existing Accela collection is the only source transport. The lane derives
an evidence view from canonical SQLite and verifies the existing Supabase
`permits` mirror. It does not contact Accela, add a utility inbox, establish a
serving utility, prove that a record predates PDMR or a permit application, or
write a permit, score, Candidate, Signal, story, or public output.

Parity means equality of the complete declared 16-column mirror projection:
count, permit-number set, and canonical projected-row hash. It is not a claim
of transactional snapshot isolation. Two complete remote reads must produce
the same proof; any intervening mutation visible to those reads fails closed.

## Least-privilege transport

The collector has one hard-coded remote operation: `GET /rest/v1/permits`
using `SUPABASE_ANON_KEY` (a publishable or legacy `anon` key). It selects only
the declared 16 columns, walks stable permit-number keyset pages until an
explicit empty page, reconciles every page to Supabase's exact declared count,
enforces row/scan caps, applies the exact family boundary locally, and repeats
the complete read for stability. It has no generic request method and no remote
write method.

The 2026-08-31 policy review found an `anon` SELECT-only `permits` policy named
`anon_read_permits` with `qual=true`, and SELECT-only `anon` access to
`editorial_pipeline_health`. The collector does not query or mutate
`editorial_pipeline_health`. Reconfirm both table grants and policies at every
deployment; the reviewed state is evidence, not a permanent assumption.

The dedicated host EnvironmentFile contains exactly:

```text
SUPABASE_URL=https://project-ref.supabase.co
SUPABASE_ANON_KEY=sb_publishable_replace-with-the-project-public-read-key
```

Install it as root:root mode `0600`. Do not reuse the shared application env,
and never install a service-role key in this file. The unit marks the
EnvironmentFile optional so systemd cannot stop before Python runs. Python
independently validates that the file exists, is a regular non-symlink,
root:root-owned, and mode `0600`; missing or invalid configuration therefore creates
a sanitized immutable failure receipt and latest pointer. Secret values are
never included in errors or receipts.

The service identity needs traverse-only access to the parent secrets directory
so Python can inspect metadata without reading the root-only file (for example,
root:andy mode `0710`). Do not grant the service identity file read permission;
systemd loads the EnvironmentFile before executing the unprivileged process.

## Evidence and health contract

Production paths are:

- SQLite: `/srv/grahamandgold/florida-signal/staging/db/permits.sqlite`
- Writer lock: `/srv/grahamandgold/florida-signal/app/db/.writer.lock`
- Evidence: `/srv/grahamandgold/florida-signal/staging/data/utility-intake/runs/`
- Receipts: `/srv/grahamandgold/florida-signal/staging/data/utility-intake/receipts/`
- Latest pointer: `/srv/grahamandgold/florida-signal/staging/data/utility-intake/latest.json`
- Dedicated env: `/srv/grahamandgold/florida-signal/secrets/florida-utility-intake.env`
- Dependency helper: `/srv/grahamandgold/florida-signal/tools/florida-utility-intake-wait.sh`

Verification and outcome receipts are create-only mode `0600` files. Each file
is fsynced and its containing directory is fsynced before it can be referenced.
Only then is the mode-`0600` latest pointer atomically replaced and the pointer
directory fsynced. The outcome receipt contains sanitized health and binds the
verification-receipt path/hash. There is no mutable remote health row.

The Desk rereads the complete all-lane projection and verifies count, primary
key hash, declared projection hash/version, two-read declaration, the
latest-pointer/outcome hash and identity, the outcome/health/verification
binding, the accessible verification receipt hash/schema/run identity, and a
75-minute collection freshness threshold. It renders exact total, event clock,
collection clock, health status, and detail. Missing, stale, empty, changing,
unbound, or mismatched evidence is warning state, never green.

## Hard stops

- Do not broaden `ENG-`, `ROW-`, `PLB-`, or `TMP-` admission.
- Dotted `ENG-CR` and `ENG-OAA` subrecords remain excluded.
- Do not add a second source transport, custom Edge transport, remote health
  write, service-role key, source-row write, scoring, promotion, or publishing.
- Stop on duplicates, schema drift, pagination/byte/cap exhaustion, short-page
  truncation, SQLite instability, writer-lock contention, unexpected empty,
  remote read mutation, parity mismatch, receipt/fsync failure, or stale/unbound
  Desk health.
- Do not claim a database snapshot. Claim only the complete declared projection
  equality and repeated-read stability actually proven.

## Install disabled

Preserve the current scripts, units, and Desk files in a new mode-`0700` backup
directory. Install the reviewed files, but keep the timer disabled:

```bash
sudo install -o root -g root -m 0755 ops/droplet/florida-utility-intake-wait.sh /srv/grahamandgold/florida-signal/tools/florida-utility-intake-wait.sh
sudo systemd-analyze verify /etc/systemd/system/florida-utility-intake.service /etc/systemd/system/florida-utility-intake.timer
sudo systemctl daemon-reload
sudo systemctl disable --now florida-utility-intake.timer
systemctl is-enabled florida-utility-intake.timer
```

The helper only performs a bounded wait for the existing Accela and sync
oneshots. Python invokes it so timeout, missing-helper, and failed-dependency
states are receipted. It never starts, stops, or restarts a dependency.

Before installing the env file, start the unit once with the timer disabled.
Require Python to start and produce a sanitized `credential_file` failure
receipt plus hash-bound latest pointer. Preserve that receipt. If systemd fails
before `ExecStart`, stop: the optional-env production path is not working.

Install the two-variable env file without printing it. Recheck its metadata and
the live Supabase authorization boundary with an administrative read-only
session:

```sql
select schemaname, tablename, policyname, roles, cmd, qual, with_check
from pg_policies
where schemaname = 'public'
  and tablename in ('permits', 'editorial_pipeline_health')
order by tablename, policyname;

select grantee, table_name, privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name in ('permits', 'editorial_pipeline_health')
  and grantee = 'anon'
order by table_name, privilege_type;
```

Require `anon` SELECT and reject any `anon` INSERT, UPDATE, DELETE, TRUNCATE,
TRIGGER, or REFERENCES grant/policy for these tables. Require the permits
SELECT policy to remain unconditional for the complete mirror read. Do not
weaken RLS to make the canary pass.

## Manual canary and Desk gate

After the normal Accela and sync jobs are terminal, run one manual canary:

```bash
sudo systemctl start florida-utility-intake.service
systemctl show florida-utility-intake.service -p Result -p ExecMainStatus -p ActiveState
sudo journalctl -u florida-utility-intake.service -n 100 --no-pager
sudo jq . /srv/grahamandgold/florida-signal/staging/data/utility-intake/latest.json
```

Require exit zero, `status=ok`, exact family accounting, non-empty source,
equal SQLite/Supabase counts, equal PK hashes, equal declared 16-column rowset
hashes, and two equal complete remote reads. Recompute both receipt hashes from
disk. Confirm the terminal safety section declares only `GET`, and verify from
the reviewed code/network audit that no POST, PATCH, PUT, DELETE, RPC, or health
request occurred. The record count is discovered by the canary, never hard-coded.

Deploy `cms/server.py` and `cms/data.html` through the existing private Desk
release process. The Desk process must have read-only access to the receipt
paths as the same trusted host identity; do not broaden receipt permissions.
If paths differ, set `FL_SIGNAL_UTILITY_RECEIPT_DIR` and
`FL_SIGNAL_UTILITY_LATEST_POINTER` to the reviewed read-only locations.

Verify sewer/utility and outside-agency engineering cards, exact live rows,
search, paging through an explicit empty page, exact total, event clock,
collection clock, receipt health/detail, and mobile readability. Mutate a test
copy of each hash/metric/clock and require `unverified` or `stale`. No failed or
absent receipt may render current.

## Natural scheduled-run gate

```bash
sudo systemctl enable --now florida-utility-intake.timer
systemctl list-timers --all florida-utility-intake.timer
```

Wait for the minute-27 or minute-57 timer run. Repeat the complete receipt,
parity, GET-only, Desk, and freshness checks using that natural run. A manual
canary alone is not completion. Confirm
`OnFailure=florida-healthreport.service` is installed and that a controlled
failed-config canary invokes the existing alert path without exposing values.

## Rollback

Disable the timer and restore only the backed-up script, unit, helper, and Desk
files. Remove the dedicated env file only through the approved secret-management
process. Do not delete evidence bundles, immutable receipts, latest pointers,
logs, Accela rows, Supabase rows, or user work. Re-run the private Desk and
existing source-lane checks after restoration.
