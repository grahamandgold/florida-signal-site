#!/usr/bin/env python3
"""Retired Mac Sunbiz deed-party writer.

The supported resolver runs on the Florida droplet and reads the local Sunbiz
SFTP corpus. The former Mac implementation queried search.sunbiz.org, which
returns HTTP 403, then overwrote authoritative cache rows with ERROR results.

This tombstone intentionally contains no network or database-writing code.
"""


def main() -> int:
    print(
        "RETIRED: Mac Sunbiz web-search writer is disabled; "
        "use the droplet local-SFTP-corpus resolver."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
