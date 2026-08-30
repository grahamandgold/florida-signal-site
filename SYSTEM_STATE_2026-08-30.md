# Florida Signal site + Data Wire checkpoint — 2026-08-30

**Verified:** 2026-08-30 19:10 ET  
**Scope:** private Newsroom/Data Explorer, public Data Room behavior, local Finder app, and the
cross-repository Accela health/canary patch.  
**Release state:** pushed branches only. Nothing in this checkpoint was merged to `main`, deployed
to the public site/API, installed on the production droplet, enabled as a timer, or applied to
production Supabase.

## Revisions

- Site branch `codex/project-state-panel-2026-08-23` code through `fa399d2`, plus this
  documentation checkpoint.
- Source/Accela branch `codex/accela-health-truth-2026-08-30` through documentation
  checkpoint `6683f95` (canary `7222ec0`; false-green detection `3c491b5`).
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

## Private Newsroom truth

- Fort Lauderdale **Preliminary Development Meeting Request (PDMR)** records are the first built
  planning-intent lane. They precede permit execution evidence in the private discovery sequence.
- The 27 studied PDMR records are public. The research roster/adjudication is frozen against
  after-the-fact changes; record access is not locked. Historical first-public timing remains
  unresolved, which is the purpose of the prepared City metadata request.
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
- These safeguards are pushed but not deployed. Production behavior remains unchanged until an
  approved release window.

## Production gates still open

- Rotate the shared Edge query secret that appeared in request logs; move scheduled calls to named
  secret/header authentication and Vault-backed configuration.
- Revoke public execution of heavy/writing security-definer RPCs and reduce anonymous/authenticated
  source-table grants to intentional read-only access.
- Add durable per-run receipts so successful zero-row polls, event coverage and collector progress
  are independently visible without scanning source tables.
- Automate/mirror PDMR only after its timing/noise gates, and build the planned sewer/SFWMD/
  engineering/lobbyist collectors only with explicit source, RLS, cadence and evidence contracts.

## Verification receipt

- Site: 96 JavaScript safety checks, 44 Python tests and 25 public browser tests passed; the six
  private browser tests were then rerun against the rebuilt app and passed 6/6.
- Accela: wrapper suite passed, 43 alert-semantic tests passed, seven exit-matrix tests passed, and
  shell syntax/Python compile/diff checks were clean.
- Both pushed worktrees were clean and synchronized after the commits above.
