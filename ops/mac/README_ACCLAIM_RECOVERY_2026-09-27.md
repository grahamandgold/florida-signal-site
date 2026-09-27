# Portable collector recovery — September 27, 2026

The launch agent referenced a removed checkout. Install the reviewed collector and its sibling helpers in an immutable release directory; use the script-relative directory in `acclaim_pull.sh`. Preserve the existing state, receipt outbox, credentials and logs.

This incorporates only the existing receipt collector from `2f77630`, its state helper and tests. It does not merge the donor branch's CMS, desktop or public-page changes. The migration file records the existing production receipt contract; do not reapply without inspecting migration history.

Before launch-agent replacement, back up its plist and state/outbox, unload it, and run a bounded two-date check. One date after noon selects the forming day only. RunAtLoad starts collection immediately after bootstrap. A source wait is not a successful catch-up; retain its terminal receipt and verify a subsequent naturally scheduled run.

Rollback: unload the new job, restore the saved plist, and bootstrap only when its target path is valid. Do not restore old state over new collected records.
