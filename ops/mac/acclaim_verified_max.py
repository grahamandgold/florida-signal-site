#!/usr/bin/env python3
"""Read the latest verified Clerk business date without ever rewinding the cursor."""

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request


DEFAULT_SUPABASE_URL = "https://jrjewmzkyluxdywyusrw.supabase.co"
DEFAULT_PUBLISHABLE_KEY = "sb_publishable_dEyBjKE_vcTj3YYx4p6XvA_xnkVW3Wb"


def _valid_date(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        return None


def cached_verified_max(state_file):
    try:
        with open(state_file, encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    return _valid_date(state.get("verified_max_at_last_run"))


def fetch_verified_max(urlopen=urllib.request.urlopen, attempts=3, sleep=time.sleep):
    base = os.environ.get("SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", DEFAULT_PUBLISHABLE_KEY)
    url = (
        base
        + "/rest/v1/broward_clerk_records_run"
        + "?select=business_date&order=business_date.desc&limit=1"
    )
    last_error = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            headers={
                "apikey": key,
                "User-Agent": "Florida-Signal/1.0 (+https://thefloridasignal.com)",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
            value = _valid_date(payload[0].get("business_date") if payload else None)
            if not value:
                raise ValueError("verified Clerk query returned no valid business_date")
            return value
        except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError) as error:
            last_error = error
            if attempt < attempts:
                sleep(attempt)
    raise RuntimeError("verified Clerk query failed after retries: %s" % last_error)


def resolve_verified_max(state_file):
    try:
        return fetch_verified_max(), False
    except RuntimeError as error:
        cached = cached_verified_max(state_file)
        if cached:
            print(
                "WARNING: %s; retaining cached verified max %s" % (error, cached),
                file=sys.stderr,
            )
            return cached, True
        raise


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: acclaim_verified_max.py STATE_FILE")
    try:
        value, _used_cache = resolve_verified_max(sys.argv[1])
    except RuntimeError as error:
        raise SystemExit("FATAL: %s and no cached verified max is available" % error)
    print(value)


if __name__ == "__main__":
    main()
