#!/usr/bin/env python3
"""Persist Acclaim backfill progress.
Usage: acclaim_state.py STATEFILE ISO_DATE status pages found inserted verified_max
Updates the per-date record + top-level cursor and recomputes backlog_remaining.
"""
import json, os, sys, datetime

statef, iso, status, pages, found, inserted, verified_max = (
    sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]),
    int(sys.argv[5]), int(sys.argv[6]), sys.argv[7])
total_shown = int(sys.argv[8]) if len(sys.argv) > 8 else 0

st = {"dates": {}}
if os.path.exists(statef):
    try:
        st = json.load(open(statef))
    except Exception:
        st = {"dates": {}}
st.setdefault("dates", {})

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
st["dates"][iso] = {
    "status": status, "pages": pages, "found": found, "total_shown": total_shown,
    "inserted": inserted, "skipped": max(0, found - inserted), "at": now,
}
st["last_run_at"] = now
st["verified_max_at_last_run"] = verified_max
done = [d for d, v in st["dates"].items() if v.get("status") == "done"]
if done:
    st["last_completed_date"] = max(done)

# Backlog = calendar dates after verified_max up to today not yet done.
base = datetime.date.fromisoformat(verified_max)
today = datetime.date.today()
backlog = []
d = base + datetime.timedelta(days=1)
while d <= today:
    if st["dates"].get(d.isoformat(), {}).get("status") != "done":
        backlog.append(d.isoformat())
    d += datetime.timedelta(days=1)
st["backlog_remaining"] = backlog

tmp = statef + ".tmp"
json.dump(st, open(tmp, "w"), indent=2)
os.replace(tmp, statef)
print("state: %s %s (backlog %d)" % (iso, status, len(backlog)))
