# Florida Signal site repository instructions

These instructions apply to this repository and all paths below it.

## Required startup

Before acting in a new Codex chat, read these current-state authorities in order:

1. `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/.worktrees/florida-signal-site-project-state/SYSTEM_STATE_2026-08-30.md`.
2. `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/.worktrees/florida-signal-state-reconciliation/docs/FLORIDA_SIGNAL_START_HERE.md`.
3. `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/.worktrees/florida-signal-state-reconciliation/data/reference/florida_signal_project_state.json`.
4. `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/.worktrees/florida-signal-state-reconciliation/docs/SESSION_HANDOFF_2026-08-30.md`.

Treat the manifest as durable project state, not live health. Verify current operational claims from their declared live receipts; missing health remains `UNKNOWN`.

When work materially changes source coverage, automation, production state, release state, safety
gates, or the current priority, update this checkpoint and the canonical state authorities in the
same workstream before reporting completion. If an authority cannot be updated safely, report the
drift explicitly instead of leaving a silent contradiction.

At task start, state the repository top level, branch, status, HEAD, and `origin`. Run the equivalent of `git rev-parse --show-toplevel`, `git status --short --branch`, `git branch --show-current`, `git log -1 --oneline`, and `git remote get-url origin` before editing.

## Worktree guard

Also inspect `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD` at task start, every 30 minutes during long work, and immediately before any commit, push, merge, deploy, or completion report. Recheck its repository top level, branch, status, HEAD, and `origin`; do the same for the active worktree before a Git or release action.

Assume dirty or untracked files are user work. Preserve them. Do not clean, reset, checkout, restore, stash, overwrite, reformat, stage, or commit unrelated changes. Stop and report any overlap that cannot be safely isolated.

## Current truth

- Fort Lauderdale Preliminary Development Meeting Request (PDMR) records are public. The 27-record research cohort is **frozen**, meaning its roster and adjudication are fixed; the records are not access-locked, and their first-public timestamps remain unresolved.
- PDMR is the first built private Early Radar lane, not the whole product. Sewer/utility capacity, engineering intake, assemblage plus new LLC, lobbyist registrations, and SFWMD remain planned research sensors without connected collectors or evidence contracts.
- Production Supabase has no PDMR table, function, cron, mirror, or queue. The research archive has 329 unique PDMRs: 30 have current raw receipts, 299 lack current raw receipts, and eight have malformed folios. Do not guess or silently repair folios.
- Fail-closed PDMR reconciliation is pushed on `codex/pdmr-reconciliation-admission-2026-08-30` at `364917770f638726f653c72809e2908812040055`. It has not been run or deployed: no stage was initialized, no network fetch occurred, and no production write occurred. Its plan preserves the exact 329-ID set, copies only the 30 independently current receipts, requires exact-ID re-observation for the other 299, blocks malformed/ambiguous folios, and requires whole-stage parity before admission.
- Permit normalization hardening is pushed on `codex/accela-health-truth-2026-08-30` at `40f5f1058cb0073da3189970169c3a3466fdb0d7`; it is not deployed. The current audit found 97,653 raw owner rows without `owner_normalized`.
- Acclaim collector-health receipts are pushed on `codex/acclaim-run-receipts-2026-08-30` at `0c99f0e5abf058a58bee9d5cf1a69355fda27cd9`; they are not deployed and their Supabase migration has not been applied. The production LaunchAgent is running hourly. An August 28 event clock is expected over the August 29–30 weekend; the production gap is the absence of durable receipts for successful empty/unchanged polls, not a stopped collector.
- BCPA/property and county-parcel coverage remain sparse or stale, and FDEP/FAA lack durable versioned run ledgers/raw evidence. Treat those as evidence gaps, not healthy connected lanes.
- Every pull must deterministically parse, type-normalize, validate and deduplicate new or changed raw rows and preserve raw evidence plus a versioned run receipt, including empty/unchanged polls. Do not repeatedly re-clean unchanged rows; reprocess only when parser/normalizer versions change. Claude/Grok are optional post-admission audit or enrichment, never collectors, required cleaners or health authorities.
- The current priority is an explicitly approved, bounded canary of existing-source health and normalization work before adding new source pulls or wiring Grok advisors into the Newsroom. Grok remains advisory.
- The August 30 site and data-hardening work is pushed on feature branches but is not merged or deployed. A rebuilt local Finder app is not a production deployment. Never describe pushed, built, automated, deployed, validated, or live as interchangeable states.
- Keep the private PDMR-first Newsroom sequence distinct from the public map-first Data Room.

## Mutation and approval boundary

Begin read-only and keep changes within the user's stated scope. Commit or push only when the current task explicitly authorizes it. Merge, deploy, production service restart, timer/cron changes, Edge deployment or secret rotation, database migrations/writes/grant or RLS changes, wet mirrors, queue writes, publication/newsletter sends, and external communications such as the City records request all require explicit owner approval for that specific action. Never infer production authority from permission to edit, test, commit, or push code.
