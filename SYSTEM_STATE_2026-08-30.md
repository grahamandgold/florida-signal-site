# Florida Signal site + Data Wire checkpoint — 2026-08-30

**Verified:** 2026-08-30 20:34 ET
**Scope:** private Newsroom/Data Explorer, public Data Room behavior, local Finder app, and the
cross-repository Acclaim, Accela/permit-normalization and PDMR evidence audits.
**Release state:** pushed branches only. Nothing in this checkpoint was merged to `main`, deployed
to the public site/API, installed on the production droplet, enabled as a timer, or applied to
production Supabase.

## Revisions

- Site branch `codex/project-state-panel-2026-08-23` through pushed pre-checkpoint head `ebd364e`, plus this
  documentation checkpoint.
- Source/Accela branch `codex/accela-health-truth-2026-08-30` through
  `40f5f1058cb0073da3189970169c3a3466fdb0d7` (permit normalization and repair gates;
  not deployed).
- Acclaim receipt/health branch `codex/acclaim-run-receipts-2026-08-30` through
  `0c99f0e5abf058a58bee9d5cf1a69355fda27cd9` (not deployed; migration not applied).
- PDMR reconciliation branch `codex/pdmr-reconciliation-admission-2026-08-30` through
  `364917770f638726f653c72809e2908812040055` (not run or deployed; no staging database,
  network fetch or production write occurred).
- Canonical source-state branch `codex/state-reconciliation-2026-08-23`; `5afddac` is the
  pushed base before the August 30 reconciliation checkpoint. Read the branch's current `origin`
  head rather than hard-coding a later self-referential documentation hash.
- The local `Florida Signal Data Wire.app` was rebuilt, ad-hoc signed, verified and reopened from
  the pushed site code.

## Agent entry points

- Repository-root `AGENTS.md` makes new Codex chats start with this checkpoint and the canonical
  engine START_HERE/manifest/handoff, verify the active and root worktrees, and recheck
  `FL SIGNAL SITE BUILD` every 30 minutes during long work and before Git/release claims.
- The signed-in ChatGPT **Florida Signal Detection** project instruction was replaced with the same
  source-first, public-PDMR, planned-sensor and pushed-not-deployed contract in one line and
  verified after a full page reload. It is convenience context, not project authority.
- The signed-in Grok **Florida Signal Detector** instruction now preserves its adversarial-reviewer
  role while using the same source paths and safety/current-state contract; it was also verified
  after a full page reload. It remains advisory.
- During active Florida Signal work, recheck the root build repository at least every 30 minutes.
  When source coverage, automation, production/release state, safety gates or current priority
  changes materially, update this checkpoint and the canonical state authorities before reporting
  completion; otherwise name the drift explicitly.

## Private Newsroom truth

- Fort Lauderdale **Preliminary Development Meeting Request (PDMR)** records are the first built
  planning-intent lane. They precede permit execution evidence in the private discovery sequence.
- The 27 studied PDMR records are public. The research roster/adjudication is frozen against
  after-the-fact changes; record access is not locked. Historical first-public timing remains
  unresolved, which is the purpose of the prepared City metadata request.
- Production Supabase currently has no PDMR table, function, cron, mirror or queue. The broader
  research archive contains 329 unique PDMRs: 30 have current raw receipts, 299 lack current raw
  receipts, and eight have malformed folios. Missing receipts and malformed folios are admission
  blockers; folios must never be guessed.
- The pushed reconciliation path is fail-closed and dry-run by default. It binds the exact 329-ID
  source snapshot, copies only the 30 independently current receipts into a brand-new stage,
  schedules bounded/resumable exact-ID re-observation for the other 299, and promotes a folio only
  when current source evidence exposes one unique validated 12-character value. A final manifest
  fails unless the stage has exact 329-ID parity, source-bound raw/version/hash receipts and a
  fully passing ledger. The plan has not been executed: there is no stage, network pull, canonical
  admission, Supabase mirror or other production write.
- Data Explorer defaults to the bounded, read-only local PDMR evidence table. It supports paged
  fielded lookup by request ID, folio, address, owner and project.
- Sewer/utility capacity, engineering intake, assemblage + new LLC, lobbyist registrations and
  SFWMD remain research/planned lanes. They have no collector/evidence contract and are not shown
  as connected.
- Availability, freshness and automation are separate. A readable table may be `connected` while
  its collector health is `unknown`; manual and snapshot sources never borrow a green automated
  receipt. Preliminary and verified Clerk cards use distinct source receipts.
- At verification, preliminary Clerk reached 2026-08-28; verified Clerk reached 2026-08-25.
  Those dates describe different evidence levels and must not be collapsed.

## Public Data Room truth

- Public ordering remains map-first, then Now / Places / Property / Watch. PDMR-first applies only
  to the private Newsroom discovery sequence.
- One Refresh Data Room action refreshes permits, meetings, storms and source health. The page also
  refreshes every five minutes while visible and on focus/visibility return.
- Failed live requests render unavailable state, never invented zero counts. A valid successful
  empty meetings response remains distinct from an outage.
- A later failed permit refresh preserves the last good map and labels it unavailable rather than
  destroying the last verified view. Preliminary and verified Clerk clocks remain separate.

## Accela and automation

- The existing Accela detail lane had a false-green condition: repeated runs could exit green while
  producing zero successful detail records. The tracked health report now surfaces latest/24-hour
  ok, propagated, not-found and error counts and marks substantial or three-run zero progress as
  attention.
- The tracked public-search canary is dry-run only, bounded to 1–25 records, refuses recurring
  systemd invocation, shares the production lock, writes a separate `accela-canary` receipt and
  fails closed on zero successes, hard blocks, incomplete accounting or timeout.
- The permit hardening at `40f5f1058cb0073da3189970169c3a3466fdb0d7` makes Claude output
  audit-only for modeled owner/contractor fields, uses exact IDs rather than positional fallback,
  preserves deterministic values and adds a dry-run-default, bounded compare-and-set owner repair
  tool. Claude is not the network permit collector; Accela collection uses Playwright/httpx and
  deterministic cleaning remains the required ingestion path.
- The current production audit found 97,653 permit rows with a raw owner value but no
  `owner_normalized`. The repair and future-write safeguards are pushed but not deployed or run;
  production behavior and data remain unchanged pending an explicitly approved canary.

## Acclaim collector health

- The production Acclaim LaunchAgent is loaded and running on its hourly cadence. Its latest
  August 30 checks completed normally, including an explicit empty Sunday result; August 29 was
  also verified empty. The last non-empty source event date is Friday, August 28, so an `8/28`
  event clock over this weekend does not mean the Mac or collector stopped.
- The defect is observability: successful empty or unchanged polls do not yet leave a durable
  Supabase run receipt, so a fresh collector check can look stale when inferred only from inserted
  source rows. The pushed receipt patch records `ok`, `empty`, `source_wait` and `failed` outcomes,
  separates run/event/verified clocks, and queues failed uploads for replay.
- Acclaim receipt code at `0c99f0e5abf058a58bee9d5cf1a69355fda27cd9` is pushed only. Its
  Supabase migration has not been applied, its collector wrapper has not been installed, and the
  site has not been deployed. No service restart or timer change is warranted solely because the
  latest event date is August 28.

## Evidence gaps and current priority

- BCPA property coverage is sparse/stale and countywide parcel coverage is partial/stale. FDEP and
  FAA are deterministic sources but still lack durable versioned run ledgers and raw-evidence
  receipts. Verified Clerk also lacks an end-to-end atomic parent/child mirror receipt.
- Stabilize the existing lanes first: approve and execute bounded canaries for Acclaim run receipts
  and permit-owner normalization, with exact readback and rollback evidence. Then repair property/
  parcel coverage and add FDEP/FAA receipts before admitting PDMR or building sewer/SFWMD/
  engineering/lobbyist collectors.
- Hold Grok/agent wiring into the Newsroom until the deterministic source contracts and receipts
  are solid. Grok remains an advisory reviewer, not a collector or source of record.

## Production gates still open

- Obtain separate owner approval for the Acclaim migration/collector/site canary and for the
  permit deployment/dry-run/backup/bounded owner-normalization canary. Pushed code is not
  production authority.
- Rotate the shared Edge query secret that appeared in request logs; move scheduled calls to named
  secret/header authentication and Vault-backed configuration.
- Revoke public execution of heavy/writing security-definer RPCs and reduce anonymous/authenticated
  source-table grants to intentional read-only access.
- Apply the approval-gated Acclaim receipt design so successful zero-row polls, event coverage and
  collector progress are independently visible without scanning source tables; add equivalent
  versioned receipts for FDEP/FAA and close the BCPA/parcel evidence gaps.
- Reconcile and admit PDMR only after its missing-receipt and malformed-folio gates. Automate its
  private mirror only with explicit source, RLS, cadence and evidence contracts; use the same
  standard before building sewer/SFWMD/engineering/lobbyist collectors.

## Verification receipt

- Site: 96 JavaScript safety checks, 44 Python tests and 25 public browser tests passed; the six
  private browser tests were then rerun against the rebuilt app and passed 6/6.
- Accela: wrapper suite passed, 43 alert-semantic tests passed, seven exit-matrix tests passed, and
  shell syntax/Python compile/diff checks were clean. The permit-normalization hardening added 29
  focused passing tests and its pipeline wrapper passed, including the partial/budget exit path.
- Acclaim receipt work passed 55 Python tests, 11 resilience tests, 11 focused tests and 96
  JavaScript safety checks; Bash syntax, Python compile, inline JavaScript parse and diff checks
  were clean.
- PDMR reconciliation passed 99 relevant tests, including plan snapshot integrity, dry-run and
  approval gates, bounded resumable exact-ID fetch behavior, malformed/ambiguous-folio blocking,
  receipt validation and whole-stage admission parity.
- The permit and Acclaim feature worktrees were clean and synchronized after their pushed commits.
  This documentation checkpoint itself remains a separate, not-yet-committed worktree change.
