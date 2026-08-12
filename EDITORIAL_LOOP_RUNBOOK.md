# Florida Signal — editorial loop runbook

**Live from August 11, 2026 · Record → Candidate → human verification only**

This is the operating contract for the first durable journalistic detector. Collection and
Candidate assembly continue on hosted infrastructure when a laptop, Wi-Fi connection or AI chat
is unavailable. No scheduled job can publish or send email.

## What runs automatically

| Job | Schedule (UTC) | Output | Failure behavior |
|---|---|---|---|
| `property-transfer-refresh` | weekdays 19:20 | refreshed deed/parcel snapshot + aggregate health row | `broward_property_transfer_current` returns no rows if snapshot lag exceeds two business days |
| `transfer-permit-candidates-v1` | daily 03:30 | at most eight new private evidence packets | inserts nothing if the snapshot gate is closed; stable IDs prevent duplicates |
| `florida-clerk-catchup.timer` | weekdays about 18:10 | missing authoritative Clerk business dates, oldest first | complete run-ledger pagination; up to ten dates per run; parent-before-child writes; nonzero failure |

The Clerk source's own release window is a separate clock. A delayed courthouse release is shown
as delayed; it does not make already verified records untrue. A Candidate packet always retains
both event dates and the source/snapshot clocks observed when it was sealed.

## First detector: Transfer → Permit

The detector requires all of the following:

1. verified Clerk deed;
2. Clerk legal-file folio resolved to exactly one official county parcel;
3. Fort Lauderdale permit with a nonempty verified parcel and provenance field;
4. exact equality of the two canonical parcel identifiers;
5. permit application date on or after the deed date and no more than 365 days later; and
6. a native permit value of at least $250,000 or a bounded development-work phrase.

Related structural and trade applications are grouped into one deed/parcel Candidate. Values are
not summed because trade permits can overlap a project's stated scope. The packet preserves every
included source record, exposes the largest native permit-declared value only, and says what
remains unknown.

## Human morning gate

Open the private Data Wire Signal Review desk and review no more than eight packets:

1. confirm the health board has no red snapshot/detector state;
2. open the evidence packet and confirm the SHA receipt says `SEALED`;
3. compare the deed and permit event dates and exact folio;
4. decide `APPROVED`, `HOLD`, `REJECTED` or `NEEDS_MORE_REPORTING`;
5. use the approved publication-role byline; and
6. remember that `APPROVED` publishes nothing. A complete Story Packet and separate human
   Publish and Send gates remain required.

## Checks

Public aggregate health:

```sh
curl -fsS https://api.thefloridasignal.com/api/data-health
```

Database checks from an authorized SQL session:

```sql
select * from public.broward_property_transfer_freshness;
select component, status, event_through, source_through, system_time, detail
from public.editorial_pipeline_health order by component;
select jobname, schedule, active from cron.job
where jobname in ('property-transfer-refresh','transfer-permit-candidates-v1');
select status, start_time, end_time, return_message
from cron.job_run_details
where jobid in (select jobid from cron.job where jobname in
  ('property-transfer-refresh','transfer-permit-candidates-v1'))
order by start_time desc limit 12;
```

## Recovery

- Snapshot stale: run `select internal.refresh_property_transfer_snapshot();`, inspect the
  returned source and snapshot dates, and leave current modules suppressed if it is not current.
- Detector red/suppressed: fix snapshot health first, then run
  `select internal.enqueue_transfer_permit_candidates_v1(8);` once.
- Clerk backlog: inspect `florida-clerk-catchup.service`; do not bypass parent-before-child writes
  or merge preliminary text into the verified tables.
- Bad Candidate: reject or hold it. Never edit source facts inside the sealed packet. A changed
  detector must use a new version and stable ID namespace.

Timestamped production backups from the August 11 deployment remain beside the replaced public
API and Clerk catch-up scripts on the droplet. Database migrations are additive; unschedule the two
named cron jobs first if a rollback is required.
