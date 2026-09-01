#!/usr/bin/env bash
set -euo pipefail

# Bound the dependency wait inside the unit's larger TimeoutStartSec. Both
# dependencies are existing oneshot services; inactive means their current run
# is terminal. This helper never starts, stops, or restarts either unit.
readonly max_wait_seconds=600
readonly poll_seconds=2
readonly deadline=$((SECONDS + max_wait_seconds))
readonly units=(florida-accela.service florida-sync.service)
readonly credential_file=/srv/grahamandgold/florida-signal/secrets/florida-utility-intake.env

if [[ -L "$credential_file" || ! -f "$credential_file" ]]; then
  echo "dedicated utility credential file is missing or unsafe" >&2
  exit 64
fi
credential_mode="$(/usr/bin/stat --format=%a -- "$credential_file")"
credential_owner="$(/usr/bin/stat --format=%U:%G -- "$credential_file")"
if [[ "$credential_mode" != "600" || "$credential_owner" != "root:root" ]]; then
  echo "dedicated utility credential file must be root:root mode 600" >&2
  exit 64
fi

for unit in "${units[@]}"; do
  while true; do
    load_state="$(/usr/bin/systemctl show --property=LoadState --value -- "$unit")"
    active_state="$(/usr/bin/systemctl show --property=ActiveState --value -- "$unit")"
    result="$(/usr/bin/systemctl show --property=Result --value -- "$unit")"
    if [[ "$load_state" != "loaded" ]]; then
      echo "dependency unavailable: $unit ($load_state)" >&2
      exit 65
    fi
    if [[ "$active_state" == "failed" || ( -n "$result" && "$result" != "success" ) ]]; then
      echo "dependency failed: $unit ($result)" >&2
      exit 65
    fi
    if [[ "$active_state" == "inactive" ]]; then
      break
    fi
    if (( SECONDS >= deadline )); then
      echo "dependency wait timed out after ${max_wait_seconds}s: $unit ($active_state)" >&2
      exit 75
    fi
    /usr/bin/sleep "$poll_seconds"
  done
done
