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
    today = (now or dt.datetime.now()).date()
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
    while cursor <= end:
        # A completed past date is immutable enough to skip. The current day's
        # public grid is still forming, so recheck it on every post-noon run;
        # acclaim_upsert.py makes those refreshes idempotent.
        if cursor.isoformat() not in done or cursor == today:
            output.append(cursor)
        cursor += dt.timedelta(days=1)

    if len(output) <= cap:
        return output

    # Keep oldest-first catch-up, but reserve one slot for today's refresh so a
    # long offline backlog cannot delay same-day intelligence by another day.
    if end == today and today in output and cap > 0:
        return output[: max(0, cap - 1)] + [today]
    return output[:cap]


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: acclaim_targets.py VERIFIED_MAX MAX_DATES STATE_FILE")
    base = dt.date.fromisoformat(sys.argv[1])
    for date_value in candidate_dates(base, int(sys.argv[2]), sys.argv[3]):
        print(f"{date_value.month}/{date_value.day}/{date_value.year}|{date_value.isoformat()}")


if __name__ == "__main__":
    main()
