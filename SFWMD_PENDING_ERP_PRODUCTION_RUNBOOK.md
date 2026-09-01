# SFWMD Pending ERP production package runbook

## Current truth

This repository contains a production-shaped SFWMD Pending ERP collection
package, but it is **not deployed, scheduled, enabled, mirrored, scored, or
connected** by this change. Collection, mirror, alert delivery, and offsite
backup gates all default to `0`. There is no
natural production receipt yet, so the Desk must show `UNKNOWN` and
`not_connected`.

The package observes only the official SFWMD `Pending ERP Applications` layer
and scopes records by intersection with the official City of Fort Lauderdale
boundary. The current-source snapshot is bounded to 2,000 SFWMD rows and 500
in-scope rows. A 2,001-ID start set fails before any feature-page request;
pagination and the ending ID set re-enforce the same total-run budget. There is
no date-range or unrestricted-backfill command.

The DigitalOcean SQLite database is the canonical source store. Supabase is an
optional private product mirror. Neither store is a scoring, Candidate,
review-queue, or publication authority for this lane.

## Evidence basis

The production package is downstream of the file-only collector introduced in
commit `131c2c6`. Its two preserved manual observations each saw 1,100 official
pending rows, included 3 Fort Lauderdale intersections, excluded 1,097 as
outside the boundary, and reported zero rejects or duplicate identities. Their
stable source-content index was
`84b79506efa274e50b342158992dcc33983212c403d44d38f1c7ca7443514459`.

Those observations validate deterministic replay only. They were not natural,
scheduled, staged, mirrored, scored, or connected observations. The official
layer does not expose a reliable source-modified clock, which remains
`UNKNOWN_NOT_EXPOSED`; event-through and system observation clocks stay
separate.

## Files and contracts

- `ops/droplet/sfwmd_pending_erp_shadow.py` performs the bounded official-host
  fetch, schema checks, deterministic normalization/rejection, polygon scope,
  and immutable file-only evidence capture.
- `ops/droplet/sfwmd_pending_erp_production.py` requires canonical JSON/JSONL,
  exact receipt/manifest/source/version/safety contracts, replays every bound
  official raw response through the pinned schema, boundary, paging, and
  normalizer functions, and byte-for-byte compares the resulting normalized
  rows before SQLite. It then commits current rows, immutable versions, a
  terminal run receipt, and one mirror-outbox item in one SQLite transaction.
- `ops/droplet/sfwmd_pending_erp_schema.sql` is the explicit canonical SQLite
  prerequisite. Only `install-schema`, under the shared writer lock, may apply
  it. One transaction records and rechecks migration SHA-256
  `a8f39dfe2d9dcff1ffe85cce16a5771a58138fa2cf6d1dcfc1e96c69a724d088`
  and exact object-manifest SHA-256
  `6b907c0c9943d24884c4365bb3483548e7d9d7ba831e999b3f202418b97ed98f`.
  The manifest preserves raw `sqlite_master.sql` and inventories the namespace
  case-insensitively. Partial, extra, case-variant, or definition-drifted
  schemas are poisoned and refused.
- `supabase/migrations/20260831235900_sfwmd_pending_erp_private_mirror.sql` is the
  separately applied, one-time private mirror prerequisite. It refuses any
  preexisting/case-variant SFWMD relation, type, index, or routine namespace,
  clears every non-owner table/function ACL (including custom default-privilege
  grantees), and transactionally postflights zero policies, forced RLS, the
  exact service-role privilege matrix, exact `SECURITY INVOKER` routine
  signatures/settings, required `public`/`extensions` access for the invoker,
  and no effective `anon`/`authenticated` access or schema-create authority.
- `ops/droplet/florida-sfwmd-pending-erp.service` is the manual canary path.
  The timer targets the separate `florida-sfwmd-pending-erp-timer.service`,
  which has `RefuseManualStart=yes` and creates a mode-`0400`, invocation-ID
  bound canary in the 06:17 America/New_York schedule window. Natural
  provenance additionally requires systemd's timer-only `TRIGGER_UNIT` and
  `TRIGGER_TIMER_REALTIME_USEC` activation metadata and hashes the running
process's bounded `/proc/self/cgroup` evidence for the exact timer-only
service. The raw cgroup evidence and its SHA-256 are preserved together in
the immutable canary so a reviewer can recompute the hash. Canonical SQLite
admission independently requires exact JSON string types, six-fractional-digit
UTC clocks, and the exact 06:17 America/New_York slot before treating it as
natural.
- `ops/droplet/sfwmd_pending_erp_alert.py` and its template unit provide a
  bounded Slack `OnFailure` route. `sfwmd_pending_erp_backup.py` performs an
  S3/restic upload, exact restore, and byte/hash verification before issuing a
  backup receipt. Both routes are independently default-off.

Before admission, every evidence file and directory is fsynced and the run is
sealed read-only (`0400` files, `0500` directories). Raw response bodies stay
in the host evidence directory. Mirror payloads carry
only normalized records and the hash-bound production receipt. Credentials are
read from the process environment and are never written to receipts.
Collector/mirror, alert, and backup credentials live in three separate
host-owned environment files. The restic child receives only an explicit
RESTIC/AWS variable allowlist.

Desk admission revalidates exact top-level and nested keys, canonical bytes,
receipt/pointer/provenance hashes, timer-canary identity and mode, UTC clock
ordering and future bounds, count caps/accounting, mirror fields, and every
safety boolean. Any missing, extra, unsafe, stale-contract, or contradictory
field returns `UNKNOWN / not_connected`; no receipt authorizes a connected
label.

## Admission behavior

Only a verified timer-provenanced `ok` or `empty` observation can advance the
snapshot. Under the shared writer lock, one `BEGIN IMMEDIATE` transaction:

1. classifies each business identity (`GlobalID + APP_NO`) as inserted,
   updated, or unchanged;
2. appends content-addressed versions;
3. updates the canonical current snapshot and retires identities absent from
   the complete bounded snapshot;
4. appends the terminal run receipt; and
5. for a natural run, appends one exact-payload mirror-outbox item.

The run ID is the idempotency key. Replaying the same run and evidence returns
the stored receipt. Reusing a run ID for different evidence fails closed.
Stable source content is recorded as `progress_status=unchanged`; a successful
HTTP request is not presented as source advancement.

All emitted UTC clocks have exactly six fractional digits. Observation and
failure order keys rebuild clocks in that fixed-width form before lexical
comparison, so a later fractional-second event cannot sort behind an earlier
exact-second event.

For `partial` or `failed`, normalized current rows and versions are untouched.
The terminal receipt and, for a natural run, its hash-bound evidence-row mirror
item are still committed so operators can distinguish a failure from silence.
Collection evidence contains the bounded raw attempts and failure reason.

The receipt file and `latest.json` decision remain under that same writer lock.
If the file write is interrupted, replaying the same evidence reconstructs
the exact file from the immutable SQLite receipt. The `repair-receipt` command
requires an existing matching database row and cannot admit a new run. Only a natural scheduled run
updates `latest.json`, and the pointer is an atomic rename bound to the receipt
SHA-256. Direct CLI and manual-service runs are `natural_run=false`,
`progress_status=canary`, mutate no current/version/outbox state, and never
update Desk latest. A stale natural observation is `superseded` and cannot roll
current state or latest backward. Repair advances latest only when the database
monotonic-state singleton names that run as the newest natural observation.

## Separately approved deployment prerequisites

Before touching production, an independent reviewer must confirm all of the
following:

1. The code commit and this runbook have been reviewed against the current
   project-state authority and live source contract.
2. The canonical SQLite path and shared writer-lock path are confirmed on the
   host. Take and verify a recoverable database backup.
3. Run `install-schema` first against a disposable database copy and then
   `schema-check`; compare both reviewed hashes above. Do not pipe the SQL into
   `sqlite3`. Applying `install-schema` to the canonical database remains a
   separate approved migration and requires a verified pre-migration backup.
4. Create host-owned evidence, receipt, failure-ledger, timer-provenance,
   alert-receipt, and backup-receipt directories with mode `0700`, and
   confirm the service user can write only the listed staging/app-lock paths.
5. Copy the manual service, timer-only service, timer, alert, and backup units;
   run `systemd-analyze verify`; and confirm the effective environment still
   reports all four gates as `0`. Install three distinct host-owned mode-`0600`
   files from the collector/mirror, alert-only, and
   backup-only `.env.example` contracts; never combine their secrets. Confirm
   the host systemd version exports
   `TRIGGER_UNIT` and `TRIGGER_TIMER_REALTIME_USEC` for timer-activated
   services and that the service process appears in the exact timer-only
   service cgroup. Installing or
   daemon-reloading units does not authorize enabling or starting them.
6. If a product mirror is desired, independently review and apply the Supabase
   migration only to a pristine SFWMD mirror namespace. Any preexisting object
   is a hard failure requiring investigation, not a reason to bypass the
   preflight. Preserve the successful catalog postflight showing zero policies,
   forced RLS, no arbitrary ACL grantees, and the exact service-role table/RPC
   matrix. Provision the service-role credential only in
   `florida-sfwmd-pending-erp.env`. Do not enable the mirror yet.
7. Point the Desk server's `FL_SIGNAL_SFWMD_RECEIPT_DIR` and
   `FL_SIGNAL_SFWMD_LATEST_PATH` at the host receipt directory in a separately
   reviewed Desk deployment. With no valid natural receipt, verify that it says
   `UNKNOWN / not_connected`.
8. Before alert activation, provision the Slack webhook only in the `0600`
   `florida-sfwmd-pending-erp-alert.env`, set the alert gate in a separately approved test
   window, induce a fixture failure, and reconcile its delivery receipt. The
   webhook URL must not appear in any artifact.
9. Before backup activation, independently verify `/usr/bin/restic`, provision
   an offsite `s3:https://...` repository plus a `0600` password file and
   process-only S3 credentials in `florida-sfwmd-pending-erp-backup.env`, then
   perform a fixture backup. Activation
   requires a `restore_verified=true` receipt with exact file/byte counts.

No step above authorizes a network run, timer activation, mirror activation, or
connection claim.

## Controlled natural-run observation

After explicit approval for live collection, set only
`FLORIDA_SIGNAL_SFWMD_ENABLED=1`; keep mirror, alert, and backup gates at `0`.
Starting `florida-sfwmd-pending-erp.service` manually is only a canary and
cannot create a natural receipt. A natural observation requires a separately
approved one-shot timer activation: start the timer, not either service, for
its next scheduled 06:17 America/New_York firing. The timer-only service
refuses manual start and binds its receipt to systemd's `INVOCATION_ID`,
timer trigger unit/realtime clock, timer-only service cgroup hash, scheduled
slot, immutable canary path/hash, and exact unit names. Directly executing
`timer-run`, or reaching that command without all independently verified timer
metadata, is classified as a non-natural canary and can never advance current
state or Desk latest.
Stop the timer immediately after that one firing; do not enable it at boot.

Reconcile the resulting run before proceeding:

- service exit and terminal status;
- raw manifest object paths, byte counts, and SHA-256 hashes;
- source schema and boundary hashes;
- `rows_observed <= 2000`, `rows_accepted <= 500`, and exact accounting;
- `GlobalID + APP_NO` uniqueness;
- SQLite current/version/run/outbox counts;
- file receipt hash against SQLite and `latest.json`;
- journal `INVOCATION_ID` against the immutable provenance canary and receipt;
- Desk shows a verified natural receipt but still says `not_connected`;
- no Candidate, review-queue, score, or publication row changed.

Run a second separately approved daily observation and inspect whether its
truthful progress state is `changed`, `unchanged`, `empty`, or `uncommitted`.
One successful run is not a connection decision. Enable the daily timer only
after the observation window and a separate schedule approval.

## Optional mirror activation

After the private migration and at least one reconciled local natural run, set
`FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED=1` only with separate approval. The
coordinator sends at most one pending outbox item per invocation. Local code
first binds canonical outbox bytes to the immutable SQLite run receipt, then
recomputes exact row, index, and database-payload digests. SQLite triggers
forbid payload updates and outbox deletion. PostgreSQL independently orders
canonical rows with `COLLATE "C"`, reconstructs and hashes each record and
source-content basis, hashes the ordered content index, computes its own row
count and payload digest, and performs every check before considering an exact
replay. Wrong payload/index hashes, changed rows, classification drift, and
conflicting replays fail closed. The admitted numeric domain excludes exponent
notation and negative zero so Python and PostgreSQL JSONB canonical bytes
cannot silently disagree.

Mirror failure leaves the canonical SQLite commit and pending outbox intact.
It must never cause a refetch or a source-row rollback. A mirror receipt does
not make the source connected and does not authorize public read grants.

## Alert and verified offsite preservation

Every handled provenance, collection, commit, or mirror exception before a
canonical receipt creates a per-run/per-stage create-only failure receipt.
Global and per-unit convenience pointers advance monotonically under a
dedicated ledger lock; they are not alert-correlation authority. A canonical
`partial` or `failed` terminal also records `canonical_terminal` there. Both
collection units declare the real alert template in `OnFailure`. With
`FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED=1`, it scans the bounded immutable ledger,
validates the exact failed-unit receipt, creates a deterministic durable claim,
posts one bounded secret-free Slack message, and persists a hash-bound delivery
receipt. A verified delivery receipt makes retry idempotent. A claim without a
delivery receipt is deliberately `indeterminate` and never auto-posts a
possible duplicate; an operator must reconcile Slack and the claim. With the
gate at `0`, it makes no alert network call. Each handler prioritizes the
newest unclaimed receipt so a disabled-window backlog cannot mask the failure
that triggered it; older pending receipts require an explicit bounded operator
replay and are never discarded. Reconcile only one ledger receipt at a time by
starting the matching instantiated unit, then inspecting its journal and new
claim/delivery receipt before deciding whether to repeat:

```bash
sudo systemctl start florida-sfwmd-pending-erp-alert@florida-sfwmd-pending-erp-timer.service.service
# For failures from the manual canary service instead:
sudo systemctl start florida-sfwmd-pending-erp-alert@florida-sfwmd-pending-erp.service.service
```

Stop when the handler reports `already_delivered`; stop immediately and
reconcile externally if it reports `indeterminate`. Do not wrap either command
in an automatic or unbounded loop.

Offsite preservation is not established by installing this commit. With
`FLORIDA_SIGNAL_SFWMD_BACKUP_ENABLED=1`, the backup unit takes a writer-locked
SQLite snapshot and inventories evidence, receipts, failure ledgers, timer
canaries, alert claims/delivery receipts, prior backup receipts, and that
snapshot. It rejects symlinks and more than 50,000 files or 50 GiB, passes
paths through restic's NUL-delimited `--files-from-raw`, uploads one tagged
snapshot to the approved S3 HTTPS repository, and restores it into a private
temporary directory. Missing, changed, symlinked, unsafe, or extra restored
files all fail before every declared byte and SHA-256 can be verified. Only
then does it write a
`FloridaSignalSfwmdOffsiteBackupReceiptV1`. No successful offsite-backup claim
is allowed without a recent verified receipt and independently visible remote
snapshot. The backup unit is not enabled or transitively scheduled by this
package; any recurring backup schedule is a separate deployment decision.

## Failure and no-progress handling

| Condition | Durable result | Operator response |
| --- | --- | --- |
| Gate is `0` | `disabled`; no network or state write | Leave Desk `UNKNOWN / not_connected` |
| Schema/boundary drift or transport failure | Raw attempt bundle plus `failed` production receipt when the bundle can be verified; no source mutation | Inspect evidence; do not retry unboundedly |
| OBJECTID set changes, rejection, or accounting drift | `partial` and `uncommitted`; no source mutation | Treat as incomplete coverage, not absence |
| Stable complete snapshot | `ok` and `unchanged`; no new content version | Healthy observation, explicitly no source progress |
| Empty complete snapshot | `empty`; current identities retired atomically | Confirm upstream contract before accepting absence |
| Receipt-file write interruption | SQLite receipt/outbox remains canonical | Replay the same immutable evidence to recreate the exact file |
| Mirror timeout or contract rejection | Outbox remains pending; local state remains canonical | Diagnose and retry one outbox item; do not refetch |
| Missing/tampered Desk pointer or receipt | Desk returns `UNKNOWN / not_connected` | Repair from canonical receipt only; never infer health |
| Pre-receipt exception | Create-only failure receipt plus atomic failure pointer; no source claim | Reconcile `OnFailure`; never treat silence as green |
| Alert disabled | Failure ledger remains canonical; no claim or network call | Enable only in an approved test window |
| Alert transport fails after durable claim | Claim remains `indeterminate`; no automatic duplicate post | Reconcile Slack and claim manually before any approved repair |
| Backup upload/restore/hash failure | No verified backup receipt | Preserve local evidence; repair offsite route; rerun one bounded verification |

The network transport has a 30-second request timeout, three default retries
(maximum five in code), a 64 MiB response cap, no redirects, and an exact URL
allowlist. The systemd oneshot has a 20-minute upper bound. Do not wrap it in an
unbounded retry loop or use `Persistent=true` to manufacture catch-up runs.

## Rollback and preservation

Set all four gates back to `0` and stop/disable the timer if it was separately
enabled. Preserve all raw evidence, run/failure/alert/backup receipts, timer
canaries, SQLite versions, and mirror receipts; they are audit records, not
rollback debris. The private mirror can be
left unreadable behind forced RLS. Do not drop tables or delete run directories
as an operational rollback.

After rollback, the Desk must remain `not_connected`. If its last natural
receipt is outside the freshness window it will become `STALE`; if the pointer
or receipt cannot be verified it will fail closed to `UNKNOWN`.
