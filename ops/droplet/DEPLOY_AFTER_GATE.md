# Deploy clerk catch-up to droplet — AFTER shadow gate completes (post 2026-07-20 run-5 review)

The five-run gate rules forbid installs/daemon-reload on the droplet until run 5 is reviewed.
After Andy approves the gate report:

    scp ops/droplet/clerk_catchup.py florida:/srv/grahamandgold/florida-signal/app/
    scp ops/droplet/florida-clerk-catchup.{service,timer} florida:/tmp/
    ssh florida 'sudo mv /tmp/florida-clerk-catchup.* /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now florida-clerk-catchup.timer && systemctl list-timers florida-clerk-catchup*'

Confirm the droplet secrets env exposes SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (or edit env names in the script).
First run: `ssh florida 'sudo systemctl start florida-clerk-catchup.service && journalctl -u florida-clerk-catchup -n 20'`
Then retire the Claude scheduled task `broward-clerk-catchup-sync` (keep as backup for a week if preferred).
Verified from droplet 2026-07-19: SFTP :22 reachable, Supabase reachable, paramiko present.
NOTE: AcclaimWeb 403-blocks the droplet IP (datacenter block) — same-day preliminary pulls STAY on the Mac/Claude path by design.
