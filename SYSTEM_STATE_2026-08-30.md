# Florida Signal site + Data Wire checkpoint — 2026-08-30

**Verified:** 2026-08-31 00:31 ET
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
  installed to close a confirmed live false-green. The exact pushed Accela detail scraper was
  subsequently installed with one required import and two functional same-transaction
  owner-mirror/parent-propagation write sites; no existing row,
  timer, cadence or service unit changed and no restart occurred. The reviewed/pushed AI permit
  cleaner was then installed with an SQL write set that excludes `owner_normalized` and
  `contractor_normalized`; Claude's proposed values for those fields remain in its audit JSON.
  Exact response IDs protect row association and atomic batches protect transaction integrity. Its
  allowed classifications remain non-authoritative enrichment, and it was not executed. The cleaner belongs
  to the `florida-intake` lane, not the enrichment service.
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
  This proved the manual receipt path, not ordinary cadence. The later two successful natural
  scheduled runs below separately closed the release-observation gate.
- The first two ordinary receipt runs, `120f38c6-2586-4309-9f72-99ad2b7e442b` at 22:03 ET and
  `3804e4d8-f453-44e2-b2c8-492d53f003b9` at 22:30 ET, each recorded status `failed`, reason
  `one_or_more_attempts_failed; timeout_no_result_state`, 0 observed/new rows and exact
  local/Supabase parity. They are immutable truthful failures, not `source_wait`. Pushed/deployed
  head `2f77630` now retries only that exact transient result-state timeout once in a fresh
  AppleScript invocation; installed script SHA-256 is
  `da33d3adca53582e2e363d49a7fdd63af106bb4b44f975b6123d1d89abef342e`. Two unresolved
  attempts still fail as
  `timeout_no_result_state_after_retry`. No manual post-patch run or cadence change occurred.
- The first natural post-retry observation, run `6a783924-47b3-46ca-a49b-566658f9d681`, advanced
  the LaunchAgent run count from 89 to 90. It started at 23:30:37 ET and completed at 23:31:14
  with exit 0, status `source_wait`, reason `source_not_authoritative_yet`, source result
  `empty_unverified_date` and 0 observed/0 new rows. The exact-timeout retry was exercised once in
  its fresh process and recovered; exact local/Supabase receipt parity was verified. This is the
  first of the two required successful ordinary scheduled observations.
- The second natural post-retry observation, run `c6e02f29-0625-4608-a789-60b52fb8956e`, advanced
  the LaunchAgent run count from 90 to 91 and ran directly from 00:30:04 to 00:30:08 ET with no
  retry warning. It exited 0 with status `source_wait`, reason
  `source_not_authoritative_yet; terms_acceptance_required`, one attempted date (2026-08-30), event
  through 2026-08-28, verified through 2026-08-25 and rows 0/0. Its 692-byte mode-`0600` local
  receipt has SHA-256 `d976e292ef33fbd87a3401b5247c82b170c9155ffb951f6fb284ade42fc3c771`.
  Supabase contains exactly one row for the run; all local fields and outcomes matched, with all 14
  field checks true. This is a truthful terminal source wait, not a relabeled failure. The required
  two-of-two natural release-observation gate is closed on the unchanged cadence.
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
  while enrichment and Supabase sync remained queued. That follow-up pass ended at 23:14:18 with
  wrapper status `SUCCESS_WITH_WORK`, queue before 92,492, selected/attempted 150, completed useful
  0, `not_found` 150, failed 0 and remaining 92,492. It ended early enough for enrichment and the
  waiting normal sync to run; `florida-sync.service` exited successfully at
  23:15:23 ET. Exact Supabase readback then returned 25 expected rows, 25 cloud rows, 25 normalized
  matches, 25 canary-clock matches and an empty mismatch set. A separate global stamp query found
  exactly 25 rows with the canary clock, all 25 expected and zero unexpected. No full backfill, wet
  manual mirror, timer change, rollback or unrelated production write occurred.
- A post-canary audit found 27 newly admitted permits. Twelve had raw owner names and none of those
  twelve had normalized owner names, so the live missing-normalization gap had risen from the
  canary's 97,628 postimage to 97,640. Root cause was the live `scrape_accela_detail.py` path: when
  it later filled a NULL owner/parent, it omitted the deterministic normalization used elsewhere.
  After coverage by the combined 45-test focused suite and compile checks, the exact pushed scraper SHA-256
  `ad56cc0e3435a9dcf6d45cfcca10ab9a147412420a62814e970c0fc85409b612` was atomically installed
  at 23:55 ET with dependency SHA-256 prefix `6dce22` and mode `0664`. The byte-for-byte rollback
  copy is
  `/srv/grahamandgold/florida-signal/backups/scrape_accela_detail.pre_owner_normalization_future_20260831T035347Z.py`
  (old SHA-256 prefix `800936`). The patch adds one required import plus two functional write sites
  used when future detail collection fills a NULL owner/parent; it did not touch any existing row,
  run a backfill, restart the idle service or alter
  its timer/cadence. A read-only recount confirmed the gap remained 97,640 after installation.
- The live preimage of
  `/srv/grahamandgold/florida-signal/app/scripts/ai_clean_permits.py` had SHA-256
  `999c6912f1edf5bfa5b6738af0447ab060de800116eb49dafcfd37bc4e0bffbc`, exactly matching git base
  `85341f1`. After coverage by the combined 45-test focused suite and successful local and remote Python compile checks, the
  reviewed/pushed branch file was atomically installed at about 23:58 ET; live and expected SHA-256
  both equal `352a5ae37a85a08241d19b46b5c2d1becbdb5c1f4a6c04f02d4ee276892cf293`. Backup
  `/srv/grahamandgold/florida-signal/backups/ai_clean_permits.pre_canonical_safety_20260831T035750Z.py`
  retains the exact preimage SHA-256. The live file was verified at 26,699 bytes, mode `0664`,
  owner/group `andy:andy`, with mtime 2026-08-30 23:58:18 ET. The script is scheduled as
  `ai_clean_permits.py --skip-budget` in `/srv/grahamandgold/florida-signal/tools/fs_pipeline.sh intake`;
  live wrapper SHA-256 is
  `4b47f72bb1518e50231f5fc355d6a847d3557d00bb75f83f24d0a4913dc3233f`. Its owning unit is
  `florida-intake.service`, triggered by `florida-intake.timer` at daily
  `OnCalendar=*-*-* 22:00:00`; the AI cleaner is not invoked by `florida-enrich.service`. Read-only
  systemd history proves intake last started at 22:00:02 ET, exited and entered inactive at 22:28:19
  with `Result=success` / `ExecMainStatus=0`, and remained inactive/dead before, through and after
  the 23:58:18 install. Its timer/cadence was untouched. No AI run occurred at install, and there
  was no row mutation, backfill or restart.
- The final pre-safety intake had exercised the old AI identity write path at 22:01:05–22:01:33 ET:
  27/27 targets were cleaned in three batches with zero errors. A privacy-preserving exact-cohort
  audit found 12 valid raw-owner rows, zero normalized owners and 12 differences from the current
  deterministic owner rule; 13 raw contractors had 13 normalized values, with one differing from
  the current deterministic contractor rule. All 27 current owner/contractor results match the
  stored AI proposals. This proves the prior write set affected current identity fields; the safe
  replacement prevents future AI owner/contractor writes but has not had its next natural intake.
- A privacy-preserving whole-corpus comparison against the current deterministic rule found 99,102
  valid owner inputs: 97,502 lack a normalized key and 832 present keys differ. It also found
  101,058 valid contractor inputs: 130 lack a normalized key and 6,262 present keys differ. Nine
  normalized owner rows and 15 normalized contractor rows lack a corresponding raw value. These
  are audit/repair candidates, not proof that every differing historical value is corrupt. No
  identity repair or expanded backfill was authorized or run.
- Production `tools/fs_health_report.py` previously lacked the pushed false-green parser and
  incorrectly reported GREEN. The reviewed health-only file was backed up to
  `/srv/grahamandgold/florida-signal/backups/fs_health_report.pre_false_green_20260831T0310Z.py`
  (old SHA-256 `49e2fae3a2db5cb95cc0d8331a0662fbb3ce8652b5dd6dd106afb4fa98362a9f`) and atomically
  replaced with SHA-256 `019556e9317e9361338eccf1f1a357cf912316fdda699bc8ac91ed39e91ff5d6`.
  The first read-only dry run reported YELLOW with `FALSE GREEN ... 0/49`; after the follow-up pass,
  a second read-only run remained YELLOW and named the latest false green as 0/150 with 150
  `not_found`. The status-aware report initially measured useful Accela coverage at 75.3%, with 12
  `ok` and 1,950 `not_found` outcomes in the preceding 24 hours. No data, collector, timer, restart,
  public-search diagnostic or report send occurred.
- The next naturally scheduled `florida-accela` run began at 2026-08-31 00:00:04 ET and ended at
  00:08:39. Systemd reported `Result=success`, `ExecMainStatus=0` and inactive/dead. Its
  authoritative receipt was `SUCCESS_WITH_WORK`: queue before 92,343, selected 150, attempted 150,
  completed ok 0, `not_found` 150, failed 0, remaining 92,343, rc 0 and elapsed 515 seconds. Exact
  SQLite run-window corroboration found 150 `accela_details` rows, all `not_found`, fetched from
  00:02:26.187671 through 00:08:39.544385, and zero permit owner-field updates. Because there were
  no successful details, the future owner-normalization path was not exercised. The live owner
  counts were 99,240 raw, 1,609 normalized and nine normalized rows with no raw owner; the exact
  raw-owner normalization gap therefore remained 97,640. This is another false useful-success:
  exit 0 does not mean useful progress, and Accela remains YELLOW.

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
  false green; it remained YELLOW after the next 0/150 run. The naturally scheduled 00:00 run then
  also completed 0/150 useful work while systemd and its wrapper reported success. Exact SQLite
  run-window evidence corroborated all 150 outcomes as `not_found`. This fixes observability, not
  the underlying roughly 92,000-row retry backlog; process exit 0 is not useful progress.
- The tracked public-search canary is dry-run only, bounded to 1–25 records, refuses recurring
  systemd invocation, shares the production lock, writes a separate `accela-canary` receipt and
  fails closed on zero successes, hard blocks, incomplete accounting or timeout.
- Permit hardening at `476475614adf8d8850b691209c06f261146dc0d9` makes Claude output
  audit-only for modeled owner/contractor fields, uses exact IDs rather than positional fallback,
  preserves deterministic values, and provides a dry-run-default repair bound by full-universe and
  selected-cohort hashes. Execute performs locked re-scan, compare-and-set writes and exact readback
  atomically; its V2 receipt preserves exact preimages for a targeted rollback. The deployed AI
  cleaner now accepts only exact response IDs, writes each validated batch atomically and stores
  Claude's proposed owner/contractor normalized values only in `ai_clean_json`; it cannot write
  `owner_normalized` or `contractor_normalized`. Its allowed classifications remain
  non-authoritative enrichment. Claude is not the network permit collector; Accela collection uses
  Playwright/httpx and deterministic cleaning remains the required ingestion path.
- The approved canary used the protected backup and receipts above to update exactly 25 rows. Its
  immediate postimage gap was 97,628; subsequent intake and the newly discovered future-row writer
  omission raised the live gap to 97,640. The writer omission is now patched for future
  owner/parent NULL fills, but no existing row or backlog row was changed. Targeted canary rollback
  is available and unrun. Exact normal-mirror Supabase readback and the global clock check are
  complete. The first natural post-patch Accela run had zero detail successes and zero owner-field
  updates, so it did not exercise that future-write path. Exact live counts remain 99,240 raw-owner
  rows, 1,609 normalized rows, nine normalized-without-raw rows and a 97,640 raw-owner gap. Do not
  run a full backfill without a separate owner decision.

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
  transient result-state timeout; they do not satisfy the release gate. Natural run
  `6a783924-47b3-46ca-a49b-566658f9d681` then exited 0 after its one exact-timeout retry recovered,
  recording `source_wait` / `source_not_authoritative_yet`, source result `empty_unverified_date`,
  0 observed/0 new rows and exact local/Supabase parity. Natural run
  `c6e02f29-0625-4608-a789-60b52fb8956e` then exited 0 directly with no retry, recording truthful
  `source_wait` / `source_not_authoritative_yet; terms_acceptance_required`, rows 0/0 and exact
  parity to exactly one Supabase row. These are the two required successful ordinary observations;
  the receipt release gate is closed. The terms-acceptance result explains the empty poll and does
  not manufacture source advancement.
- The Finder Desk was rebuilt and opened locally from site head
  `0a72f53e3a717020eb7d30755c5a559bbb208458` so its separate run, event, verified and
  attempted-through clocks can be inspected. Its exact user-scoped launchd lifecycle, serialized
  rebuild/launch path and strict health response are covered by the pushed hardening. That local
  app state is not a public site deployment.

## Evidence gaps and current priority

- BCPA property coverage is sparse/stale and countywide parcel coverage is partial/stale. FDEP and
  FAA are deterministic sources but still lack durable versioned run ledgers and raw-evidence
  receipts. Verified Clerk also lacks an end-to-end atomic parent/child mirror receipt.
- Stabilize the existing lanes first: the Acclaim two-of-two observation gate is closed; now resolve
  the zero-useful-work Accela backlog without hiding it as systemd success and bound the historical
  deterministic identity repair candidates. The exact 25-row permit cohort is closed with
  authoritative SQLite and normal-mirror Supabase parity. The live raw-owner gap is 97,640; do not
  expand any bounded change into a repair or full backfill without a separate decision. After those
  gates, repair property/
  parcel coverage and add FDEP/FAA receipts before admitting PDMR or building sewer/SFWMD/
  engineering/lobbyist collectors.
- Hold Grok/agent wiring into the Newsroom until the deterministic source contracts and receipts
  are solid. Grok remains an advisory reviewer, not a collector or source of record.

## Production gate status

- The Acclaim release-observation gate is closed by two successful natural post-retry runs with
  exact local/Supabase parity. Preserve the manual canary, two truthful pre-retry failures and both
  natural successes as immutable evidence; keep the existing LaunchAgent plist and cadence.
- The exact 25-row permit postimage is verified in Supabase through the normal dependency chain;
  this gate is closed. The future owner/parent NULL-fill path is patched, but the existing 97,640-row
  gap was deliberately left unchanged and the first natural post-patch run did not exercise the
  path because all 150 detail attempts were `not_found`. Keep the corrected Accela health state
  YELLOW until useful-work receipts improve; systemd/wrapper success alone is insufficient. Do not
  alter the timer/dependency chain, run the remaining full backfill or roll back unless a separate
  decision explicitly requires it.
- Rotate the shared Edge query secret that appeared in request logs; move scheduled calls to named
  secret/header authentication and Vault-backed configuration.
- Revoke public execution of heavy/writing security-definer RPCs and reduce anonymous/authenticated
  source-table grants to intentional read-only access.
- Now that the scheduled Acclaim observation gate has passed, use its durable receipts so successful
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
  dry-run, exactly-25 execute, exact SQLite/Supabase readback and post-write `quick_check` are
  recorded above.
  The health-only deployment retained a byte-for-byte rollback copy; its read-only production
  verification changed the truthful report from GREEN to YELLOW and exposed 0/49 useful work.
  The later future-row scraper patch was covered by the combined 45-test focused suite and compile
  checks, retained its own rollback copy, and was installed while the service was idle; read-only
  verification confirmed it changed no existing data and left the live normalization gap at 97,640.
  The 00:00 natural run then returned systemd/wrapper success but 0/150 useful results; exact SQLite
  corroboration found all 150 `not_found` and zero owner-field updates, so the future normalization
  branch remained unexercised and Accela remained YELLOW.
  The production AI-cleaner safety file was covered by the combined 45-test focused suite plus local and
  remote Python compile checks and was atomically installed with exact expected hash and a byte-for-byte
  backup. Its live size, mode, `andy:andy` ownership and mtime were verified. Read-only systemd
  history confirms its owning intake service—not the enrichment service—had completed successfully
  at 22:28:19 ET and remained inactive/dead throughout the later install. The unchanged daily 22:00
  intake timer did not run at install, and no post-install natural intake has exercised the file yet.
- Acclaim receipt work through `2f77630` passed the full 55-test Python suite, 14 resilience tests,
  29 focused tests and 96
  JavaScript safety checks; Bash syntax, Python compile, inline JavaScript parse and diff checks
  were clean.
- PDMR reconciliation passed 99 relevant tests, including plan snapshot integrity, dry-run and
  approval gates, bounded resumable exact-ID fetch behavior, malformed/ambiguous-folio blocking,
  receipt validation and whole-stage admission parity.
- Acclaim migration/manual parity, two truthful pre-patch scheduled failure receipts and both
  successful natural post-retry scheduled receipts with exact local/Supabase parity, the complete
  local-to-Supabase permit canary and the corrected YELLOW Accela health report are confirmed.
  The Acclaim release gate is closed; resolution of the Accela zero-useful-work and deterministic
  identity-audit backlogs remains pending. This documentation checkpoint itself remains a separate,
  not-yet-committed worktree change.
