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
MAXPAGES="${ACCLAIM_MAX_PAGES:-60}"
MAXDATES="${ACCLAIM_MAX_DATES:-8}"

# Secrets: set -a exports sourced KEY=value pairs to child processes (osascript/python).
ENVFILE="$HOME/.florida_signal_supabase_env"
if [ -f "$ENVFILE" ]; then set -a; source "$ENVFILE"; set +a; fi

log(){ echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$LOG"; }
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
TARGETS=$(/usr/bin/python3 - "$VERIFIED_MAX" "$MAXDATES" "$STATE" <<'PY'
import sys,datetime,json,os
base=datetime.date.fromisoformat(sys.argv[1]); cap=int(sys.argv[2]); statef=sys.argv[3]
today=datetime.date.today()
done=set()
if os.path.exists(statef):
    try:
        st=json.load(open(statef))
        done={d for d,v in st.get("dates",{}).items() if v.get("status")=="done"}
    except Exception: pass
out=[]; d=base+datetime.timedelta(days=1)
while d<=today and len(out)<cap:
    iso=d.isoformat()
    if iso not in done: out.append(f"{d.month}/{d.day}/{d.year}|{iso}")
    d+=datetime.timedelta(days=1)
print("\n".join(out))
PY
)

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
  if [ "$RES" != "OK" ] && [ "$RES" != "EMPTY" ]; then
    log "HARVEST FAILED $ISO: $RES"; FAIL=1
    /usr/bin/python3 "$DIR/acclaim_state.py" "$STATE" "$ISO" incomplete 0 0 0 "$VERIFIED_MAX" 2>>"$LOG"
    break   # resume from this date next run
  fi
  FOUND=$(wc -l < "$OUT" | tr -d ' ')
  INS=0; SKIP=0
  if [ "$FOUND" -gt 0 ]; then
    UPOUT=$(/usr/bin/python3 "$DIR/acclaim_upsert.py" "$OUT" 2>>"$LOG")
    log "upsert $ISO: $UPOUT"
    INS=$(echo "$UPOUT" | grep -oE 'inserted [0-9]+' | grep -oE '[0-9]+' | head -1); INS="${INS:-0}"
    SKIP=$(echo "$UPOUT" | grep -oE 'already present\)?' >/dev/null && echo "$UPOUT" | grep -oE '[0-9]+ already present' | grep -oE '[0-9]+' | head -1 || echo 0); SKIP="${SKIP:-0}"
  fi
  PAGES=$(( (FOUND + 99) / 100 ))
  /usr/bin/python3 "$DIR/acclaim_state.py" "$STATE" "$ISO" done "$PAGES" "$FOUND" "$INS" "$VERIFIED_MAX" 2>>"$LOG"
  log "date done $ISO: found=$FOUND inserted=$INS pages~$PAGES"
  LAST="$ISO"
  rm -f "$OUT" "$OUT.page"
done <<< "$TARGETS"

log "=== acclaim pull end (fail=$FAIL first=$FIRST last=$LAST) ==="
exit $FAIL
