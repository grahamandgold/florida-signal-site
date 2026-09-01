# Utility and engineering intake production runbook

## What this lane is

This lane makes five exact Fort Lauderdale Accela record-number families
visible and independently verifiable in the private Data Desk:

- `ENG-CR` — water/wastewater capacity requests
- `ENG-OAA` — outside-agency engineering intake
- `ROW-SEW` — sewer right-of-way work
- `ROW-WTR` — water right-of-way work
- `PLB-SEWCP-WT` — sewer-cap walk-through records

It is a derived evidence view over the existing Accela collector, canonical
SQLite database, and existing Supabase `permits` mirror. It is **not** a
second source transport, does not search a separate utility inbox, and cannot
identify the serving utility when the source row does not say so. It makes no
claim that these records precede PDMR or a permit application.

The existing Accela pipeline performs the source collection and deterministic
field cleaning. This lane adds an exact-family classifier, immutable evidence
bundle, complete SQLite-to-Supabase count/primary-key/row-hash parity proof for
the declared 16-column mirror projection, two-read remote stability proof,
sanitized health pointer, and private Desk views. It writes no permit row,
score, Candidate, Signal, story, or public output.

## Production paths

- Canonical SQLite: `/srv/grahamandgold/florida-signal/staging/db/permits.sqlite`
- Canonical writer lock: `/srv/grahamandgold/florida-signal/app/db/.writer.lock`
- Evidence bundles: `/srv/grahamandgold/florida-signal/staging/data/utility-intake/runs/`
- Verification/outcome receipts: `/srv/grahamandgold/florida-signal/staging/data/utility-intake/receipts/`
- Latest pointer: `/srv/grahamandgold/florida-signal/staging/data/utility-intake/latest.json`
- Dedicated credentials: `/srv/grahamandgold/florida-signal/secrets/florida-utility-intake.env` (root:root, mode `0600`, exactly two variables)
- Bounded dependency wait: `/srv/grahamandgold/florida-signal/tools/florida-utility-intake-wait.sh`
- Sanitized mutable health pointer: Supabase `editorial_pipeline_health`, component `utility-intake`
- Timer: minute 27 and 57 of every hour, after the normal Accela and Supabase sync lanes

## Hard stops

- Do not deploy if `scripts/utils/config.py` or `scripts/utils/db.py` differ
  from the reviewed checkout used by `utility_intake_shadow.py`.
- Do not add broad `ENG-`, `ROW-`, `PLB-`, or `TMP-` matching.
- Do not admit dotted `ENG-CR` or `ENG-OAA` subrecords.
- Do not call the source network from this lane.
- Do not create a second Supabase source table or write source rows.
- Do not show `CONNECTED` unless the receipt is successful, complete parity
  passed, the health readback matches, and the private Desk endpoint returns
  the exact same family boundary.
- Stop on duplicates, pagination-cap exhaustion, SQLite instability, writer
  lock contention, schema drift, parity mismatch, receipt failure, health
  readback mismatch, or missing service credentials.
- A `current` Desk label additionally requires the displayed all-family mirror
  proof to match the receipt metrics, a declared verification-receipt path/hash,
  and a system clock no more than 75 minutes old. Otherwise show
  `stale`, `unverified`, or `unknown`.

## 1. Preview and preserve the current state

Record without printing secrets:

```bash
systemctl is-active florida-accela.service florida-sync.service
systemctl is-enabled florida-accela.timer florida-sync.timer
sha256sum /srv/grahamandgold/florida-signal/staging/db/permits.sqlite
sqlite3 -readonly /srv/grahamandgold/florida-signal/staging/db/permits.sqlite \
  "pragma quick_check; select substr(permit_number,1,instr(substr(permit_number,5),'-')+3),count(*) from permits where permit_number like 'ENG-%' or permit_number like 'ROW-%' or permit_number like 'PLB-%' group by 1 order by 1;"
```

The broad-prefix count is diagnostic only. The reviewed Python classifier is
the admission boundary. Preserve the current script, unit, and Desk files in
a new mode-0700 backup directory before overwriting any existing path.

## 2. Install disabled and verify on Linux

Install the reviewed files as:

```text
ops/droplet/utility_intake_shadow.py     -> app/scripts/utility_intake_shadow.py
ops/droplet/utility_intake_production.py -> app/scripts/utility_intake_production.py
ops/droplet/florida-utility-intake-wait.sh -> tools/florida-utility-intake-wait.sh
ops/droplet/florida-utility-intake.service -> /etc/systemd/system/florida-utility-intake.service
ops/droplet/florida-utility-intake.timer   -> /etc/systemd/system/florida-utility-intake.timer
```

Then:

```bash
sudo install -o root -g root -m 0755 /reviewed/path/florida-utility-intake-wait.sh /srv/grahamandgold/florida-signal/tools/florida-utility-intake-wait.sh
sudo systemd-analyze verify /etc/systemd/system/florida-utility-intake.service /etc/systemd/system/florida-utility-intake.timer
sudo systemctl daemon-reload
sudo systemctl disable --now florida-utility-intake.timer
systemctl is-enabled florida-utility-intake.timer
```

Create the dedicated EnvironmentFile from
`ops/droplet/florida-utility-intake.env.example` with exactly `SUPABASE_URL`
and `SUPABASE_SERVICE_ROLE_KEY`; install it root-owned mode `0600` and never
print either value. Do not reuse the shared application `.env`. Confirm the existing
`editorial_pipeline_health` table permits the service role to upsert and read
one `utility-intake` row. No DDL is required by this lane.

## 3. Manual live canary

Keep the timer disabled. Start the unit once after the ordinary Accela and
sync jobs have completed:

```bash
sudo systemctl start florida-utility-intake.service
systemctl show florida-utility-intake.service -p Result -p ExecMainStatus -p ActiveState
sudo journalctl -u florida-utility-intake.service -n 100 --no-pager
sudo jq . /srv/grahamandgold/florida-signal/staging/data/utility-intake/latest.json
```

Follow the pointer, hash the immutable outcome receipt, follow its
`verification.receipt_path`, and hash that immutable verification receipt.
Require:

- exit code zero and outcome `status=ok`;
- no SQLite or Supabase source-row writes;
- exact family accounting with zero duplicate identities;
- complete SQLite/Supabase counts equal;
- complete primary-key-set SHA-256 equal;
- complete declared 16-column projection-rowset SHA-256 equal;
- two complete remote reads with identical count, PK set and projection hash;
- a read-back-verified `editorial_pipeline_health` row with `status=current`;
- health metrics that bind the immutable verification receipt path and hash.

The number of records is discovered by the canary; do not hard-code a stale
expected count into the deployment decision.

## 4. Deploy and verify the private Desk

Deploy the independently reviewed `cms/server.py` and `cms/data.html` through
the existing Data Desk release process. Confirm the service-role key remains
server-only. Verify both views:

- **Sewer + utility intake:** `ENG-CR`, `ROW-SEW`, `ROW-WTR`, `PLB-SEWCP-WT`
- **Outside-agency engineering intake:** parent `ENG-OAA` only

The rows, search, explicit-empty pagination, exact record count, event clock,
collection clock, health detail and receipt-binding state must render. Dotted
`ENG-CR`/`ENG-OAA`, broad `ENG`/`TMP`, and
unclassified records must not render. A failed or absent health receipt must
show warning/unknown, never green.

## 5. Enable and prove a natural run

```bash
sudo systemctl enable --now florida-utility-intake.timer
systemctl list-timers --all florida-utility-intake.timer
```

Wait for a timer-triggered run, then repeat the receipt-chain, complete parity,
health readback, and Desk checks. A manual canary alone is not completion.
The unit's `OnFailure=florida-healthreport.service` hook must be installed and
observable in `systemctl cat`.

## Non-destructive rollback

Disable the utility timer and restore only the backed-up script/unit/Desk
files. Do not delete evidence bundles, receipts, the latest pointer, the
health history available in logs, Accela rows, Supabase rows, or user work.
