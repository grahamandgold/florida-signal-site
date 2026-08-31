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
LOCKDIR="$STATEDIR/acclaim.lock"
RECEIPT_OUTBOX="$STATEDIR/acclaim_run_receipts"
mkdir -p "$STATEDIR"
MAXPAGES="${ACCLAIM_MAX_PAGES:-40}"   # 40 pages x 500 rows = 20,000 rows/day capacity
MAXDATES="${ACCLAIM_MAX_DATES:-8}"
HARVEST_TIMEOUT="${ACCLAIM_HARVEST_TIMEOUT:-1200}"

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

acquire_lock(){
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo "$$" >"$LOCKDIR/pid"
    return 0
  fi
  local owner=""
  [ -f "$LOCKDIR/pid" ] && owner=$(tr -dc '0-9' <"$LOCKDIR/pid")
  if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
    return 1
  fi
  log "RECOVERY: reclaiming stale Acclaim lock${owner:+ from pid $owner}"
  rm -f "$LOCKDIR/pid"
  rmdir "$LOCKDIR" 2>/dev/null || return 1
  mkdir "$LOCKDIR" 2>/dev/null || return 1
  echo "$$" >"$LOCKDIR/pid"
}
if ! acquire_lock; then
  log "SKIP: another Acclaim pull is already running"
  exit 0
fi

utc_now(){
  /usr/bin/python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat())'
}
RUN_ID=$(/usr/bin/python3 -c 'import uuid; print(uuid.uuid4())')
RUN_STARTED_AT=$(utc_now)
RECEIPT_OUTCOMES="/tmp/fs_acclaim_run_${RUN_ID}.ndjson"
: > "$RECEIPT_OUTCOMES"
RECEIPT_FINALIZED=0
RECEIPT_BACKLOG=0
VERIFIED_MAX=""

finalize_receipt(){
  local run_status="$1"
  local run_reason="${2:-}"
  local completed receipt_output receipt_rc
  [ "$RECEIPT_FINALIZED" -eq 0 ] || return 0
  completed=$(utc_now)
  local args=(
    record
    --run-id "$RUN_ID"
    --started-at "$RUN_STARTED_AT"
    --completed-at "$completed"
    --outcomes-file "$RECEIPT_OUTCOMES"
    --state-file "$STATE"
    --outbox-dir "$RECEIPT_OUTBOX"
    --status "$run_status"
  )
  [ -n "$VERIFIED_MAX" ] && args+=(--verified-through "$VERIFIED_MAX")
  [ -n "$run_reason" ] && args+=(--reason "$run_reason")
  receipt_output=$(/usr/bin/python3 "$DIR/acclaim_run_receipt.py" "${args[@]}" 2>>"$LOG")
  receipt_rc=$?
  log "run receipt: ${receipt_output:-no result}"
  RECEIPT_FINALIZED=1
  return "$receipt_rc"
}

cleanup(){
  rm -f "$LOCKDIR/pid"
  rmdir "$LOCKDIR" 2>/dev/null || true
  rm -f "$RECEIPT_OUTCOMES"
}
trap cleanup EXIT
trap 'finalize_receipt failed signal_INT || true; exit 130' INT
trap 'finalize_receipt failed signal_TERM || true; exit 143' TERM

log "=== acclaim pull start (maxdates=$MAXDATES maxpages=$MAXPAGES) ==="
if ! /usr/bin/python3 "$DIR/acclaim_run_receipt.py" flush --outbox-dir "$RECEIPT_OUTBOX" >>"$LOG" 2>>"$LOG"; then
  RECEIPT_BACKLOG=1
  log "WARNING: one or more prior Acclaim receipts remain queued for retry"
fi

# 1) Last verified SFTP business date (authoritative floor — we only pull dates AFTER this).
# A transient query failure retains the last known floor; it must never rewind to an old
# hard-coded date and pointlessly re-harvest an already verified week.
if ! VERIFIED_MAX=$(/usr/bin/python3 "$DIR/acclaim_verified_max.py" "$STATE" 2>>"$LOG") || [ -z "$VERIFIED_MAX" ]; then
  log "FATAL: unable to resolve a safe verified SFTP floor"
  finalize_receipt failed verified_floor_unavailable || true
  exit 1
fi
log "verified SFTP through: $VERIFIED_MAX"

# 2) Candidate dates = (verified_max, today], oldest first, capped. Completed past dates are
#    skipped. After noon, today is deliberately re-harvested every run because the public grid
#    can grow during the day; the per-row upsert filter inserts only new instrument numbers.
#    One target slot is reserved for today so an offline backlog cannot starve same-day intel.
if ! TARGETS=$(/usr/bin/python3 "$DIR/acclaim_targets.py" "$VERIFIED_MAX" "$MAXDATES" "$STATE"); then
  log "FATAL: unable to select Acclaim target dates"
  finalize_receipt failed target_selection_failed || true
  exit 1
fi

if [ -z "$TARGETS" ]; then
  log "no missing dates after verified max; backlog empty"
  NO_TARGET_STATUS=ok; NO_TARGET_REASON=no_targets
  if [ "$RECEIPT_BACKLOG" -ne 0 ]; then
    NO_TARGET_STATUS=failed; NO_TARGET_REASON=prior_receipt_replay_failed
  fi
  if ! finalize_receipt "$NO_TARGET_STATUS" "$NO_TARGET_REASON"; then
    log "FATAL: run receipt remains queued; remote receipt write failed"
    exit 1
  fi
  [ "$RECEIPT_BACKLOG" -eq 0 ] || exit 1
  echo "nothing to backfill"
  exit 0
fi

FAIL=0; DEGRADED=0
FIRST=""; LAST=""; SAW_ROWS=0
while IFS= read -r LINE; do
  [ -z "$LINE" ] && continue
  TD="${LINE%%|*}"; ISO="${LINE##*|}"
  [ -z "$FIRST" ] && FIRST="$ISO"
  OUT="/tmp/fs_acclaim_${ISO}.ndjson"; : > "$OUT"
  log "harvest $ISO ($TD)"
  # Bound Chrome/AppleScript hangs. The helper always converts a timeout or automation
  # exception into the same structured status contract used by the harvester.
  RES=$(/usr/bin/python3 - "$HARVEST_TIMEOUT" "$DIR/acclaim_harvest.applescript" "$TD" "$OUT" "$MAXPAGES" 2>>"$LOG" <<'PY'
import subprocess, sys
timeout = int(sys.argv[1])
command = ["/usr/bin/osascript", *sys.argv[2:]]
try:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
except subprocess.TimeoutExpired:
    print("INCOMPLETE|0|0|harvest_timeout_%ss" % timeout)
    raise SystemExit(0)
if result.stderr:
    print(result.stderr, file=sys.stderr, end="")
status = result.stdout.strip()
if "Executing JavaScript through AppleScript is turned off" in result.stderr:
    print("SOURCE_WAIT|0|0|javascript_from_apple_events_disabled")
elif result.returncode:
    print("INCOMPLETE|0|0|browser_automation_exit_%d" % result.returncode)
elif not status:
    print("INCOMPLETE|0|0|browser_automation_empty_status")
else:
    print(status)
PY
)
  STATUS="${RES%%|*}"
  PAGES_DONE=$(echo "$RES" | cut -d'|' -f2); PAGES_DONE="${PAGES_DONE:-0}"
  TOTAL_SHOWN=$(echo "$RES" | cut -d'|' -f3); TOTAL_SHOWN="${TOTAL_SHOWN:-0}"
  REASON=$(echo "$RES" | cut -d'|' -f4)
  log "harvest result $ISO: status=$STATUS pages=$PAGES_DONE total=$TOTAL_SHOWN ${REASON:+reason=$REASON}"
  SOURCE_OBSERVED_AT=$(utc_now)
  FOUND=$(wc -l < "$OUT" | tr -d ' ')
  INS=0
  if [ "$FOUND" -gt 0 ]; then
    SAW_ROWS=1
    if UPOUT=$(/usr/bin/python3 "$DIR/acclaim_upsert.py" "$OUT" 2>>"$LOG"); then
      log "upsert $ISO: $UPOUT"
      INS=$(echo "$UPOUT" | grep -oE 'inserted [0-9]+' | grep -oE '[0-9]+' | head -1); INS="${INS:-0}"
    else
      STATUS=INCOMPLETE
      REASON=upsert_failed
      log "FATAL: preliminary upsert failed for $ISO"
    fi
  fi
  # A date is COMPLETE only when every page was processed and the row count matches the
  # total Acclaim displayed (allowing rows the grid shows without an instrument number).
  DSTATUS=incomplete
  CONTINUE_AFTER=0
  if [ "$STATUS" = "EMPTY" ]; then
    # Acclaim can positively render an empty grid before Broward has released a weekday.
    # Keep every unverified weekday retryable; only a past weekend (or a date already
    # covered by the authoritative SFTP floor) is safe to close as a real zero.
    EMPTY_POLICY=$(/usr/bin/python3 "$DIR/acclaim_empty_policy.py" "$ISO" "$VERIFIED_MAX" 2>>"$LOG")
    if [ "$EMPTY_POLICY" != "done" ]; then
      DSTATUS=source_wait
      DEGRADED=1
      CONTINUE_AFTER=1
      log "DATE DEGRADED $ISO: EMPTY is not authoritative beyond verified floor $VERIFIED_MAX"
    else
      DSTATUS=done
    fi
  elif [ "$STATUS" = "SOURCE_WAIT" ]; then
    # Expected source-side/operator gate: preserve backlog and freshness warning, but do not
    # claim the optional collector process crashed or poison the core pipeline's service state.
    DSTATUS=source_wait
    DEGRADED=1
    log "DATE DEGRADED $ISO: ${REASON:-source_wait}"
  elif [ "$STATUS" = "OK" ] && [ "$FOUND" -ge "$TOTAL_SHOWN" ]; then
    DSTATUS=done
  else
    FAIL=1
    log "DATE INCOMPLETE $ISO: status=$STATUS found=$FOUND of $TOTAL_SHOWN ${REASON:+($REASON)}"
  fi
  RECEIPT_STATUS=failed
  RECEIPT_REASON="$REASON"
  if [ "$DSTATUS" = "done" ] && [ "$STATUS" = "EMPTY" ]; then
    RECEIPT_STATUS=empty
  elif [ "$DSTATUS" = "done" ]; then
    RECEIPT_STATUS=ok
  elif [ "$DSTATUS" = "source_wait" ]; then
    RECEIPT_STATUS=source_wait
    [ -n "$RECEIPT_REASON" ] || RECEIPT_REASON=empty_unverified_date
  fi
  if ! /usr/bin/python3 "$DIR/acclaim_state.py" "$STATE" "$ISO" "$DSTATUS" "$PAGES_DONE" "$FOUND" "$INS" "$VERIFIED_MAX" "$TOTAL_SHOWN" 2>>"$LOG"; then
    FAIL=1
    RECEIPT_STATUS=failed
    RECEIPT_REASON=state_write_failed
    log "FATAL: unable to persist local Acclaim state for $ISO"
  fi
  OBSERVED_AT="$SOURCE_OBSERVED_AT"
  APPEND_ARGS=(
    append
    --outcomes-file "$RECEIPT_OUTCOMES"
    --target-date "$ISO"
    --status "$RECEIPT_STATUS"
    --pages "$PAGES_DONE"
    --rows-observed "$FOUND"
    --rows-new "$INS"
    --observed-at "$OBSERVED_AT"
  )
  [ -n "$RECEIPT_REASON" ] && APPEND_ARGS+=(--reason "$RECEIPT_REASON")
  if ! /usr/bin/python3 "$DIR/acclaim_run_receipt.py" "${APPEND_ARGS[@]}" 2>>"$LOG"; then
    FAIL=1
    log "FATAL: unable to append Acclaim receipt outcome for $ISO"
  fi
  log "date $DSTATUS $ISO: found=$FOUND/$TOTAL_SHOWN inserted=$INS pages=$PAGES_DONE"
  [ "$DSTATUS" = "done" ] && LAST="$ISO"
  rm -f "$OUT" "$OUT.page"
  # A not-yet-released empty weekday must stay in backlog without starving newer
  # dates that may already be searchable. Other failures stop so a broken browser
  # or source gate is not hammered repeatedly in the same invocation.
  if [ "$DSTATUS" != "done" ] && [ "$CONTINUE_AFTER" -ne 1 ]; then break; fi
done <<< "$TARGETS"

log "=== acclaim pull end (fail=$FAIL degraded=$DEGRADED first=$FIRST last=$LAST) ==="
RUN_STATUS=ok; RUN_REASON=""
if [ "$RECEIPT_BACKLOG" -ne 0 ]; then
  RUN_STATUS=failed; RUN_REASON=prior_receipt_replay_failed
elif [ "$FAIL" -ne 0 ]; then
  RUN_STATUS=failed; RUN_REASON=one_or_more_attempts_failed
elif [ "$DEGRADED" -ne 0 ]; then
  RUN_STATUS=source_wait; RUN_REASON=source_not_authoritative_yet
elif [ "$SAW_ROWS" -eq 0 ]; then
  RUN_STATUS=empty
fi
if ! finalize_receipt "$RUN_STATUS" "$RUN_REASON"; then
  log "FATAL: run receipt remains queued; remote receipt write failed"
  exit 1
fi
[ "$RECEIPT_BACKLOG" -eq 0 ] || exit 1
exit "$FAIL"
