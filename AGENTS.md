# Florida Signal site repository instructions

These instructions apply to this repository and all paths below it.

## Required startup

Before acting in a new Codex chat, read these current-state authorities in order:

1. `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/.worktrees/florida-signal-site-project-state/SYSTEM_STATE_2026-08-30.md`.
2. `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/.worktrees/florida-signal-state-reconciliation/docs/FLORIDA_SIGNAL_START_HERE.md`.
3. `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/.worktrees/florida-signal-state-reconciliation/data/reference/florida_signal_project_state.json`.
4. `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/.worktrees/florida-signal-state-reconciliation/docs/SESSION_HANDOFF_2026-08-30.md`.

Treat the manifest as durable project state, not live health. Verify current operational claims from their declared live receipts; missing health remains `UNKNOWN`.

At task start, state the repository top level, branch, status, HEAD, and `origin`. Run the equivalent of `git rev-parse --show-toplevel`, `git status --short --branch`, `git branch --show-current`, `git log -1 --oneline`, and `git remote get-url origin` before editing.

## Worktree guard

Also inspect `/Users/gillfillan/Documents/FL SIGNAL SITE BUILD` at task start, every 30 minutes during long work, and immediately before any commit, push, merge, deploy, or completion report. Recheck its repository top level, branch, status, HEAD, and `origin`; do the same for the active worktree before a Git or release action.

Assume dirty or untracked files are user work. Preserve them. Do not clean, reset, checkout, restore, stash, overwrite, reformat, stage, or commit unrelated changes. Stop and report any overlap that cannot be safely isolated.

## Current truth

- Fort Lauderdale Preliminary Development Meeting Request (PDMR) records are public. The 27-record research cohort is **frozen**, meaning its roster and adjudication are fixed; the records are not access-locked, and their first-public timestamps remain unresolved.
- PDMR is the first built private Early Radar lane, not the whole product. Sewer/utility capacity, engineering intake, assemblage plus new LLC, lobbyist registrations, and SFWMD remain planned research sensors without connected collectors or evidence contracts.
- The August 30 site and Accela work is pushed on feature branches but is not merged or deployed. A rebuilt local Finder app is not a production deployment. Never describe pushed, built, automated, deployed, validated, or live as interchangeable states.
- Keep the private PDMR-first Newsroom sequence distinct from the public map-first Data Room.

## Mutation and approval boundary

Begin read-only and keep changes within the user's stated scope. Commit or push only when the current task explicitly authorizes it. Merge, deploy, production service restart, timer/cron changes, Edge deployment or secret rotation, database migrations/writes/grant or RLS changes, wet mirrors, queue writes, publication/newsletter sends, and external communications such as the City records request all require explicit owner approval for that specific action. Never infer production authority from permission to edit, test, commit, or push code.
