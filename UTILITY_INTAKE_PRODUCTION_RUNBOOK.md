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

The 2026-08-31 live review found an `anon` SELECT-only `permits` policy named
`anon_read_permits` with `qual=true`. It also found broad table-level grants for
`anon`; therefore the lane is **not authorized for timer enablement** until the
separately gated least-privilege function below converges `public.permits` to
SELECT-only and a fresh readback passes. RLS is necessary but is not a reason to
ignore overbroad grants. The collector does not query or mutate
`editorial_pipeline_health`.

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
- Latest attempt: `/srv/grahamandgold/florida-signal/staging/data/utility-intake/latest-attempt.json`
- Latest success: `/srv/grahamandgold/florida-signal/staging/data/utility-intake/latest-success.json`
- Dedicated env: `/srv/grahamandgold/florida-signal/secrets/florida-utility-intake.env`
- Active release: `/srv/grahamandgold/florida-signal/utility-intake-releases/current`
- Dependency helper: `/srv/grahamandgold/florida-signal/utility-intake-releases/current/florida-utility-intake-wait.sh`

Every raw/derived shadow evidence file is create-only mode `0600`, fsynced, and
followed by a run-directory fsync. The run-directory entry itself is fsynced
before the bundle is populated. Verification and outcome receipts use the same
file-plus-directory durability contract. Only then is the mode-`0600`
latest-attempt pointer atomically replaced. A successful outcome also replaces
latest-success; a failure never overwrites the prior success. Both pointer
directories are fsynced. The outcome binds the verification path/hash. There is
no mutable remote health row.

The localhost Desk uses a separate hard-coded publishable-key GET-only client;
the utility route never calls the Desk's generic service-role helper. It rereads
the complete all-lane projection twice and verifies count, primary
key hash, declared projection hash/version, two-read declaration, the
latest-attempt/outcome hash and identity, the outcome/health/verification
binding, the accessible verification receipt hash/schema/run identity, and a
75-minute collection freshness threshold. It separately displays the latest
attempt and latest successful parity clocks, so a failed attempt cannot be
mislabelled as the last verification. Missing, stale, empty, changing, unbound,
or mismatched evidence is warning state, never green.

The Finder app stores its read-only snapshot under
`~/Library/Application Support/Florida Signal Data Wire/utility-intake/`.
`ops/mac/sync_utility_intake_receipts.py` copies fixed remote pointer names over
the existing `florida` SSH alias, copies only sanitized receipt basenames from
the fixed producer directory, verifies the complete hash/schema/run binding,
rereads both pointers for stability, then atomically places the receipt files
before the pointers. It issues no remote shell and no remote write. The helper
requires an explicit absolute, non-symlink, non-writable known-hosts file and
passes `StrictHostKeyChecking=yes` with only that file trusted. A mode-`0600`
nonblocking process lock suppresses overlap. The Desk server owns an immediate
and five-minute recurring refresh thread; it starts and stops with that exact
Desk process. A failed sync preserves the previous snapshot; the independent
75-minute receipt threshold then fails closed to stale naturally.

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

## Exact atomic install, still disabled

First preserve the current scripts, units, helper, Desk app, and existing
receipt pointers in a new explicit mode-`0700` backup directory and record a
SHA-256 inventory. Do not use a broad checkout copy as a runtime replacement.
The reviewed manifest covers the production script, its sibling shadow module,
wait helper, service, and timer. Quiesce and prove the service/timer state
**before** invoking the installer:

```bash
sudo systemctl disable --now florida-utility-intake.timer 2>/dev/null || \
  test "$(systemctl is-enabled florida-utility-intake.timer 2>/dev/null || true)" = "not-found"
sudo systemctl stop florida-utility-intake.service 2>/dev/null || true
systemctl is-active florida-utility-intake.timer
systemctl is-enabled florida-utility-intake.timer
systemctl is-active florida-utility-intake.service
sudo env FL_SIGNAL_UTILITY_INSTALL_APPROVAL=I_APPROVE_EXACT_UTILITY_INTAKE_ATOMIC_INSTALL \
  bash ops/droplet/install_utility_intake.sh "$(pwd)"
systemctl is-active florida-utility-intake.timer
systemctl is-enabled florida-utility-intake.timer
```

The first state check may report `unknown/not-found` only when the timer unit is
absent; otherwise require `inactive/disabled`. The installer rechecks before
creating a stage and fails on any active service or enabled timer. It copies all
five hash-reviewed files into an unreachable generation, validates the sibling
imports and both units there, then runs an empty-environment/missing-credential
self-test there. That self-test must exit 3 and preserve a
`startup_stage=credential_file` receipt under the printed `install-checks/`
path, with `remote_methods=[]` and no latest-success pointer. Only after every
check passes are both inactive unit files atomically placed from that same
generation; one atomic `current` symlink then switches every executable code
path. A post-switch daemon reload, byte-for-byte unit verification, active
import verification, and strict `inactive/disabled` timer check are mandatory.
Any late failure restores the prior generation and unit files and reloads them.
Do not continue if the exact hash manifest, staged or active import, self-test
receipt, unit verification, rollback, or timer-state gate fails.

The helper only performs a bounded wait for the existing Accela and sync
oneshots. Python invokes it so timeout, missing-helper, and failed-dependency
states are receipted. It never starts, stops, or restarts a dependency.

Install the two-variable env file without printing it. Apply
`20260831235500_utility_intake_anon_read_hardening.sql`; this creates a private
owner-only function and changes no table/schema grant, policy, RLS state, or row
by default. The canonical `private` schema must already exist; migration
application does not create it and performs no schema-wide revoke. Preview
current policy/grant state, preserve its output, then invoke the exact function
once in an explicit transaction:

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

begin;
select private.fs_apply_utility_intake_anon_read_hardening(
  'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
);
commit;
```

The function itself fails and rolls back unless the exact unconditional
`anon_read_permits` SELECT policy exists and no anon write policy exists. Its
postcondition requires RLS enabled and forced, `anon` SELECT, and zero anon
INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES, or column-level write
grants. Repeat both read-only queries and preserve the returned attestation.
Do not waive this gate or weaken RLS to make the canary pass.

## Manual canary and Desk gate

After the normal Accela and sync jobs are terminal, run one manual canary:

```bash
sudo systemctl start florida-utility-intake.service
systemctl show florida-utility-intake.service -p Result -p ExecMainStatus -p ActiveState
sudo journalctl -u florida-utility-intake.service -n 100 --no-pager
sudo jq . /srv/grahamandgold/florida-signal/staging/data/utility-intake/latest-attempt.json
sudo jq . /srv/grahamandgold/florida-signal/staging/data/utility-intake/latest-success.json
```

Require exit zero, `status=ok`, exact family accounting, non-empty source,
equal SQLite/Supabase counts, equal PK hashes, equal declared 16-column rowset
hashes, and two equal complete remote reads. Recompute both receipt hashes from
disk. Confirm the terminal safety section declares only `GET`, and verify from
the reviewed code/network audit that no POST, PATCH, PUT, DELETE, RPC, or health
request occurred. The record count is discovered by the canary, never hard-coded.

Deploy only the reviewed utility deltas from a branch descended from current
Desk authority; never replace whole Desk files from the older utility branch.
Run `ops/update_datawire_desktop_app.sh`, which bundles the read-only receipt
sync helper. The Finder launcher gives the loopback server the exact local
receipt/pointer paths, helper path, `florida` alias, explicit
`~/.ssh/known_hosts`, and five-minute interval. The server refreshes immediately
and repeatedly only while the Desk is open. Confirm the Desk env contains
`SUPABASE_ANON_KEY`; the utility route rejects a service-role or secret key and
sends no Authorization header.

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
canary alone is not completion. The receipt's `execution` object must contain a
valid 32-hex `systemd_invocation_id`, expected service/timer unit names, and
`natural_schedule_verified=false`—the collector does not attest itself. Prove
the natural run independently and preserve these outputs together:

```bash
invocation_id="$(sudo jq -r .execution.systemd_invocation_id \
  /srv/grahamandgold/florida-signal/staging/data/utility-intake/latest-attempt.json)"
systemctl show florida-utility-intake.timer \
  -p LastTriggerUSec -p LastTriggerUSecMonotonic -p NextElapseUSecRealtime
sudo journalctl _SYSTEMD_INVOCATION_ID="$invocation_id" --no-pager
sudo journalctl -u florida-utility-intake.timer --since '-90 minutes' --no-pager
```

Require the timer trigger clock, timer journal, service invocation ID, outcome
receipt, and latest-success run ID to identify the same natural window. Confirm
`OnFailure=florida-healthreport.service` is installed and that a controlled
failed-config canary invokes the existing alert path without exposing values.

## Rollback

Disable the timer, stop the service, atomically repoint `utility-intake-releases/current`
to the preserved prior generation, reload systemd, and prove the timer remains
inactive/disabled. Restore the backed-up Desk app only if needed. Remove the
dedicated env file only through the approved secret-management process. Do not
delete release generations, evidence bundles, immutable receipts, latest
pointers, logs, Accela rows, Supabase rows, or user work. Re-run the private
Desk and existing source-lane checks after restoration.
