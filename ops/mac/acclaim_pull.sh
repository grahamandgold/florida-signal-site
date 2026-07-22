#!/bin/bash
# Florida Signal — Acclaim preliminary pull (native Mac, no Claude/node).
# launchd ExecStart. Drives the operator's real Chrome (passes Cloudflare) via AppleScript,
# backfills every missing record date after the verified SFTP feed, oldest-first, with
# per-date state/resume, then upserts to broward_clerk_preliminary. Nonzero exit on failure.
set -uo pipefail

DIR="/Users/gillfillan/Documents/FL SIGNAL SITE BUILD/ops/mac"
LOG="/Users/gillfillan/Library/Logs/florida-acclaim.log"
STATEDIR="/Users/gillfillan/Library/Application Support/FloridaSignal"
STATE="$STATEDIR/acclaim_state.json"
mkdir -p "$STATEDIR"
MAXPAGES="${ACCLAIM_MAX_PAGES:-40}"   # 40 pages x 500 rows = 20,000 rows/day capacity
MAXDATES="${ACCLAIM_MAX_DATES:-8}"

# Secrets: set -a exports sourced KEY=value pairs to child processes (osascript/python).
ENVFILE="$HOME/.florida_signal_supabase_env"
if [ -f "$ENVFILE" ]; then set -a; source "$ENVFILE"; set +a; fi

log(){ echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$LOG"; }

# Log rotation only: roll at 5 MB, retain 3 rotated copies. No other retention system;
# per-date NDJSON cleanup remains tied to verified Supabase insertion (see below).
rotate_log(){
  [ -f "$LOG" ] || return 0
  local size; size=$(stat -f%z "$LOG" 2>/dev/null || echo 0)
  [ "$size" -lt 5242880 ] && return 0
  rm -f "$LOG.3"
  [ -f "$LOG.2" ] && mv "$LOG.2" "$LOG.3"
  [ -f "$LOG.1" ] && mv "$LOG.1" "$LOG.2"
  mv "$LOG" "$LOG.1"
  echo "$(date '+%Y-%m-%d %H:%M:%S') log rotated at ${size} bytes (retaining 3 copies)" >>"$LOG"
}
rotate_log

log "=== acclaim pull start (maxdates=$MAXDATES maxpages=$MAXPAGES) ==="

# 1) Last verified SFTP business date (authoritative floor — we only pull dates AFTER this).
VERIFIED_MAX=$(/usr/bin/python3 - <<'PY'
import json,urllib.request,os
sb=os.environ.get("SUPABASE_URL","https://jrjewmzkyluxdywyusrw.supabase.co").rstrip("/")
key=os.environ.get("SUPABASE_ANON_KEY","sb_publishable_dEyBjKE_vcTj3YYx4p6XvA_xnkVW3Wb")
req=urllib.request.Request(sb+"/rest/v1/broward_clerk_records_run?select=business_date&order=business_date.desc&limit=1")
req.add_header("apikey",key)
try:
    d=json.loads(urllib.request.urlopen(req,timeout=30).read()); print(d[0]["business_date"] if d else "2026-07-10")
except Exception: print("2026-07-10")
PY
)
log "verified SFTP through: $VERIFIED_MAX"

# 2) Candidate dates = (verified_max, today], oldest first, capped. Dates already fully present
#    in the preliminary table (and marked done in state) are skipped; the per-row upsert filter
#    is the final idempotency guard, so a Mac-was-off gap is always backfilled, never skipped.
TARGETS=$(/usr/bin/python3 "$DIR/acclaim_targets.py" "$VERIFIED_MAX" "$MAXDATES" "$STATE")

if [ -z "$TARGETS" ]; then
  log "no missing dates after verified max; backlog empty"; echo "nothing to backfill"; exit 0
fi

FAIL=0
FIRST=""; LAST=""
while IFS= read -r LINE; do
  [ -z "$LINE" ] && continue
  TD="${LINE%%|*}"; ISO="${LINE##*|}"
  [ -z "$FIRST" ] && FIRST="$ISO"
  OUT="/tmp/fs_acclaim_${ISO}.ndjson"; : > "$OUT"
  log "harvest $ISO ($TD)"
  RES=$(/usr/bin/osascript "$DIR/acclaim_harvest.applescript" "$TD" "$OUT" "$MAXPAGES" 2>>"$LOG")
  STATUS="${RES%%|*}"
  PAGES_DONE=$(echo "$RES" | cut -d'|' -f2); PAGES_DONE="${PAGES_DONE:-0}"
  TOTAL_SHOWN=$(echo "$RES" | cut -d'|' -f3); TOTAL_SHOWN="${TOTAL_SHOWN:-0}"
  REASON=$(echo "$RES" | cut -d'|' -f4)
  log "harvest result $ISO: status=$STATUS pages=$PAGES_DONE total=$TOTAL_SHOWN ${REASON:+reason=$REASON}"
  FOUND=$(wc -l < "$OUT" | tr -d ' ')
  INS=0; SKIP=0
  if [ "$FOUND" -gt 0 ]; then
    UPOUT=$(/usr/bin/python3 "$DIR/acclaim_upsert.py" "$OUT" 2>>"$LOG")
    log "upsert $ISO: $UPOUT"
    INS=$(echo "$UPOUT" | grep -oE 'inserted [0-9]+' | grep -oE '[0-9]+' | head -1); INS="${INS:-0}"
    SKIP=$(echo "$UPOUT" | grep -oE 'already present\)?' >/dev/null && echo "$UPOUT" | grep -oE '[0-9]+ already present' | grep -oE '[0-9]+' | head -1 || echo 0); SKIP="${SKIP:-0}"
  fi
  # A date is COMPLETE only when every page was processed and the row count matches the
  # total Acclaim displayed (allowing rows the grid shows without an instrument number).
  DSTATUS=incomplete
  if [ "$STATUS" = "EMPTY" ]; then
    # EMPTY is final only for a date strictly before today. Acclaim can render an empty
    # current-day grid before the county releases that day's recordings.
    if [ "$ISO" = "$(date '+%Y-%m-%d')" ]; then
      FAIL=1
      log "DATE INCOMPLETE $ISO: current-day EMPTY is not a release confirmation"
    else
      DSTATUS=done
    fi
  elif [ "$STATUS" = "OK" ] && [ "$FOUND" -ge "$TOTAL_SHOWN" ]; then
    DSTATUS=done
  else
    FAIL=1
    log "DATE INCOMPLETE $ISO: status=$STATUS found=$FOUND of $TOTAL_SHOWN ${REASON:+($REASON)}"
  fi
  /usr/bin/python3 "$DIR/acclaim_state.py" "$STATE" "$ISO" "$DSTATUS" "$PAGES_DONE" "$FOUND" "$INS" "$VERIFIED_MAX" "$TOTAL_SHOWN" 2>>"$LOG"
  log "date $DSTATUS $ISO: found=$FOUND/$TOTAL_SHOWN inserted=$INS pages=$PAGES_DONE"
  [ "$DSTATUS" = "done" ] && LAST="$ISO"
  rm -f "$OUT" "$OUT.page"
  if [ "$DSTATUS" != "done" ]; then break; fi   # stop; resume this date next run
done <<< "$TARGETS"

log "=== acclaim pull end (fail=$FAIL first=$FIRST last=$LAST) ==="
exit $FAIL
