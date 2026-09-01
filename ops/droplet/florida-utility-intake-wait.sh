#!/usr/bin/env bash
set -euo pipefail

# Bound the dependency wait inside the unit's larger TimeoutStartSec. Both
# dependencies are existing oneshot services; inactive means their current run
# is terminal. This helper never starts, stops, or restarts either unit.
readonly max_wait_seconds=600
readonly poll_seconds=2
readonly deadline=$((SECONDS + max_wait_seconds))
readonly units=(florida-accela.service florida-sync.service)

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
