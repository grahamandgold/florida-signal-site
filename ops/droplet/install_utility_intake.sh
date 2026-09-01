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

systemd_active_state() {
  local value
  if value="$(/usr/bin/systemctl is-active "$1" 2>/dev/null)"; then
    :
  fi
  printf '%s\n' "${value:-unavailable}"
}

systemd_enabled_state() {
  local value
  if value="$(/usr/bin/systemctl is-enabled "$1" 2>/dev/null)"; then
    :
  fi
  printf '%s\n' "${value:-unavailable}"
}

timer_is_preinstall_safe() {
  local active enabled
  active="$(systemd_active_state "$timer_name")"
  enabled="$(systemd_enabled_state "$timer_name")"
  if [[ "$active" == "inactive" && "$enabled" == "disabled" ]]; then
    return 0
  fi
  [[ "$active" == "unknown" && "$enabled" == "not-found" ]] && \
    ! path_exists "$unit_root/$timer_name"
}

service_is_preinstall_safe() {
  local active
  active="$(systemd_active_state "$service_name")"
  [[ "$active" == "inactive" || "$active" == "unknown" ]]
}

timer_is_postswitch_safe() {
  local active enabled
  active="$(systemd_active_state "$timer_name")"
  enabled="$(systemd_enabled_state "$timer_name")"
  [[ "$active" == "inactive" && "$enabled" == "disabled" ]]
}

service_is_postswitch_safe() {
  [[ "$(systemd_active_state "$service_name")" == "inactive" ]]
}

copy_candidate() {
  local source="$1" destination="$2" mode="$3"
  # main runs as root, so newly staged files are root-owned without an
  # ownership-changing second pass. Keeping this primitive unprivileged also
  # lets the release-byte contract run in a disposable test directory.
  /usr/bin/install -m "$mode" "$source" "$destination" || return 1
  /usr/bin/cmp -s "$source" "$destination" || return 1
  /bin/sync -f "$destination" || return 1
}

freeze_manifest() {
  local source="$1" destination="$2"
  /usr/bin/python3 -c 'import os, pathlib, re, stat, sys
source = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
fd = os.open(source, flags)
try:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 100_000:
        raise SystemExit("release manifest is not a bounded regular file")
    raw = bytearray()
    while len(raw) < before.st_size:
        chunk = os.read(fd, before.st_size - len(raw))
        if not chunk:
            raise SystemExit("release manifest changed during read")
        raw.extend(chunk)
    if os.read(fd, 1):
        raise SystemExit("release manifest changed during read")
    after = os.fstat(fd)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != \
       (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise SystemExit("release manifest changed during read")
finally:
    os.close(fd)

expected = {
    "ops/droplet/utility_intake_production.py",
    "ops/droplet/utility_intake_shadow.py",
    "ops/droplet/florida-utility-intake-wait.sh",
    "ops/droplet/florida-utility-intake.service",
    "ops/droplet/florida-utility-intake.timer",
}
seen = set()
for line in bytes(raw).decode("ascii").splitlines():
    match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_./-]+)", line)
    if not match or match.group(2) not in expected or match.group(2) in seen:
        raise SystemExit("release manifest contract is not exact")
    seen.add(match.group(2))
if seen != expected:
    raise SystemExit("release manifest contract is not exact")

out_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
out = os.open(destination, out_flags, 0o600)
try:
    offset = 0
    while offset < len(raw):
        written = os.write(out, raw[offset:])
        if written <= 0:
            raise OSError("release manifest write stalled")
        offset += written
    os.fchmod(out, 0o600)
    os.fsync(out)
finally:
    os.close(out)
parent = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(parent)
finally:
    os.close(parent)' "$source" "$destination"
}

copy_release_files() {
  local repo_root="$1" stage_dir="$2"
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

verify_staged_release_manifest() {
  local manifest="$1" stage_dir="$2"
  /usr/bin/python3 -c 'import hashlib, os, pathlib, re, stat, sys
manifest = pathlib.Path(sys.argv[1])
stage = pathlib.Path(sys.argv[2])
mapping = {
    "ops/droplet/utility_intake_production.py": "utility_intake_production.py",
    "ops/droplet/utility_intake_shadow.py": "utility_intake_shadow.py",
    "ops/droplet/florida-utility-intake-wait.sh": "florida-utility-intake-wait.sh",
    "ops/droplet/florida-utility-intake.service": "florida-utility-intake.service",
    "ops/droplet/florida-utility-intake.timer": "florida-utility-intake.timer",
}
expected = {}
for line in manifest.read_text(encoding="ascii").splitlines():
    match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_./-]+)", line)
    if not match or match.group(2) not in mapping or match.group(2) in expected:
        raise SystemExit("frozen release manifest contract is not exact")
    expected[match.group(2)] = match.group(1)
if set(expected) != set(mapping):
    raise SystemExit("frozen release manifest contract is not exact")
for relative, digest in expected.items():
    path = stage / mapping[relative]
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 20_000_000:
            raise SystemExit(f"staged release file is unsafe: {relative}")
        hashed = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(remaining, 1024 * 1024))
            if not chunk:
                raise SystemExit(f"staged release file changed: {relative}")
            hashed.update(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise SystemExit(f"staged release file changed: {relative}")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != \
           (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise SystemExit(f"staged release file changed: {relative}")
        if hashed.hexdigest() != digest:
            raise SystemExit(f"staged release hash mismatch: {relative}")
    finally:
        os.close(fd)' "$manifest" "$stage_dir"
}

stage_release() {
  local repo_root="$1" stage_dir="$2"
  /usr/bin/install -d -m 0755 "$stage_dir"
  freeze_manifest \
    "$repo_root/ops/droplet/utility-intake-install.sha256" \
    "$stage_dir/.source-manifest.sha256"
  copy_release_files "$repo_root" "$stage_dir"
  verify_staged_release_manifest "$stage_dir/.source-manifest.sha256" "$stage_dir"
  /bin/sync -f "$stage_dir"
}

validate_staged_release() {
  local stage_dir="$1" check_root="$2"
  # Recheck the frozen manifest immediately before validation. Repository
  # source paths are no longer consulted after stage_release returns.
  verify_staged_release_manifest "$stage_dir/.source-manifest.sha256" "$stage_dir"
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
    /bin/cp -a "$path" "$backup_dir/$name" || return 1
    : >"$backup_dir/$name.present" || return 1
  fi
  return 0
}

verify_restored_path() {
  local path="$1" backup_dir="$2" name="$3"
  /usr/bin/python3 -c 'import os, pathlib, stat, sys
path = pathlib.Path(sys.argv[1])
backup = pathlib.Path(sys.argv[2]) / sys.argv[3]
present = pathlib.Path(sys.argv[2]) / (sys.argv[3] + ".present")
if not present.is_file():
    try:
        os.lstat(path)
    except FileNotFoundError:
        raise SystemExit(0)
    raise SystemExit("restored path should be absent")
try:
    expected = os.lstat(backup)
    actual = os.lstat(path)
except FileNotFoundError:
    raise SystemExit("restored path is absent")
if stat.S_IFMT(expected.st_mode) != stat.S_IFMT(actual.st_mode):
    raise SystemExit("restored path type differs")
if stat.S_IMODE(expected.st_mode) != stat.S_IMODE(actual.st_mode):
    raise SystemExit("restored path mode differs")
if (expected.st_uid, expected.st_gid) != (actual.st_uid, actual.st_gid):
    raise SystemExit("restored path ownership differs")
if stat.S_ISLNK(expected.st_mode):
    if os.readlink(backup) != os.readlink(path):
        raise SystemExit("restored symlink target differs")
elif stat.S_ISREG(expected.st_mode):
    if backup.read_bytes() != path.read_bytes():
        raise SystemExit("restored path bytes differ")
else:
    raise SystemExit("unsupported restored path type")' "$path" "$backup_dir" "$name"
}

restore_path() {
  local path="$1" backup_dir="$2" name="$3"
  if [[ -d "$path" && ! -L "$path" ]]; then
    return 1
  fi
  /bin/rm -f -- "$path" || return 1
  if [[ -f "$backup_dir/$name.present" ]]; then
    /bin/cp -a "$backup_dir/$name" "$path" || return 1
  fi
  return 0
}

replace_symlink() {
  local target="$1" destination="$2"
  local temporary="${destination}.install.$$"
  if [[ -d "$destination" && ! -L "$destination" ]]; then
    return 1
  fi
  /bin/rm -f -- "$temporary" || return 1
  /bin/ln -s "$target" "$temporary" || return 1
  # os.replace swaps the symlink inode itself and never follows a destination
  # symlink-to-directory; plain `mv` differs between GNU and BSD here.
  /usr/bin/python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' \
    "$temporary" "$destination" || return 1
  /bin/sync -f "$(/usr/bin/dirname "$destination")" || return 1
}

replace_unit_file() {
  local source="$1" destination="$2"
  local temporary="${destination}.install.$$"
  if [[ -d "$destination" && ! -L "$destination" ]]; then
    return 1
  fi
  /bin/rm -f -- "$temporary" || return 1
  /usr/bin/install -m 0644 "$source" "$temporary" || return 1
  /usr/bin/cmp -s "$source" "$temporary" || return 1
  /bin/sync -f "$temporary" || return 1
  /usr/bin/python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' \
    "$temporary" "$destination" || return 1
  /bin/sync -f "$(/usr/bin/dirname "$destination")" || return 1
}

reload_systemd() {
  /usr/bin/systemctl daemon-reload >/dev/null 2>&1
}

restore_timer_state() {
  local prior_active="$1" prior_enabled="$2" prior_service_active="$3" units="$4"
  local failed=0
  if path_exists "$units/$timer_name"; then
    if ! /usr/bin/systemctl disable --now "$timer_name" >/dev/null 2>&1; then
      failed=1
    fi
  elif [[ "$prior_active" != "unknown" || "$prior_enabled" != "not-found" ]]; then
    failed=1
  fi
  if path_exists "$units/$service_name"; then
    if ! /usr/bin/systemctl stop "$service_name" >/dev/null 2>&1; then
      failed=1
    fi
  elif [[ "$prior_service_active" != "unknown" ]]; then
    failed=1
  fi
  if [[ "$(systemd_active_state "$timer_name")" != "$prior_active" ]] || \
      [[ "$(systemd_enabled_state "$timer_name")" != "$prior_enabled" ]] || \
      [[ "$(systemd_active_state "$service_name")" != "$prior_service_active" ]]; then
    failed=1
  fi
  [[ "$failed" -eq 0 ]]
}

write_recovery_required() {
  local recovery_root="$1" backup_dir="$2" final_dir="$3" failures="$4"
  local timer_active="$5" timer_enabled="$6" service_active="$7"
  /usr/bin/install -d -m 0700 "$recovery_root" || return 1
  /usr/bin/python3 -c 'import datetime, json, os, pathlib, sys, uuid
root = pathlib.Path(sys.argv[1])
if not root.is_absolute() or root.is_symlink() or not root.is_dir():
    raise SystemExit("recovery evidence directory is unsafe")
payload = {
    "schema_version": "FloridaSignalUtilityIntakeInstallRecoveryV1",
    "status": "recovery_required",
    "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "backup_dir": sys.argv[2],
    "failed_release": sys.argv[3],
    "failures": [item for item in sys.argv[4].split(",") if item],
    "timer_active": sys.argv[5],
    "timer_enabled": sys.argv[6],
    "service_active": sys.argv[7],
}
raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
path = root / ("recovery-required-" + str(os.getpid()) + "-" + uuid.uuid4().hex + ".json")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
fd = os.open(path, flags, 0o600)
try:
    offset = 0
    while offset < len(raw):
        written = os.write(fd, raw[offset:])
        if written <= 0:
            raise OSError("recovery evidence write stalled")
        offset += written
    os.fchmod(fd, 0o600)
    os.fsync(fd)
finally:
    os.close(fd)
directory = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(directory)
finally:
    os.close(directory)
print(path)' "$recovery_root" "$backup_dir" "$final_dir" "$failures" \
    "$timer_active" "$timer_enabled" "$service_active"
}

rollback_release_switch() {
  local backup_dir="$1" final_dir="$2" release_base="$3" current_path="$4" units="$5"
  local prior_active="$6" prior_enabled="$7" prior_service_active="$8" recovery_root="$9"
  local failures="" timer_active timer_enabled service_active evidence_path=""

  if ! restore_path "$current_path" "$backup_dir" current; then
    failures="${failures}restore_current,"
  fi
  if ! restore_path "$units/$service_name" "$backup_dir" service; then
    failures="${failures}restore_service,"
  fi
  if ! restore_path "$units/$timer_name" "$backup_dir" timer; then
    failures="${failures}restore_timer,"
  fi
  if ! /bin/sync -f "$release_base"; then
    failures="${failures}fsync_release_root,"
  fi
  if ! /bin/sync -f "$units"; then
    failures="${failures}fsync_unit_root,"
  fi
  if ! reload_systemd; then
    failures="${failures}daemon_reload,"
  fi
  if ! restore_timer_state \
      "$prior_active" "$prior_enabled" "$prior_service_active" "$units"; then
    failures="${failures}timer_state,"
  fi
  if ! verify_restored_path "$current_path" "$backup_dir" current; then
    failures="${failures}verify_current,"
  fi
  if ! verify_restored_path "$units/$service_name" "$backup_dir" service; then
    failures="${failures}verify_service,"
  fi
  if ! verify_restored_path "$units/$timer_name" "$backup_dir" timer; then
    failures="${failures}verify_timer,"
  fi

  timer_active="$(systemd_active_state "$timer_name")"
  timer_enabled="$(systemd_enabled_state "$timer_name")"
  service_active="$(systemd_active_state "$service_name")"
  if [[ "$timer_active" != "$prior_active" || \
        "$timer_enabled" != "$prior_enabled" || \
        "$service_active" != "$prior_service_active" ]]; then
    failures="${failures}verify_runtime_state,"
  fi
  if [[ -n "$failures" ]]; then
    if evidence_path="$(write_recovery_required \
      "$recovery_root" "$backup_dir" "$final_dir" "$failures" \
      "$timer_active" "$timer_enabled" "$service_active")"; then
      echo "Rollback incomplete; durable recovery evidence: $evidence_path" >&2
    elif evidence_path="$(write_recovery_required \
      "$backup_dir" "$backup_dir" "$final_dir" "$failures" \
      "$timer_active" "$timer_enabled" "$service_active")"; then
      echo "Rollback incomplete; fallback recovery evidence: $evidence_path" >&2
    else
      echo "Rollback incomplete and recovery evidence write failed; preserve $backup_dir" >&2
    fi
    echo "Timer state after failed rollback: $timer_active/$timer_enabled" >&2
    return 1
  fi
  return 0
}

install_post_switch_guard() {
  local final_dir="$1"
  /usr/bin/systemctl daemon-reload || return 1
  timer_is_postswitch_safe || return 1
  service_is_postswitch_safe || return 1
  [[ "$(/usr/bin/readlink "$current_link")" == "$final_dir" ]] || return 1
  [[ ! -L "$unit_root/$service_name" && ! -L "$unit_root/$timer_name" ]] || return 1
  /usr/bin/cmp -s "$final_dir/$service_name" "$unit_root/$service_name" || return 1
  /usr/bin/cmp -s "$final_dir/$timer_name" "$unit_root/$timer_name" || return 1
  "$python_bin" -c 'import pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
import utility_intake_shadow
import utility_intake_production
assert utility_intake_production.SHADOW_IMPORT_ERROR is None
assert utility_intake_production.shadow is utility_intake_shadow' "$current_link" || return 1
  /usr/bin/systemd-analyze verify \
    "$unit_root/$service_name" "$unit_root/$timer_name" || return 1
}

switch_release() {
  local stage_dir="$1" final_dir="$2"
  local release_base="${3:-$release_root}"
  local current_path="${4:-$current_link}"
  local units="${5:-$unit_root}"
  local recovery_root="${6:-$data_root/install-recovery-required}"
  local backup_dir prior_active prior_enabled prior_service_active
  if ! timer_is_preinstall_safe || ! service_is_preinstall_safe; then
    echo "Utility timer/service changed state before release switch" >&2
    return 1
  fi
  prior_active="$(systemd_active_state "$timer_name")"
  prior_enabled="$(systemd_enabled_state "$timer_name")"
  prior_service_active="$(systemd_active_state "$service_name")"
  if ! backup_dir="$(/usr/bin/mktemp -d "$release_base/.rollback.XXXXXX")"; then
    return 1
  fi
  if [[ -d "$current_path" && ! -L "$current_path" ]] || \
      [[ -d "$units/$service_name" && ! -L "$units/$service_name" ]] || \
      [[ -d "$units/$timer_name" && ! -L "$units/$timer_name" ]]; then
    /bin/rm -rf -- "$backup_dir"
    return 1
  fi
  save_path "$current_path" "$backup_dir" current || return 1
  save_path "$units/$service_name" "$backup_dir" service || return 1
  save_path "$units/$timer_name" "$backup_dir" timer || return 1
  /bin/sync -f "$backup_dir" || return 1

  if ! /bin/mv "$stage_dir" "$final_dir" || \
      ! replace_unit_file "$final_dir/$service_name" "$units/$service_name" || \
      ! replace_unit_file "$final_dir/$timer_name" "$units/$timer_name" || \
      ! replace_symlink "$final_dir" "$current_path" || \
      ! install_post_switch_guard "$final_dir"; then
    rollback_release_switch \
      "$backup_dir" "$final_dir" "$release_base" "$current_path" "$units" \
      "$prior_active" "$prior_enabled" "$prior_service_active" "$recovery_root" || return 1
    /bin/rm -rf -- "$backup_dir" || return 1
    return 1
  fi
  /bin/rm -rf -- "$backup_dir" || return 1
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

  /usr/bin/install -d -o root -g root -m 0755 "$release_root"
  /usr/bin/install -d -o andy -g andy -m 0700 \
    "$data_root" "$data_root/runs" "$data_root/receipts" \
    "$data_root/install-checks" "$data_root/install-recovery-required"

  local manifest_sha release_id stage_dir final_dir check_root nonce
  nonce="$(/bin/date -u +%Y%m%dT%H%M%SZ)-$$"
  stage_dir="$release_root/.stage-$nonce"
  if path_exists "$stage_dir"; then
    echo "Refusing to reuse a release generation" >&2
    exit 1
  fi
  trap '/bin/rm -rf -- "$stage_dir"' EXIT
  stage_release "$repo_root" "$stage_dir"
  manifest_sha="$(/usr/bin/sha256sum "$stage_dir/.source-manifest.sha256" | /usr/bin/cut -d' ' -f1)"
  release_id="${nonce}-${manifest_sha:0:16}"
  final_dir="$release_root/$release_id"
  check_root="$data_root/install-checks/install-$release_id"
  if path_exists "$final_dir"; then
    echo "Refusing to reuse a release generation" >&2
    exit 1
  fi
  validate_staged_release "$stage_dir" "$check_root"
  switch_release "$stage_dir" "$final_dir" "$release_root" "$current_link" \
    "$unit_root" "$data_root/install-recovery-required"
  trap - EXIT

  echo "Installed reviewed utility-intake release $release_id atomically."
  echo "Timer remains inactive and disabled; preserved startup check at $check_root"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
