#!/bin/bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_path="$HOME/Desktop/Florida Signal Data Wire.app"
expected_bundle="com.floridasignal.datawire.local"
site_repo="${FL_SIGNAL_SITE_REPO:-$HOME/Documents/FL SIGNAL SITE BUILD}"
source_root="${FL_SIGNAL_SOURCE_ROOT:-$site_repo/_source_copies/florida-signal}"
project_state_source="${FL_SIGNAL_PROJECT_STATE_SOURCE:-$source_root/data/reference/florida_signal_project_state.json}"
pdmr_db_source="${FL_SIGNAL_PDMR_DB_SOURCE:-$source_root/data/pdmr/florida_signal_v1.sqlite}"
pdmr_candidate_source="${FL_SIGNAL_PDMR_CANDIDATE_SOURCE:-$source_root/scripts/nominate_pdmr_candidates.py}"
job_label="com.floridasignal.datawire.server"
service_target="gui/$(/usr/bin/id -u)/$job_label"
launchctl_bin="${FL_SIGNAL_DESK_LAUNCHCTL_BIN:-/bin/launchctl}"
lsof_bin="${FL_SIGNAL_DESK_LSOF_BIN:-/usr/sbin/lsof}"
ps_bin="${FL_SIGNAL_DESK_PS_BIN:-/bin/ps}"
kill_bin="${FL_SIGNAL_DESK_KILL_BIN:-/bin/kill}"
sleep_bin="${FL_SIGNAL_DESK_SLEEP_BIN:-/bin/sleep}"
open_bin="${FL_SIGNAL_DESK_OPEN_BIN:-/usr/bin/open}"
curl_bin="${FL_SIGNAL_DESK_CURL_BIN:-/usr/bin/curl}"
python_process_argv0_override="${FL_SIGNAL_DESK_PYTHON_ARGV0:-}"
data_dir="$HOME/Library/Application Support/Florida Signal Data Wire"
lifecycle_lock="$data_dir/lifecycle.lock"
lifecycle_lock_held=0
desk_was_running=0

acquire_desk_lifecycle_lock() {
  if [[ "$lifecycle_lock_held" == 1 ]]; then
    return 0
  fi
  /bin/mkdir -p "$data_dir"
  exec 9>"$lifecycle_lock"
  if ! /usr/bin/lockf -s -t 10 9; then
    exec 9>&-
    return 1
  fi
  lifecycle_lock_held=1
}

release_desk_lifecycle_lock() {
  if [[ "$lifecycle_lock_held" == 1 ]]; then
    exec 9>&-
    lifecycle_lock_held=0
  fi
}

desk_job_is_loaded() {
  "$launchctl_bin" print "$service_target" >/dev/null 2>&1
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

desk_listener_pids() {
  "$lsof_bin" -nP -tiTCP:8788 -sTCP:LISTEN 2>/dev/null || true
}

desk_port_is_busy() {
  "$lsof_bin" -nP -tiTCP:8788 -sTCP:LISTEN >/dev/null 2>&1
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

is_expected_legacy_desk_pid() {
  local process_id="$1"
  local command_line
  local process_uid
  local python_process_argv0
  local expected_command
  local historical_command
  [[ "$process_id" =~ ^[0-9]+$ ]] || return 1
  if [[ -n "$python_process_argv0_override" ]]; then
    python_process_argv0="$python_process_argv0_override"
  else
    python_process_argv0="$(/usr/bin/python3 -c 'import os, subprocess
print(subprocess.check_output(["/bin/ps", "-p", str(os.getpid()), "-o", "comm="], text=True).strip())' 2>/dev/null)" || return 1
  fi
  [[ -n "$python_process_argv0" ]] || return 1
  expected_command="$python_process_argv0 $app_path/Contents/Resources/cms/server.py --port 8788"
  historical_command="$python_process_argv0 $app_path/Contents/MacOS/../Resources/cms/server.py --port 8788"
  process_uid="$("$ps_bin" -p "$process_id" -o uid= 2>/dev/null)" || return 1
  process_uid="${process_uid#"${process_uid%%[![:space:]]*}"}"
  process_uid="${process_uid%"${process_uid##*[![:space:]]}"}"
  [[ "$process_uid" == "$(/usr/bin/id -u)" ]] || return 1
  command_line="$("$ps_bin" -ww -p "$process_id" -o command= 2>/dev/null)" || return 1
  command_line="${command_line#"${command_line%%[![:space:]]*}"}"
  [[ "$command_line" == "$expected_command" || "$command_line" == "$historical_command" ]]
}

desk_has_only_listener_pid() {
  local expected_pid="$1"
  local current_pid
  local count=0
  local matched=0
  while IFS= read -r current_pid; do
    [[ -n "$current_pid" ]] || continue
    count=$((count + 1))
    if [[ "$current_pid" == "$expected_pid" ]]; then
      matched=1
    fi
  done < <(desk_listener_pids)
  [[ "$count" == 1 && "$matched" == 1 ]]
}

legacy_desk_health_is_expected() {
  "$curl_bin" --fail --silent --max-time 1 "http://127.0.0.1:8788/api/health" 2>/dev/null |
    /usr/bin/python3 -c 'import json, sys
try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError):
    raise SystemExit(1)
raise SystemExit(0 if payload.get("ok") is True and payload.get("service") == "the-data-wire" and payload.get("admin_writes_enabled") is True else 1)' \
      2>/dev/null
}

coordinate_desk_restart_after_update() {
  local managed_was_running=0
  local process_id
  local -a listener_pids=()
  acquire_desk_lifecycle_lock || return 1
  desk_was_running=0
  if desk_job_is_loaded; then
    managed_was_running=1
    desk_was_running=1
  fi

  # Boot out only the exact GUI-domain Desk service, then boundedly prove its
  # target is absent before examining the port.
  "$launchctl_bin" bootout "$service_target" 2>/dev/null || true
  if ! wait_for_desk_job_absent; then
    release_desk_lifecycle_lock
    return 1
  fi

  if [[ "$managed_was_running" == 1 ]]; then
    # Never signal a launchd-managed PID. The exact-label removal owns teardown.
    if ! wait_for_desk_port_free; then
      release_desk_lifecycle_lock
      return 1
    fi
  else
    while IFS= read -r process_id; do
      [[ -n "$process_id" ]] || continue
      listener_pids+=("$process_id")
    done < <(desk_listener_pids)

    if (( ${#listener_pids[@]} > 0 )); then
      # One pre-launchd version used nohup. Require exactly one listener, the
      # current user, the exact app command, expected Desk health, and an
      # immediate listener/command recheck before sending TERM to that PID.
      if (( ${#listener_pids[@]} != 1 )); then
        release_desk_lifecycle_lock
        return 1
      fi
      process_id="${listener_pids[0]}"
      if ! is_expected_legacy_desk_pid "$process_id" || \
          ! legacy_desk_health_is_expected || \
          ! desk_has_only_listener_pid "$process_id" || \
          ! is_expected_legacy_desk_pid "$process_id"; then
        release_desk_lifecycle_lock
        return 1
      fi
      desk_was_running=1
      "$kill_bin" "$process_id" 2>/dev/null || true
      if ! wait_for_desk_port_free; then
        release_desk_lifecycle_lock
        return 1
      fi
    fi
  fi

  # Release before Finder starts the app; the launcher takes the same lock.
  release_desk_lifecycle_lock
  if [[ "$desk_was_running" == 1 ]]; then
    "$open_bin" "$app_path"
  fi
}

copy_verified_source_snapshot() {
  local snapshot_root="$1"
  local source_file
  for source_file in "$project_state_source" "$pdmr_db_source" "$pdmr_candidate_source"; do
    if [[ ! -s "$source_file" ]]; then
      echo "Desktop source snapshot is missing: $source_file" >&2
      return 1
    fi
  done
  if ! /usr/bin/python3 -m json.tool "$project_state_source" >/dev/null; then
    echo "Project-state source is not valid JSON: $project_state_source" >&2
    return 1
  fi
  if [[ "$(/usr/bin/sqlite3 "$pdmr_db_source" 'pragma quick_check;')" != "ok" ]]; then
    echo "PDMR evidence database failed SQLite quick_check" >&2
    return 1
  fi

  /bin/mkdir -p "$snapshot_root/data/reference" "$snapshot_root/data/pdmr" "$snapshot_root/scripts"
  /bin/cp "$project_state_source" "$snapshot_root/data/reference/florida_signal_project_state.json"
  /bin/cp "$pdmr_db_source" "$snapshot_root/data/pdmr/florida_signal_v1.sqlite"
  /bin/cp "$pdmr_candidate_source" "$snapshot_root/scripts/nominate_pdmr_candidates.py"

  # Prove the independently overridden files, including paths with spaces, are
  # the exact bytes bundled into the staged app. Validate the copied DB too.
  /usr/bin/cmp -s "$project_state_source" "$snapshot_root/data/reference/florida_signal_project_state.json" || return 1
  /usr/bin/cmp -s "$pdmr_db_source" "$snapshot_root/data/pdmr/florida_signal_v1.sqlite" || return 1
  /usr/bin/cmp -s "$pdmr_candidate_source" "$snapshot_root/scripts/nominate_pdmr_candidates.py" || return 1
  if [[ "$(/usr/bin/sqlite3 "$snapshot_root/data/pdmr/florida_signal_v1.sqlite" 'pragma quick_check;')" != "ok" ]]; then
    echo "Bundled PDMR evidence database failed SQLite quick_check" >&2
    return 1
  fi
}

main() {

if [[ ! -d "$app_path" ]]; then
  echo "Desktop app not found: $app_path" >&2
  exit 1
fi
actual_bundle="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app_path/Contents/Info.plist")"
if [[ "$actual_bundle" != "$expected_bundle" ]]; then
  echo "Refusing to replace an unexpected app bundle: $actual_bundle" >&2
  exit 1
fi

stage_dir="$(mktemp -d /tmp/fl-datawire-app.XXXXXX)"
staged_app="$stage_dir/Florida Signal Data Wire.app"
previous_app="$stage_dir/previous.app"
trap '/bin/rm -rf "$stage_dir"' EXIT

/usr/bin/ditto --norsrc "$app_path" "$staged_app"
/bin/cp "$repo_dir/cms/server.py" "$repo_dir/cms/home.html" "$repo_dir/cms/agenda.html" \
  "$repo_dir/cms/index.html" \
  "$repo_dir/cms/data.html" "$repo_dir/cms/review.html" "$repo_dir/cms/desk-shell.css" \
  "$repo_dir/cms/desk-shell.js" "$staged_app/Contents/Resources/cms/"
/bin/cp -L "$repo_dir/cms/mark-full-color.png" "$staged_app/Contents/Resources/cms/mark-full-color.png"
/bin/mkdir -p "$staged_app/Contents/Resources/scripts"
/bin/cp "$repo_dir/ops/mac/sync_utility_intake_receipts.py" \
  "$staged_app/Contents/Resources/scripts/sync_utility_intake_receipts.py"
/bin/chmod 755 "$staged_app/Contents/Resources/scripts/sync_utility_intake_receipts.py"

# Bundle local-only research lanes so the Finder app does not need Documents access.
# Re-running this updater refreshes the read-only snapshot.
snapshot_root="$staged_app/Contents/Resources/florida-signal"
copy_verified_source_snapshot "$snapshot_root"

for required_page in home.html agenda.html index.html data.html review.html; do
  if [[ ! -s "$staged_app/Contents/Resources/cms/$required_page" ]]; then
    echo "Staged desktop app is missing required Newsroom page: $required_page" >&2
    exit 1
  fi
done
if [[ ! -s "$staged_app/Contents/Resources/scripts/sync_utility_intake_receipts.py" ]]; then
  echo "Staged desktop app is missing the utility receipt sync helper" >&2
  exit 1
fi
for required_snapshot in \
  data/reference/florida_signal_project_state.json \
  data/pdmr/florida_signal_v1.sqlite \
  scripts/nominate_pdmr_candidates.py; do
  if [[ ! -s "$snapshot_root/$required_snapshot" ]]; then
    echo "Staged desktop app is missing source snapshot: $required_snapshot" >&2
    exit 1
  fi
done
/bin/cp "$repo_dir/ops/datawire-app-launcher.zsh" "$staged_app/Contents/MacOS/Florida Signal Data Wire"
/bin/chmod 755 "$staged_app/Contents/MacOS/Florida Signal Data Wire"
/usr/bin/xattr -cr "$staged_app"
/usr/bin/codesign --force --deep --sign - "$staged_app"
/usr/bin/codesign --verify --deep --strict "$staged_app"

if ! acquire_desk_lifecycle_lock; then
  echo "Could not acquire the private Desk lifecycle lock; no app files were replaced." >&2
  exit 1
fi
/bin/mv "$app_path" "$previous_app"
if /bin/mv "$staged_app" "$app_path"; then
  # Finder can add an empty com.apple.FinderInfo xattr as soon as a bundle lands on Desktop.
  # That metadata is not part of the app and makes strict verification report "detritus."
  /usr/bin/xattr -d com.apple.FinderInfo "$app_path" 2>/dev/null || true
fi
if [[ -d "$app_path" ]] && /usr/bin/codesign --verify --deep "$app_path"; then
  # Python loads server.py into memory. Replacing the bundle updates static pages immediately,
  # but an already-running process would keep the old route map until restart.
  if ! coordinate_desk_restart_after_update; then
    echo "Desktop app updated and verified, but the private Desk job did not stop cleanly or port 8788 remains occupied. No unrelated process was killed." >&2
    return 1
  fi
  echo "Florida Signal Data Wire desktop app updated and verified."
else
  [[ -d "$app_path" ]] && /bin/mv "$app_path" "$stage_dir/failed-new.app"
  /bin/mv "$previous_app" "$app_path"
  /usr/bin/xattr -d com.apple.FinderInfo "$app_path" 2>/dev/null || true
  echo "Update failed; the previous desktop app was restored." >&2
  exit 1
fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
