#!/bin/zsh
set -u
set -o pipefail

launcher_path="${0:A}"
resources="${launcher_path:h:h}/Resources"
token_file="$HOME/.florida_signal_datawire_token"
supabase_env="$HOME/.florida_signal_supabase_env"
data_dir="$HOME/Library/Application Support/Florida Signal Data Wire"
# Finder-launched apps can be denied access to Documents by macOS privacy controls.
# The desktop build therefore carries a verified, read-only source snapshot.
florida_source="${FL_SIGNAL_SOURCE_ROOT:-$resources/florida-signal}"
project_state_path="${FL_SIGNAL_PROJECT_STATE_PATH:-$florida_source/data/reference/florida_signal_project_state.json}"
pdmr_db_path="${FL_SIGNAL_PDMR_DB_PATH:-$florida_source/data/pdmr/florida_signal_v1.sqlite}"
pdmr_candidate_script="${FL_SIGNAL_PDMR_CANDIDATE_SCRIPT:-$florida_source/scripts/nominate_pdmr_candidates.py}"
utility_local_root="${FL_SIGNAL_UTILITY_LOCAL_ROOT:-$data_dir/utility-intake}"
utility_sync_script="$resources/scripts/sync_utility_intake_receipts.py"
utility_ssh_host="${FL_SIGNAL_UTILITY_SSH_HOST:-florida}"
utility_known_hosts="${FL_SIGNAL_UTILITY_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
utility_sync_interval="${FL_SIGNAL_UTILITY_SYNC_INTERVAL_SECONDS:-300}"
desk_url="http://127.0.0.1:8788/"
log_file="/tmp/florida-signal-data-wire-launch.log"
job_label="com.floridasignal.datawire.server"
service_target="gui/$(/usr/bin/id -u)/$job_label"
launchctl_bin="${FL_SIGNAL_DESK_LAUNCHCTL_BIN:-/bin/launchctl}"
lsof_bin="${FL_SIGNAL_DESK_LSOF_BIN:-/usr/sbin/lsof}"
curl_bin="${FL_SIGNAL_DESK_CURL_BIN:-/usr/bin/curl}"
sleep_bin="${FL_SIGNAL_DESK_SLEEP_BIN:-/bin/sleep}"
open_bin="${FL_SIGNAL_DESK_OPEN_BIN:-/usr/bin/open}"
osascript_bin="${FL_SIGNAL_DESK_OSASCRIPT_BIN:-/usr/bin/osascript}"
lifecycle_lock="$data_dir/lifecycle.lock"

desk_job_is_loaded() {
  "$launchctl_bin" print "$service_target" >/dev/null 2>&1
}

desk_port_is_busy() {
  "$lsof_bin" -nP -tiTCP:8788 -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_desk_job_absent() {
  local attempt
  for attempt in {1..100}; do
    if ! desk_job_is_loaded; then
      return 0
    fi
    "$sleep_bin" 0.1
  done
  return 1
}

wait_for_desk_port_free() {
  local attempt
  for attempt in {1..100}; do
    if ! desk_port_is_busy; then
      return 0
    fi
    "$sleep_bin" 0.1
  done
  return 1
}

remove_previous_desk_job() {
  # Boot out only our exact GUI-domain service, then prove both its target and
  # listener are gone before submitting a new job.
  "$launchctl_bin" bootout "$service_target" 2>/dev/null || true
  wait_for_desk_job_absent || return 1
  wait_for_desk_port_free || return 1
}

desk_health_is_expected() {
  "$curl_bin" --fail --silent --max-time 1 "http://127.0.0.1:8788/api/health" 2>/dev/null |
    /usr/bin/python3 -c 'import json, sys
try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError):
    raise SystemExit(1)
raise SystemExit(0 if payload.get("ok") is True and payload.get("service") == "the-data-wire" and payload.get("admin_writes_enabled") is True else 1)' \
      2>/dev/null
}

show_start_failure() {
  "$osascript_bin" -e 'display alert "Florida Signal Data Wire" message "The local desk did not start safely. Another app may be using port 8788, or the private Desk job may still be stopping. Details were saved to /tmp/florida-signal-data-wire-launch.log." as critical' >/dev/null 2>&1 || true
}

/bin/mkdir -p "$data_dir"
if [[ "${1:-}" != "--serve" ]]; then
  # Serialize launcher and updater lifecycle changes. The live submitted job
  # has a five-second exit timeout, so teardown waits allow ten seconds.
  exec 9>"$lifecycle_lock"
  if ! /usr/bin/lockf -s -t 10 9; then
    exec 9>&-
    show_start_failure
    exit 1
  fi
fi
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

if [[ "${1:-}" == "--serve" ]]; then
  DATA_WIRE_DB_PATH="$data_dir/data_wire.sqlite" \
  DATA_WIRE_ADMIN_TOKEN="$token" \
  DATA_WIRE_LOCAL_AUTOUNLOCK=1 \
  FL_SIGNAL_PROJECT_STATE_PATH="$project_state_path" \
  FL_SIGNAL_PDMR_DB_PATH="$pdmr_db_path" \
  FL_SIGNAL_PDMR_CANDIDATE_SCRIPT="$pdmr_candidate_script" \
  FL_SIGNAL_UTILITY_LOCAL_ROOT="$utility_local_root" \
  FL_SIGNAL_UTILITY_RECEIPT_DIR="$utility_local_root/receipts" \
  FL_SIGNAL_UTILITY_LATEST_ATTEMPT_POINTER="$utility_local_root/latest-attempt.json" \
  FL_SIGNAL_UTILITY_LATEST_SUCCESS_POINTER="$utility_local_root/latest-success.json" \
  FL_SIGNAL_UTILITY_LATEST_NATURAL_POINTER="$utility_local_root/latest-natural.json" \
  FL_SIGNAL_UTILITY_SYNC_SCRIPT="$utility_sync_script" \
  FL_SIGNAL_UTILITY_SSH_HOST="$utility_ssh_host" \
  FL_SIGNAL_UTILITY_KNOWN_HOSTS="$utility_known_hosts" \
  FL_SIGNAL_UTILITY_SYNC_INTERVAL_SECONDS="$utility_sync_interval" \
  exec /usr/bin/python3 "$resources/cms/server.py" --port 8788
fi

# The server owns the bounded receipt-refresh thread. It runs immediately and
# every five minutes only while this exact Desk job is alive. The helper uses a
# cross-process lock and strict known-host verification; failures preserve the
# prior snapshot, whose receipt clock then ages to stale/unverified.

# A Finder-launched shell app's descendants can be reaped when its executable
# exits. Submit the loopback server to this user's launchd domain so it remains
# available after the launcher opens Chrome. Reopening the app replaces only
# this private Desk job; it does not touch any collector LaunchAgent or timer.
if ! remove_previous_desk_job; then
  exec 9>&-
  show_start_failure
  exit 1
fi
if ! "$launchctl_bin" submit -l "$job_label" -o "$log_file" -e "$log_file" -- "$launcher_path" --serve; then
  "$launchctl_bin" bootout "$service_target" 2>/dev/null || true
  wait_for_desk_job_absent || true
  wait_for_desk_port_free || true
  exec 9>&-
  show_start_failure
  exit 1
fi

desk_ready=0
for attempt in {1..20}; do
  if desk_job_is_loaded && desk_health_is_expected; then
    desk_ready=1
    break
  fi
  "$sleep_bin" 0.25
done

if [[ "$desk_ready" == 1 ]]; then
  exec 9>&-
  if [[ -d "/Applications/Google Chrome.app" ]]; then
    "$open_bin" -a "Google Chrome" "$desk_url"
  else
    "$open_bin" "$desk_url"
  fi
else
  "$launchctl_bin" bootout "$service_target" 2>/dev/null || true
  wait_for_desk_job_absent || true
  wait_for_desk_port_free || true
  exec 9>&-
  show_start_failure
  exit 1
fi
