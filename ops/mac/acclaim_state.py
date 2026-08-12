#!/usr/bin/env python3
"""Persist Acclaim backfill progress without flagging a forming day as missing.

Usage: acclaim_state.py STATEFILE ISO_DATE status pages found inserted verified_max [total_shown]
"""

import datetime as dt
import json
import os
import sys

from acclaim_targets import collection_end_date


def update_state(
    state_file,
    iso_date,
    status,
    pages,
    found,
    inserted,
    verified_max,
    total_shown=0,
    now=None,
):
    state = {"dates": {}}
    if os.path.exists(state_file):
        try:
            with open(state_file, encoding="utf-8") as handle:
                state = json.load(handle)
        except (OSError, ValueError, TypeError):
            state = {"dates": {}}
    state.setdefault("dates", {})

    observed_at = now or dt.datetime.now(dt.timezone.utc)
    observed_at_text = observed_at.astimezone(dt.timezone.utc).isoformat()
    state["dates"][iso_date] = {
        "status": status,
        "pages": pages,
        "found": found,
        "total_shown": total_shown,
        "inserted": inserted,
        "skipped": max(0, found - inserted),
        "at": observed_at_text,
    }
    state["last_run_at"] = observed_at_text
    state["verified_max_at_last_run"] = verified_max
    done = [date_text for date_text, value in state["dates"].items() if value.get("status") == "done"]
    if done:
        state["last_completed_date"] = max(done)

    # Match acclaim_targets.py: before noon, today's still-forming grid is not backlog.
    base = dt.date.fromisoformat(verified_max)
    local_now = observed_at.astimezone() if observed_at.tzinfo else observed_at
    end = collection_end_date(local_now)
    backlog = []
    cursor = base + dt.timedelta(days=1)
    while cursor <= end:
        if state["dates"].get(cursor.isoformat(), {}).get("status") != "done":
            backlog.append(cursor.isoformat())
        cursor += dt.timedelta(days=1)
    state["backlog_remaining"] = backlog

    temporary_file = str(state_file) + ".tmp"
    with open(temporary_file, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
    os.replace(temporary_file, state_file)
    return state


def main():
    if len(sys.argv) not in {8, 9}:
        raise SystemExit(
            "usage: acclaim_state.py STATEFILE ISO_DATE status pages found inserted verified_max [total_shown]"
        )
    state = update_state(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
        int(sys.argv[4]),
        int(sys.argv[5]),
        int(sys.argv[6]),
        sys.argv[7],
        int(sys.argv[8]) if len(sys.argv) > 8 else 0,
    )
    print("state: %s %s (backlog %d)" % (sys.argv[2], sys.argv[3], len(state["backlog_remaining"])))


if __name__ == "__main__":
    main()
