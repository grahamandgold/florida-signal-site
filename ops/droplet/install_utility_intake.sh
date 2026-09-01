#!/usr/bin/env bash
set -euo pipefail

# Release-atomic, timer-default-off installer for the utility-intake verifier.
# Every candidate byte, import, unit, and startup receipt is validated in an
# unreachable generation. Inactive unit files are atomically installed from
# that generation, then one `current` symlink switches all executable code.
# Any late validation failure restores the prior generation and unit files,
# reloads that prior state, and leaves the timer inactive and disabled.

readonly approval_phrase="I_APPROVE_EXACT_UTILITY_INTAKE_ATOMIC_INSTALL"
readonly service_name="florida-utility-intake.service"
readonly timer_name="florida-utility-intake.timer"
readonly install_root="/srv/grahamandgold/florida-signal"
readonly release_root="$install_root/utility-intake-releases"
readonly current_link="$release_root/current"
readonly unit_root="/etc/systemd/system"
readonly data_root="$install_root/staging/data/utility-intake"
readonly python_bin="$install_root/app/.venv/bin/python3"

path_exists() {
  [[ -e "$1" || -L "$1" ]]
}

timer_is_preinstall_safe() {
  local active enabled
  active="$(/usr/bin/systemctl is-active "$timer_name" 2>/dev/null || true)"
  enabled="$(/usr/bin/systemctl is-enabled "$timer_name" 2>/dev/null || true)"
  if [[ "$active" == "inactive" && "$enabled" == "disabled" ]]; then
    return 0
  fi
  [[ "$active" == "unknown" && "$enabled" == "not-found" ]] && \
    ! path_exists "$unit_root/$timer_name"
}

service_is_preinstall_safe() {
  local active
  active="$(/usr/bin/systemctl is-active "$service_name" 2>/dev/null || true)"
  [[ "$active" == "inactive" || "$active" == "unknown" ]]
}

timer_is_postswitch_safe() {
  local active enabled
  active="$(/usr/bin/systemctl is-active "$timer_name" 2>/dev/null || true)"
  enabled="$(/usr/bin/systemctl is-enabled "$timer_name" 2>/dev/null || true)"
  [[ "$active" == "inactive" && "$enabled" == "disabled" ]]
}

service_is_postswitch_safe() {
  [[ "$(/usr/bin/systemctl is-active "$service_name" 2>/dev/null || true)" == "inactive" ]]
}

copy_candidate() {
  local source="$1" destination="$2" mode="$3"
  /usr/bin/install -o root -g root -m "$mode" "$source" "$destination"
  /usr/bin/cmp -s "$source" "$destination"
  /bin/sync -f "$destination"
}

stage_release() {
  local repo_root="$1" stage_dir="$2"
  /usr/bin/install -d -o root -g root -m 0755 "$stage_dir"
  copy_candidate "$repo_root/ops/droplet/utility_intake_production.py" \
    "$stage_dir/utility_intake_production.py" 0644
  copy_candidate "$repo_root/ops/droplet/utility_intake_shadow.py" \
    "$stage_dir/utility_intake_shadow.py" 0644
  copy_candidate "$repo_root/ops/droplet/florida-utility-intake-wait.sh" \
    "$stage_dir/florida-utility-intake-wait.sh" 0755
  copy_candidate "$repo_root/ops/droplet/$service_name" "$stage_dir/$service_name" 0644
  copy_candidate "$repo_root/ops/droplet/$timer_name" "$stage_dir/$timer_name" 0644
  /bin/sync -f "$stage_dir"
}

validate_staged_release() {
  local stage_dir="$1" check_root="$2"
  "$python_bin" -c 'import pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
import utility_intake_shadow
import utility_intake_production
assert utility_intake_production.SHADOW_IMPORT_ERROR is None
assert utility_intake_production.shadow is utility_intake_shadow' "$stage_dir"

  /usr/bin/systemd-analyze verify "$stage_dir/$service_name" "$stage_dir/$timer_name"

  /usr/bin/install -d -o andy -g andy -m 0700 "$check_root"
  set +e
  /usr/sbin/runuser -u andy -- /usr/bin/env -i PATH=/usr/bin:/bin \
    "$python_bin" "$stage_dir/utility_intake_production.py" \
    --sqlite-path "$install_root/staging/db/permits.sqlite" \
    --writer-lock-path "$install_root/app/db/.writer.lock" \
    --evidence-dir "$check_root/runs" \
    --receipt-dir "$check_root/receipts" \
    --latest-attempt-pointer "$check_root/latest-attempt.json" \
    --latest-success-pointer "$check_root/latest-success.json" \
    --credential-file "$check_root/intentionally-absent.env" \
    --run-id "utility-install-startup-${check_root##*/}" \
    >"$check_root/stdout.json" 2>"$check_root/stderr.log"
  local check_rc=$?
  set -e
  [[ "$check_rc" -eq 3 ]]
  "$python_bin" -c 'import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
pointer = json.loads((root / "latest-attempt.json").read_text())
receipt = json.loads((root / "receipts" / pathlib.Path(pointer["receipt_path"]).name).read_text())
assert pointer["pointer_kind"] == "attempt"
assert receipt["status"] == "failed"
assert receipt["startup_stage"] == "credential_file"
assert receipt["safety"]["remote_methods"] == []
assert not (root / "latest-success.json").exists()' "$check_root"
}

save_path() {
  local path="$1" backup_dir="$2" name="$3"
  if path_exists "$path"; then
    /bin/cp -a "$path" "$backup_dir/$name"
    : >"$backup_dir/$name.present"
  fi
}

restore_path() {
  local path="$1" backup_dir="$2" name="$3"
  if [[ -d "$path" && ! -L "$path" ]]; then
    return 1
  fi
  /bin/rm -f -- "$path"
  if [[ -f "$backup_dir/$name.present" ]]; then
    /bin/cp -a "$backup_dir/$name" "$path"
  fi
}

replace_symlink() {
  local target="$1" destination="$2"
  local temporary="${destination}.install.$$"
  if [[ -d "$destination" && ! -L "$destination" ]]; then
    return 1
  fi
  /bin/rm -f -- "$temporary"
  /bin/ln -s "$target" "$temporary"
  # os.replace swaps the symlink inode itself and never follows a destination
  # symlink-to-directory; plain `mv` differs between GNU and BSD here.
  /usr/bin/python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' \
    "$temporary" "$destination"
  /bin/sync -f "$(/usr/bin/dirname "$destination")"
}

replace_unit_file() {
  local source="$1" destination="$2"
  local temporary="${destination}.install.$$"
  if [[ -d "$destination" && ! -L "$destination" ]]; then
    return 1
  fi
  /bin/rm -f -- "$temporary"
  /usr/bin/install -o root -g root -m 0644 "$source" "$temporary"
  /usr/bin/cmp -s "$source" "$temporary"
  /bin/sync -f "$temporary"
  /usr/bin/python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' \
    "$temporary" "$destination"
  /bin/sync -f "$(/usr/bin/dirname "$destination")"
}

rollback_release_switch() {
  local backup_dir="$1" final_dir="$2" release_base="$3" current_path="$4" units="$5"
  restore_path "$current_path" "$backup_dir" current || true
  restore_path "$units/$service_name" "$backup_dir" service || true
  restore_path "$units/$timer_name" "$backup_dir" timer || true
  /bin/sync -f "$release_base" || true
  /bin/sync -f "$units" || true
  /usr/bin/systemctl daemon-reload >/dev/null 2>&1 || true
  if path_exists "$current_path" && [[ "$(/usr/bin/readlink "$current_path")" == "$final_dir" ]]; then
    echo "Rollback could not detach the failed release" >&2
    return 1
  fi
}

install_post_switch_guard() {
  local final_dir="$1"
  /usr/bin/systemctl daemon-reload
  timer_is_postswitch_safe
  service_is_postswitch_safe
  [[ "$(/usr/bin/readlink "$current_link")" == "$final_dir" ]]
  [[ ! -L "$unit_root/$service_name" && ! -L "$unit_root/$timer_name" ]]
  /usr/bin/cmp -s "$final_dir/$service_name" "$unit_root/$service_name"
  /usr/bin/cmp -s "$final_dir/$timer_name" "$unit_root/$timer_name"
  "$python_bin" -c 'import pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
import utility_intake_shadow
import utility_intake_production
assert utility_intake_production.SHADOW_IMPORT_ERROR is None
assert utility_intake_production.shadow is utility_intake_shadow' "$current_link"
  /usr/bin/systemd-analyze verify "$unit_root/$service_name" "$unit_root/$timer_name"
}

switch_release() {
  local stage_dir="$1" final_dir="$2"
  local release_base="${3:-$release_root}"
  local current_path="${4:-$current_link}"
  local units="${5:-$unit_root}"
  local backup_dir
  backup_dir="$(/usr/bin/mktemp -d "$release_base/.rollback.XXXXXX")"
  if [[ -d "$current_path" && ! -L "$current_path" ]] || \
      [[ -d "$units/$service_name" && ! -L "$units/$service_name" ]] || \
      [[ -d "$units/$timer_name" && ! -L "$units/$timer_name" ]]; then
    /bin/rm -rf -- "$backup_dir"
    return 1
  fi
  save_path "$current_path" "$backup_dir" current || return 1
  save_path "$units/$service_name" "$backup_dir" service || return 1
  save_path "$units/$timer_name" "$backup_dir" timer || return 1

  if ! /bin/mv "$stage_dir" "$final_dir" || \
      ! replace_unit_file "$final_dir/$service_name" "$units/$service_name" || \
      ! replace_unit_file "$final_dir/$timer_name" "$units/$timer_name" || \
      ! replace_symlink "$final_dir" "$current_path" || \
      ! install_post_switch_guard "$final_dir"; then
    rollback_release_switch \
      "$backup_dir" "$final_dir" "$release_base" "$current_path" "$units" || true
    /bin/rm -rf -- "$backup_dir"
    return 1
  fi
  /bin/rm -rf -- "$backup_dir"
  return 0
}

main() {
  if [[ "${FL_SIGNAL_UTILITY_INSTALL_APPROVAL:-}" != "$approval_phrase" ]]; then
    echo "Exact utility-intake atomic-install approval is required" >&2
    exit 64
  fi
  if [[ "$EUID" -ne 0 ]]; then
    echo "Run the installer as root" >&2
    exit 64
  fi

  local repo_root="${1:-}"
  if [[ -z "$repo_root" || "$repo_root" != /* || \
        ! -d "$repo_root/.git" && ! -f "$repo_root/.git" ]]; then
    echo "Pass the absolute reviewed repository/worktree root" >&2
    exit 64
  fi
  if ! timer_is_preinstall_safe || ! service_is_preinstall_safe; then
    echo "Utility timer/service must be inactive and the timer disabled before staging" >&2
    exit 65
  fi
  if [[ ! -x "$python_bin" ]]; then
    echo "Production virtualenv Python is unavailable" >&2
    exit 1
  fi

  local manifest="$repo_root/ops/droplet/utility-intake-install.sha256"
  cd "$repo_root"
  /usr/bin/sha256sum --check --strict "$manifest"
  /usr/bin/install -d -o root -g root -m 0755 "$release_root"
  /usr/bin/install -d -o andy -g andy -m 0700 \
    "$data_root" "$data_root/runs" "$data_root/receipts" "$data_root/install-checks"

  local manifest_sha release_id stage_dir final_dir check_root
  manifest_sha="$(/usr/bin/sha256sum "$manifest" | /usr/bin/cut -d' ' -f1)"
  release_id="$(/bin/date -u +%Y%m%dT%H%M%SZ)-${manifest_sha:0:16}-$$"
  stage_dir="$release_root/.stage-$release_id"
  final_dir="$release_root/$release_id"
  check_root="$data_root/install-checks/install-$release_id"
  if path_exists "$stage_dir" || path_exists "$final_dir"; then
    echo "Refusing to reuse a release generation" >&2
    exit 1
  fi
  trap '/bin/rm -rf -- "$stage_dir"' EXIT
  stage_release "$repo_root" "$stage_dir"
  validate_staged_release "$stage_dir" "$check_root"
  switch_release "$stage_dir" "$final_dir"
  trap - EXIT

  echo "Installed reviewed utility-intake release $release_id atomically."
  echo "Timer remains inactive and disabled; preserved startup check at $check_root"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
