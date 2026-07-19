# Clerk catch-up on droplet — OPERATIONS & ROLLBACK (superseded deploy note)

STATUS 2026-07-19: DEPLOYED + HARDENED. Units installed on florida-signal-runtime from GitHub-tracked
files (this directory). Venv: /srv/grahamandgold/florida-signal/.venv-clerk-catchup (paramiko pinned via
requirements-clerk-catchup.txt). Runs as andy, weekdays 18:10 UTC (+ ≤120s jitter), Persistent=true.

HISTORY: bundle authored + pushed by Claude 2026-07-19 with deploy deferred until after shadow-gate run 5;
installed early the same day (12:59–13:00 EDT) by the operator via Codex, incl. one unit revision (User=andy)
after a first-start failure (root could not see user-site paramiko). Hardened + venv'd by Claude same day with
operator authorization. GATE DISCLOSURE: an unrelated unit was installed and manually executed on the host
between shadow runs 4 and 5 (disjoint schedules/locks/code/data); scorer evidence must not be described as
from an unchanged host.

HEALTH CHECK (integrated into nightly social-graphics report task):
  ssh florida 'systemctl is-active florida-clerk-catchup.timer; systemctl show florida-clerk-catchup.service -p Result,ExecMainStatus,ExecMainExitTimestamp'
  journalctl -u florida-clerk-catchup.service --since "-3 days" --no-pager | tail -20
  Alert if: timer inactive/disabled, Result != success, no success in 3 business days, or DB max(business_date)
  lags the Clerk server's newest published date by > 2 business days.

ROLLBACK (restores Claude-task path):
  ssh florida 'sudo systemctl disable --now florida-clerk-catchup.timer'
  (optional remove: sudo rm /etc/systemd/system/florida-clerk-catchup.{service,timer} && sudo systemctl daemon-reload)
  Then re-enable Claude scheduled task "broward-clerk-catchup-sync" (Scheduled sidebar → enable; it is DISABLED,
  labeled EMERGENCY ROLLBACK ONLY — never deleted). Rollback does not touch the authoritative droplet Clerk
  ingest or any verified data; the catch-up only ever inserts missing business dates idempotently.
