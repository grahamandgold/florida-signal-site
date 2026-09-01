#!/usr/bin/env bash
set -euo pipefail

# Atomic, timer-default-off installer for the utility-intake verifier. This
# script copies reviewed bytes and proves startup receipting; it never reloads
# systemd, enables a timer, starts a service, contacts Supabase, or reads a
# production secret.

approval="${FL_SIGNAL_UTILITY_INSTALL_APPROVAL:-}"
if [[ "$approval" != "I_APPROVE_EXACT_UTILITY_INTAKE_ATOMIC_INSTALL" ]]; then
  echo "Exact utility-intake atomic-install approval is required" >&2
  exit 64
fi
if [[ "$EUID" -ne 0 ]]; then
  echo "Run the installer as root" >&2
  exit 64
fi

repo_root="${1:-}"
if [[ -z "$repo_root" || "$repo_root" != /* || ! -d "$repo_root/.git" && ! -f "$repo_root/.git" ]]; then
  echo "Pass the absolute reviewed repository/worktree root" >&2
  exit 64
fi

manifest="$repo_root/ops/droplet/utility-intake-install.sha256"
cd "$repo_root"
/usr/bin/sha256sum --check --strict "$manifest"

install_root="/srv/grahamandgold/florida-signal"
script_root="$install_root/app/scripts"
tool_root="$install_root/tools"
unit_root="/etc/systemd/system"
data_root="$install_root/staging/data/utility-intake"

/usr/bin/install -d -o root -g root -m 0755 "$script_root" "$tool_root"
/usr/bin/install -d -o andy -g andy -m 0700 \
  "$data_root" "$data_root/runs" "$data_root/receipts" "$data_root/install-checks"

atomic_install() {
  local source="$1"
  local destination="$2"
  local mode="$3"
  local owner="$4"
  local group="$5"
  local temporary="${destination}.install.$$"
  /usr/bin/install -o "$owner" -g "$group" -m "$mode" "$source" "$temporary"
  /usr/bin/cmp -s "$source" "$temporary"
  /bin/sync -f "$temporary"
  /bin/mv -f "$temporary" "$destination"
  /bin/sync -f "$(/usr/bin/dirname "$destination")"
  /usr/bin/cmp -s "$source" "$destination"
}

atomic_install "$repo_root/ops/droplet/utility_intake_production.py" \
  "$script_root/utility_intake_production.py" 0644 root root
atomic_install "$repo_root/ops/droplet/utility_intake_shadow.py" \
  "$script_root/utility_intake_shadow.py" 0644 root root
atomic_install "$repo_root/ops/droplet/florida-utility-intake-wait.sh" \
  "$tool_root/florida-utility-intake-wait.sh" 0755 root root
atomic_install "$repo_root/ops/droplet/florida-utility-intake.service" \
  "$unit_root/florida-utility-intake.service" 0644 root root
atomic_install "$repo_root/ops/droplet/florida-utility-intake.timer" \
  "$unit_root/florida-utility-intake.timer" 0644 root root

python_bin="$install_root/app/.venv/bin/python3"
if [[ ! -x "$python_bin" ]]; then
  echo "Production virtualenv Python is unavailable" >&2
  exit 1
fi

# Prove the sibling import from the installed path before testing the startup
# receipt path with an intentionally absent credential file and an empty env.
"$python_bin" -c 'import pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
import utility_intake_shadow
import utility_intake_production
assert utility_intake_production.SHADOW_IMPORT_ERROR is None
assert utility_intake_production.shadow is utility_intake_shadow' "$script_root"

check_id="install-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$$"
check_root="$data_root/install-checks/$check_id"
/usr/bin/install -d -o andy -g andy -m 0700 "$check_root"
set +e
/usr/sbin/runuser -u andy -- /usr/bin/env -i PATH=/usr/bin:/bin \
  "$python_bin" "$script_root/utility_intake_production.py" \
  --sqlite-path "$install_root/staging/db/permits.sqlite" \
  --writer-lock-path "$install_root/app/db/.writer.lock" \
  --evidence-dir "$check_root/runs" \
  --receipt-dir "$check_root/receipts" \
  --latest-attempt-pointer "$check_root/latest-attempt.json" \
  --latest-success-pointer "$check_root/latest-success.json" \
  --credential-file "$check_root/intentionally-absent.env" \
  --run-id "utility-install-startup-$check_id" \
  >"$check_root/stdout.json" 2>"$check_root/stderr.log"
check_rc=$?
set -e
if [[ "$check_rc" -ne 3 ]]; then
  echo "Installed startup receipt self-test returned $check_rc, expected 3" >&2
  exit 1
fi
"$python_bin" -c 'import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
pointer = json.loads((root / "latest-attempt.json").read_text())
receipt = json.loads((root / "receipts" / pathlib.Path(pointer["receipt_path"]).name).read_text())
assert pointer["pointer_kind"] == "attempt"
assert receipt["status"] == "failed"
assert receipt["startup_stage"] == "credential_file"
assert receipt["safety"]["remote_methods"] == []
assert not (root / "latest-success.json").exists()' "$check_root"

/usr/bin/systemd-analyze verify \
  "$unit_root/florida-utility-intake.service" \
  "$unit_root/florida-utility-intake.timer"

echo "Installed reviewed utility-intake bytes; timer remains untouched/default-off."
echo "Preserved startup receipt self-test at $check_root"
