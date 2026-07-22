#!/bin/bash
# Read-only inventory of every local path the Acclaim pipeline touches. Deletes nothing.
echo "=== 1. /tmp harvest + test artifacts ==="
ls -la /tmp/fs_acclaim* /tmp/fs_heavy* 2>/dev/null || echo "  (none present)"
echo
echo "=== 2. logs ==="
ls -la "$HOME/Library/Logs/"florida-acclaim* 2>/dev/null || echo "  (none)"
for f in "$HOME/Library/Logs/florida-acclaim.log" "$HOME/Library/Logs/florida-acclaim.launchd.log"; do
  [ -f "$f" ] && echo "  $f  lines=$(wc -l < "$f" | tr -d ' ')  first=$(head -1 "$f" | cut -c1-19)  last=$(tail -1 "$f" | cut -c1-19)"
done
echo
echo "=== 3. state dir ==="
ls -la "$HOME/Library/Application Support/FloridaSignal/" 2>/dev/null || echo "  (none)"
echo
echo "=== 4. secrets file (metadata only, no values) ==="
ls -l "$HOME/.florida_signal_supabase_env" 2>/dev/null | awk '{print "  mode="$1" owner="$3" bytes="$5" name="$9}'
echo
echo "=== 5. screenshots / HTML captures ==="
ls /tmp/*.png /tmp/*.html 2>/dev/null | grep -iE 'acclaim|clerk' || echo "  none — harvester writes no screenshots or HTML"
echo
echo "=== 6. lock files ==="
ls /tmp/*acclaim*.lock "$HOME/Library/Application Support/FloridaSignal/"*.lock 2>/dev/null || echo "  none — no lock files used"
echo
echo "=== 7. cleanup behaviour in code (does success delete raw files?) ==="
grep -n 'rm -f' "/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/ops/mac/acclaim_pull.sh"
echo
echo "=== 8. totals ==="
echo -n "  /tmp acclaim artifacts: "; du -ch /tmp/fs_acclaim* /tmp/fs_heavy* 2>/dev/null | tail -1 || echo "0"
echo -n "  logs: "; du -ch "$HOME/Library/Logs/"florida-acclaim* 2>/dev/null | tail -1
echo -n "  state: "; du -ch "$HOME/Library/Application Support/FloridaSignal/" 2>/dev/null | tail -1
