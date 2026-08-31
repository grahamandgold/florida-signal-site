# Florida Signal site + Data Wire checkpoint — 2026-08-30

**Verified:** 2026-08-30 23:10 ET
**Scope:** private Newsroom/Data Explorer, public Data Room behavior, local Finder app, and the
cross-repository Acclaim, Accela/permit-normalization and PDMR evidence audits.
**Release state:** the explicitly approved bounded Acclaim receipt deployment and exactly-25 permit
normalization canary described below were applied. The public site/API was not deployed, no full
permit backfill ran, and no timer, cron or LaunchAgent cadence changed.

## Revisions

- Site branch `codex/project-state-panel-2026-08-23` through pushed UI head
  `757e827bd63b9b9b4c623e30e95cb09ff1f9e91b` and pushed local-app lifecycle head
  `0a72f53e3a717020eb7d30755c5a559bbb208458`, plus this documentation checkpoint.
- Source/Accela branch `codex/accela-health-truth-2026-08-30` through
  `476475614adf8d8850b691209c06f261146dc0d9`; the owner-normalization tool and its deterministic
  dependency were surgically installed for the approved bounded canary without replacing the
  dirty production checkout. The reviewed health-only report file from this branch was later
  installed to close a confirmed live false-green; no collector, timer or service unit changed.
- Acclaim receipt/health branch `codex/acclaim-run-receipts-2026-08-30` through pushed commit
  `2f77630f60e42b64cbf8629bb0bd93bd8dd2bb44`; migration `20260831005904` was applied,
  the collector receipt runtime installed, and the exact transient-result retry installed with the
  existing plist/cadence unchanged.
- PDMR reconciliation branch `codex/pdmr-reconciliation-admission-2026-08-30` through
  `364917770f638726f653c72809e2908812040055` (not run or deployed; no staging database,
  network fetch or production write occurred).
- Canonical source-state branch `codex/state-reconciliation-2026-08-23`; `5afddac` is the
  pushed base before the August 30 reconciliation checkpoint. Read the branch's current `origin`
  head rather than hard-coding a later self-referential documentation hash.
- The local `Florida Signal Data Wire.app` was rebuilt, ad-hoc signed, verified and reopened with
  UI head `757e827bd63b9b9b4c623e30e95cb09ff1f9e91b` plus lifecycle hardening at
  `0a72f53e3a717020eb7d30755c5a559bbb208458`. This is local-only, not a public site/API
  deployment.
- Lifecycle head `0a72f53` serializes launch and rebuild with one lock, addresses the exact
  `gui/<uid>/com.floridasignal.datawire.server` job, bounds job/port waits, never signals a
  launchd-managed or unverified PID, requires the exact green Desk health contract, and proves
  independently overridden project-state/PDMR snapshot files byte-for-byte before bundling them.

## Confirmed bounded production receipts

- Acclaim manual canary run `6ae86e78-0771-4224-a6f4-e09d30ffc833` recorded status
  `source_wait`, attempted date 2026-08-30, event coverage through 2026-08-28, verified coverage
  through 2026-08-25 and 0 observed/0 new rows. Its local and Supabase receipts have exact parity.
  This proves the manual receipt path, not ordinary cadence: state is
  `CANARY_RECEIPT_PATH_VERIFIED / RELEASE_OBSERVATION_PENDING` until two successful normal
  scheduled runs are observed.
- The first two ordinary receipt runs, `120f38c6-2586-4309-9f72-99ad2b7e442b` at 22:03 ET and
  `3804e4d8-f453-44e2-b2c8-492d53f003b9` at 22:30 ET, each recorded status `failed`, reason
  `one_or_more_attempts_failed; timeout_no_result_state`, 0 observed/new rows and exact
  local/Supabase parity. They are immutable truthful failures, not `source_wait`. Pushed/deployed
  head `2f77630` now retries only that exact transient result-state timeout once in a fresh
  AppleScript invocation; installed script SHA-256 is
  `da33d3adca53582e2e363d49a7fdd63af106bb4b44f975b6123d1d89abef342e`. Two unresolved
  attempts still fail as
  `timeout_no_result_state_after_retry`. No manual post-patch run or cadence change occurred.
- Before the permit write, SQLite backup
  `/srv/grahamandgold/florida-signal/backups/permits.pre_owner_normalized_canary_20260831T012956Z.sqlite`
  was created at 11,945,189,376 bytes, SHA-256
  `be4c7d5ded32831a7ebb386e81b4e38b5bb55bb980e4811f7729459d3bcfcde9`, and returned
  `ok` from `quick_check`.
- Dry receipt `owner_normalization_preview_20260831T014229Z.json` has SHA-256
  `c4e3b1e3b6d1f77b60410cb3051779d1a55838a5a61098c651c61a0d49ec9d76`. It selected and
  persisted exactly 25 planned preimages, updated 0 rows, and bound universe SHA-256
  `479566bcd1127156faa8f34396ebf43d37e4095da6b83322769a9a114f1d7fb2` plus selected
  SHA-256 `c5a6aae82ad8f7712bfe8ca3d974f8f9d285bd20c49730dcba1cddf78b9394d1`.
- Execute receipt `owner_normalization_execute_20260831T014322Z.json` has SHA-256
  `db23ed27f14c9e987f93376df8cbdab6ba32025e0b5c45c81271a6f6ee18165c` and status
  `SUCCESS`. One locked transaction updated and exactly read back 25 rows at naive-local mutation
  clock `2026-08-30T21:43:51.194307`; postimage SHA-256 is
  `c0265b53b1007c085c33fc780c47469f8d535159866e34206f7c2f1abeebee7f`. The missing
  normalization count changed exactly from 97,653 to 97,628, live `quick_check` remained `ok`, and
  the permit-ID set did not change. Targeted rollback is ready but was not run.
- The natural 22:00 permit chain fired and intake completed. The 22:40:19–23:05:19 Accela pass then
  ended `BUDGET_EXHAUSTED` with inner rc 124, queue before 92,489, selected 150, attempted 49,
  completed useful 0, `not_found` 49, failed 0 and remaining 92,489. Its wrapper intentionally maps
  budget exhaustion to systemd success under ADR-008. The overdue 23:00 pass started at 23:05:19
  while enrichment and Supabase sync remained queued, so exact cloud readback is delayed behind
  the recurrent detail backlog. No full backfill, wet manual mirror, timer change or unrelated
  production write is authorized or implied by this canary.
- Production `tools/fs_health_report.py` previously lacked the pushed false-green parser and
  incorrectly reported GREEN. The reviewed health-only file was backed up to
  `/srv/grahamandgold/florida-signal/backups/fs_health_report.pre_false_green_20260831T0310Z.py`
  (old SHA-256 `49e2fae3a2db5cb95cc0d8331a0662fbb3ce8652b5dd6dd106afb4fa98362a9f`) and atomically
  replaced with SHA-256 `019556e9317e9361338eccf1f1a357cf912316fdda699bc8ac91ed39e91ff5d6`.
  A read-only dry run now reports YELLOW with `FALSE GREEN ... 0/49`, status-aware useful Accela
  coverage 75.3%, 12 `ok` and 1,950 `not_found` outcomes in 24 hours. No data, collector, timer,
  restart, public-search diagnostic or report send occurred.

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
- The private PDMR table labels its unverified event clock `Portal date`, not `Filed`; the home
  summary says `newest portal date`. The displayed date has not been proven to be a filing date.
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
- The live 22:40 pass confirmed that condition: the wrapper exposed inner rc 124 and
  `BUDGET_EXHAUSTED`, but systemd remained success by the standing ADR while useful completion was
  0/49. Before the reviewed parser was installed, the production report still rendered GREEN.
  After the health-only atomic deploy, the same read-only report renders YELLOW and names the exact
  false green. This fixes observability, not the underlying 92,489-row retry backlog.
- The tracked public-search canary is dry-run only, bounded to 1–25 records, refuses recurring
  systemd invocation, shares the production lock, writes a separate `accela-canary` receipt and
  fails closed on zero successes, hard blocks, incomplete accounting or timeout.
- Permit hardening at `476475614adf8d8850b691209c06f261146dc0d9` makes Claude output
  audit-only for modeled owner/contractor fields, uses exact IDs rather than positional fallback,
  preserves deterministic values, and provides a dry-run-default repair bound by full-universe and
  selected-cohort hashes. Execute performs locked re-scan, compare-and-set writes and exact readback
  atomically; its V2 receipt preserves exact preimages for a targeted rollback. Claude is not the
  network permit collector; Accela collection uses Playwright/httpx and deterministic cleaning
  remains the required ingestion path.
- The approved canary used the protected backup and receipts above to update exactly 25 rows. The
  missing-normalization count is now 97,628, not evidence that a full cleanup occurred. Targeted
  rollback is available and unrun. Do not run a full backfill; wait for the pending Supabase cloud
  readback and a separate owner decision.

## Acclaim collector health

- The production Acclaim LaunchAgent remains loaded on its existing hourly cadence; its plist and
  schedule were not changed. The last non-empty source event date is Friday, August 28, so an
  `8/28` event clock over this weekend does not mean the Mac or collector stopped.
- Supabase migration `20260831005904` is applied and secured, and collector receipt runtime through
  pushed commit `2f77630f60e42b64cbf8629bb0bd93bd8dd2bb44` is installed. It records `ok`,
  `empty`, `source_wait` and `failed` outcomes, separates run/event/verified clocks, and queues failed
  uploads for replay. Its wrapper retries once only when a fresh Acclaim search returns the exact
  transient state `timeout_no_result_state`; every other result remains single-attempt, and two
  unresolved attempts fail truthfully as `timeout_no_result_state_after_retry`.
- Manual canary `6ae86e78-0771-4224-a6f4-e09d30ffc833` proved exact local/Supabase receipt
  parity for a zero-row `source_wait` poll. It did not prove scheduled execution. The 22:03 and
  22:30 ordinary runs also reached exact local/Supabase parity but failed truthfully on the same
  transient result-state timeout; they do not satisfy the release gate. Observe two successful
  ordinary scheduled runs after `2f77630` before declaring the receipt release healthy; until then
  use `CANARY_RECEIPT_PATH_VERIFIED / RELEASE_OBSERVATION_PENDING`.
- The Finder Desk was rebuilt and opened locally from site head
  `0a72f53e3a717020eb7d30755c5a559bbb208458` so its separate run, event, verified and
  attempted-through clocks can be inspected. Its exact user-scoped launchd lifecycle, serialized
  rebuild/launch path and strict health response are covered by the pushed hardening. That local
  app state is not a public site deployment.

## Evidence gaps and current priority

- BCPA property coverage is sparse/stale and countywide parcel coverage is partial/stale. FDEP and
  FAA are deterministic sources but still lack durable versioned run ledgers and raw-evidence
  receipts. Verified Clerk also lacks an end-to-end atomic parent/child mirror receipt.
- Stabilize the existing lanes first: observe two successful ordinary scheduled Acclaim receipt
  runs, resolve the zero-useful-work Accela backlog without hiding it as systemd success, and
  complete the pending Supabase readback for the exact 25-row permit cohort. Do not expand the
  permit repair into a full backfill from this evidence alone. After those gates, repair property/
  parcel coverage and add FDEP/FAA receipts before admitting PDMR or building sewer/SFWMD/
  engineering/lobbyist collectors.
- Hold Grok/agent wiring into the Newsroom until the deterministic source contracts and receipts
  are solid. Grok remains an advisory reviewer, not a collector or source of record.

## Production gates still open

- Observe and verify two successful ordinary scheduled Acclaim runs after the bounded retry patch;
  neither the manual parity canary nor the two truthful pre-patch scheduled failures establishes
  release health. Keep the existing LaunchAgent plist and cadence unchanged.
- Verify the exact 25-row permit postimage in Supabase after the normal dependency chain gets a
  sync window. The current chain is delayed behind recurrent budget-exhausted Accela passes. Do not
  trigger a wet manual mirror, alter the timer/dependency chain, run a full backfill or roll back
  unless a separate decision explicitly requires it.
- Rotate the shared Edge query secret that appeared in request logs; move scheduled calls to named
  secret/header authentication and Vault-backed configuration.
- Revoke public execution of heavy/writing security-definer RPCs and reduce anonymous/authenticated
  source-table grants to intentional read-only access.
- After the scheduled Acclaim observation gate passes, use its durable receipts so successful
  zero-row polls, event coverage and collector progress are independently visible without scanning
  source tables; add equivalent versioned receipts for FDEP/FAA and close the BCPA/parcel evidence
  gaps.
- Reconcile and admit PDMR only after its missing-receipt and malformed-folio gates. Automate its
  private mirror only with explicit source, RLS, cadence and evidence contracts; use the same
  standard before building sewer/SFWMD/engineering/lobbyist collectors.

## Verification receipt

- Site/Desk: 96 JavaScript safety checks and 54 Python tests passed; the six private browser tests
  passed 6/6 against the rebuilt local Finder app at site head
  `0a72f53e3a717020eb7d30755c5a559bbb208458`.
- Accela/permit: wrapper suite passed, 43 alert-semantic tests passed, and shell syntax/Python
  compile/diff checks were clean. The final owner-normalization safety patch passed 26 focused and
  45 related Python tests plus the pipeline and Accela wrapper suites. The production backup,
  dry-run, exactly-25 execute, exact readback and post-write `quick_check` are recorded above.
  The health-only deployment retained a byte-for-byte rollback copy; its read-only production
  verification changed the truthful report from GREEN to YELLOW and exposed 0/49 useful work.
- Acclaim receipt work through `2f77630` passed the full 55-test Python suite, 14 resilience tests,
  29 focused tests and 96
  JavaScript safety checks; Bash syntax, Python compile, inline JavaScript parse and diff checks
  were clean.
- PDMR reconciliation passed 99 relevant tests, including plan snapshot integrity, dry-run and
  approval gates, bounded resumable exact-ID fetch behavior, malformed/ambiguous-folio blocking,
  receipt validation and whole-stage admission parity.
- Acclaim migration/manual parity, two truthful pre-patch scheduled failure receipts, the permit
  local canary and the corrected YELLOW Accela health report are confirmed. Acclaim's two-success
  scheduled observation, resolution of the Accela zero-useful-work backlog and the permit Supabase
  cloud readback remain pending. This documentation checkpoint itself remains a separate,
  not-yet-committed worktree change.
