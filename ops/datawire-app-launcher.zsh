#!/bin/zsh
set -u

resources="${0:A:h}/../Resources"
token_file="$HOME/.florida_signal_datawire_token"
supabase_env="$HOME/.florida_signal_supabase_env"
data_dir="$HOME/Library/Application Support/Florida Signal Data Wire"
desk_url="http://127.0.0.1:8788/"
log_file="/tmp/florida-signal-data-wire-launch.log"

/bin/mkdir -p "$data_dir"
if [[ ! -s "$token_file" ]]; then
  /usr/bin/openssl rand -hex 24 > "$token_file"
  /bin/chmod 600 "$token_file"
fi
token="$(<"$token_file")"

if [[ -f "$supabase_env" ]]; then
  set -a
  source "$supabase_env"
  set +a
fi

for process_id in $(/usr/sbin/lsof -ti :8788 2>/dev/null); do
  /bin/kill "$process_id" 2>/dev/null || true
done

DATA_WIRE_DB_PATH="$data_dir/data_wire.sqlite" \
DATA_WIRE_ADMIN_TOKEN="$token" \
DATA_WIRE_LOCAL_AUTOUNLOCK=1 \
/usr/bin/nohup /usr/bin/python3 "$resources/cms/server.py" --port 8788 >"$log_file" 2>&1 &

desk_ready=0
for attempt in {1..20}; do
  if /usr/bin/curl --fail --silent --max-time 1 "http://127.0.0.1:8788/api/health" >/dev/null; then
    desk_ready=1
    break
  fi
  /bin/sleep 0.25
done

if [[ "$desk_ready" == 1 ]]; then
  if [[ -d "/Applications/Google Chrome.app" ]]; then
    /usr/bin/open -a "Google Chrome" "$desk_url"
  else
    /usr/bin/open "$desk_url"
  fi
else
  osascript -e 'display alert "Florida Signal Data Wire" message "The local desk did not start. Details were saved to /tmp/florida-signal-data-wire-launch.log." as critical'
  exit 1
fi
