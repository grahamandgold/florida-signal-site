#!/usr/bin/env python3
"""Select Acclaim dates without prematurely treating a forming day as ready."""

import datetime as dt
import json
import os
import sys


def collection_end_date(now=None):
    """Return the newest date safe to treat as a collection target."""
    now = now or dt.datetime.now()
    return now.date() if now.hour >= 12 else now.date() - dt.timedelta(days=1)


def candidate_dates(base, cap, state_file, now=None):
    end = collection_end_date(now)
    done = set()
    if os.path.exists(state_file):
        try:
            with open(state_file, encoding="utf-8") as handle:
                state = json.load(handle)
            done = {
                date_text
                for date_text, value in state.get("dates", {}).items()
                if value.get("status") == "done"
            }
        except (OSError, ValueError, AttributeError):
            pass
    output = []
    cursor = base + dt.timedelta(days=1)
    while cursor <= end and len(output) < cap:
        if cursor.isoformat() not in done:
            output.append(cursor)
        cursor += dt.timedelta(days=1)
    return output


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: acclaim_targets.py VERIFIED_MAX MAX_DATES STATE_FILE")
    base = dt.date.fromisoformat(sys.argv[1])
    for date_value in candidate_dates(base, int(sys.argv[2]), sys.argv[3]):
        print(f"{date_value.month}/{date_value.day}/{date_value.year}|{date_value.isoformat()}")


if __name__ == "__main__":
    main()
