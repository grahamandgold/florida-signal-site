#!/usr/bin/env python3
"""Classify an Acclaim zero-result response without losing unreleased weekdays."""

import datetime as dt
import sys


def classify_empty(target_date, verified_through, today=None):
    """Return ``done`` only when a zero-result date is safe to close.

    Acclaim can temporarily render an explicit zero-result grid before Broward
    releases a weekday.  A weekday newer than the authoritative SFTP floor must
    therefore remain retryable.  Past Saturdays and Sundays may safely close;
    the current day always remains retryable because its grid can still grow.
    """
    today = today or dt.date.today()
    if target_date >= today:
        return "retry"
    if target_date > verified_through and target_date.weekday() < 5:
        return "retry"
    return "done"


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: acclaim_empty_policy.py TARGET_DATE VERIFIED_THROUGH"
        )
    target_date = dt.date.fromisoformat(sys.argv[1])
    verified_through = dt.date.fromisoformat(sys.argv[2])
    print(classify_empty(target_date, verified_through))


if __name__ == "__main__":
    main()
