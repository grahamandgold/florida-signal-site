#!/bin/bash
# One-time cleanup of VERIFIED manual test artifacts only (Andy-approved 2026-07-19).
# Deletes nothing owned by the production pipeline: no state, logs, credentials, or retry files.
# Verification basis: 2026-07-13 rows confirmed present in Supabase (2,909 unique) and a rerun of
# acclaim_upsert.py reported "all 2909 harvested rows already present" — nothing pending upload.
set -uo pipefail
LOG="$HOME/Library/Logs/florida-acclaim.log"

TARGETS=(/tmp/fs_heavy.ndjson /tmp/fs_heavy.status /tmp/fs_acclaim_test.ndjson /tmp/fs_acclaim_test.log
         /tmp/fs_empty.ndjson /tmp/fs_empty.status /tmp/fs_fail.ndjson /tmp/fs_fail.status
         /tmp/fs_fail_harvest.applescript /tmp/fs_regress.ndjson /tmp/fs_regress.status)

TOTAL=0
echo "=== deleting verified manual test artifacts ==="
for f in "${TARGETS[@]}"; do
  if [ -e "$f" ]; then
    B=$(stat -f%z "$f" 2>/dev/null || echo 0)
    TOTAL=$((TOTAL + B))
    echo "  removing $f (${B} bytes)"
    rm -f "$f"
    echo "$(date '+%Y-%m-%d %H:%M:%S') CLEANUP removed $f (${B} bytes) — verified uploaded" >>"$LOG"
  fi
done
echo "  total bytes removed: $TOTAL"
echo "$(date '+%Y-%m-%d %H:%M:%S') CLEANUP complete: ${TOTAL} bytes of verified manual test artifacts removed; state/logs/credentials/retry files untouched" >>"$LOG"

echo
echo "=== protected files must still exist ==="
for p in "$HOME/Library/Application Support/FloridaSignal/acclaim_state.json" \
         "$HOME/Library/Logs/florida-acclaim.log" \
         "$HOME/Library/Logs/florida-acclaim.launchd.log" \
         "$HOME/.florida_signal_supabase_env"; do
  [ -e "$p" ] && echo "  PRESENT: $p ($(stat -f%z "$p") bytes)" || echo "  *** MISSING: $p ***"
done

echo
echo "=== production temp files (should be none outside a run) ==="
ls /tmp/fs_acclaim_*.ndjson 2>/dev/null || echo "  none — production self-cleans after verified upload"
