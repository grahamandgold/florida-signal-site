#!/bin/bash
# Florida Signal — local launcher for the public site (4173) and The Data Wire CMS (8788).
# The Data Wire admin token lives OUTSIDE the repo in ~/.florida_signal_datawire_token.
set -u

DIR="/Users/gillfillan/Documents/FL SIGNAL SITE BUILD"
TOKEN_FILE="$HOME/.florida_signal_datawire_token"

if [ ! -s "$TOKEN_FILE" ]; then
  umask 077
  openssl rand -hex 24 > "$TOKEN_FILE"
fi
TOKEN="$(cat "$TOKEN_FILE")"

# Mailchimp credentials, if configured via ops/set_mailchimp_key.command
[ -f "$HOME/.florida_signal_mailchimp_env" ] && source "$HOME/.florida_signal_mailchimp_env"

# Supabase service-role key for the Signal review queue. Read from outside the repo and exported to
# the CMS process only — it is never sent to the browser; the desk proxies every queue call.
if [ -f "$HOME/.florida_signal_supabase_env" ]; then
  set -a; source "$HOME/.florida_signal_supabase_env"; set +a
fi

cd "$DIR"

# Stop any previous instances (kill whatever holds the ports)
for p in 8788 4173; do
  lsof -ti :"$p" | xargs kill 2>/dev/null || true
done
sleep 1

DATA_WIRE_ADMIN_TOKEN="$TOKEN" DATA_WIRE_LOCAL_AUTOUNLOCK=1 nohup python3 cms/server.py --port 8788 >/tmp/datawire.log 2>&1 &
FLORIDA_SIGNAL_CMS_URL='http://127.0.0.1:8788' \
FLORIDA_SIGNAL_CMS_MARKET='broward' \
FLORIDA_SIGNAL_CMS_CITY='fort-lauderdale' \
nohup python3 server.py --bind 127.0.0.1 --port 4173 >/tmp/flsignal.log 2>&1 &

sleep 3
echo "CMS health: $(curl -s --max-time 5 http://127.0.0.1:8788/api/health || echo FAILED)"
echo "Site http:  $(curl -s --max-time 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:4173/fort-lauderdale/ || echo FAILED)"
echo "TOKEN:$TOKEN"
echo "--- last log lines ---"
tail -n 3 /tmp/datawire.log 2>/dev/null
tail -n 3 /tmp/flsignal.log 2>/dev/null
