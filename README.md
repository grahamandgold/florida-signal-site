# Florida Signal

**New here, human or agent? Read [`NIGHT_HANDOFF_2026-08-11.md`](NIGHT_HANDOFF_2026-08-11.md),
[`SYSTEM_STATE_2026-08-11.md`](SYSTEM_STATE_2026-08-11.md) and
[`EDITORIAL_LOOP_RUNBOOK.md`](EDITORIAL_LOOP_RUNBOOK.md) first.**
They are the verified front door for production health, the live Record → Candidate loop,
public exposure, local-only site work and remaining launch blockers.
Earlier dated checkpoints are preserved as historical evidence.
**The scorer and collectors are not in this repository** — they live in `grahamandgold/florida-signal`.

Florida Signal is Broward-wide, source-first development intelligence launching city by city. The public root `/` is the signup-first home of the **Florida Signal Brief**. It launches Mondays at 7 a.m. ET without hard-coding a weekly cadence into the product name. The launch page collects email and ZIP, explains the four-part Signal standard and keeps the research experience out of the conversion path. The preserved research site remains available at `/fort-lauderdale/`; Fort Lauderdale is its first live desk. Other Broward municipality paths use one shared “coming soon” template without dates or coverage promises.

There are **two sites, with two different jobs**: the public Florida Signal reader/newsletter site
and the private Florida Signal Newsroom CMS. Live Desk, Agenda Watch, Brief, Data Explorer and
Triage are sections inside the private Newsroom; they are not additional public websites.

## Run locally

**One-click (Andy's Mac):** open the **Florida Signal Desk** or **The Data Wire** app (Dock/Desktop), or run:

```bash
bash ops/launch_local.sh
```

That starts both servers, loads the private desk token from `~/.florida_signal_datawire_token`, loads Mailchimp credentials from `~/.florida_signal_mailchimp_env`, and enables local desk auto-unlock (`DATA_WIRE_LOCAL_AUTOUNLOCK=1`, loopback-only).

**Manual:**

```bash
export DATA_WIRE_ADMIN_TOKEN='replace-with-a-long-private-token'
python3 cms/server.py --port 8788
```

In a second terminal:

```bash
export FLORIDA_SIGNAL_CMS_URL='http://127.0.0.1:8788'
export FLORIDA_SIGNAL_CMS_MARKET='broward'
python3 server.py --bind 127.0.0.1 --port 4173
```

Open the newsletter front door at `http://127.0.0.1:4173/`, the preserved research site at
`http://127.0.0.1:4173/fort-lauderdale/`, and the private Florida Signal Newsroom at
`http://127.0.0.1:8788/`.

### Unlock the private Florida Signal Newsroom

1. Start `cms/server.py` with `DATA_WIRE_ADMIN_TOKEN` as shown above.
2. Open `http://127.0.0.1:8788/`.
3. Leave the market set to `broward`; each brief separately requires a city.
4. Paste the exact same token into **Private desk token** and choose **Open desk**.

The token is kept in that tab's `sessionStorage`; it disappears when the browser session ends. Never place it in public HTML, `app.js`, a screenshot or a committed `.env` file. The CMS starts empty on purpose and only approved, source-linked packets reach the public site.

The local server provides same-origin meeting, storm, CMS, agenda-recon and subscriber endpoints. Copy `.env.example` into your private runtime environment and supply credentials there; never commit secrets.

## Operating handoff

- [`NIGHT_HANDOFF_2026-08-11.md`](NIGHT_HANDOFF_2026-08-11.md) — tonight's implementation,
  scheduled-task audit, same-day Broward ownership, tests and exact next work.
- [`NEWSLETTER_LAUNCH_HANDOFF_2026-08-15.md`](NEWSLETTER_LAUNCH_HANDOFF_2026-08-15.md) — the
  newsletter-first routing decision, preserved full-site recovery point, landing verification and
  first-edition state.
- [`AUTOMATION_AND_AGENT_INVENTORY_2026-08-11.md`](AUTOMATION_AND_AGENT_INVENTORY_2026-08-11.md) —
  what actually runs, what is paused, unverified Grok/Claude surfaces and the safe loop/graph design.
- [`SYSTEM_STATE_2026-08-11.md`](SYSTEM_STATE_2026-08-11.md) — current operational, data, editorial, Mailchimp, analytics and launch truth.
- [`EDITORIAL_LOOP_RUNBOOK.md`](EDITORIAL_LOOP_RUNBOOK.md) — live Candidate schedules, evidence contract, human gate and recovery.
- [`SITE_MAINTENANCE_RUNBOOK.md`](SITE_MAINTENANCE_RUNBOOK.md) — release checks, hourly browser monitor and incident response.
- [`ops/droplet/README_PUBLIC_API.md`](ops/droplet/README_PUBLIC_API.md) — production API, DNS/TLS, secrets, durable data, update and rollback procedure.
- [`SYSTEM_STATE_2026-07-28.md`](SYSTEM_STATE_2026-07-28.md) — historical July checkpoint.
- [`REMAINING_WORK_REGISTER_2026-07-28.md`](REMAINING_WORK_REGISTER_2026-07-28.md) — unresolved decisions and launch blockers.
- [`FLORIDA_SIGNAL_BUILD_REPORT.md`](FLORIDA_SIGNAL_BUILD_REPORT.md) — source cadence, live versus scheduled updates, date methodology, CMS/Mailchimp state and production runbook.
- [`LIVE_DATA_OPERATIONS_HANDOFF.md`](LIVE_DATA_OPERATIONS_HANDOFF.md) — exact live-stat definitions, observed source health, update/recovery procedures and daily operating sequence.
- [`AI_HANDOFF.md`](AI_HANDOFF.md) — data, editorial, multi-city, Storm Watch and implementation rules for the next AI or developer.
- [`SOCIAL_MEDIA_ASSET_GUIDE.md`](SOCIAL_MEDIA_ASSET_GUIDE.md) — logo inventory, channel masters, export command, captions and sharing rules.
- [`FLORIDA_SIGNAL_TAGGING_SYSTEM.md`](FLORIDA_SIGNAL_TAGGING_SYSTEM.md) — controlled site and CMS taxonomy.
- [`cms/README.md`](cms/README.md) — Data Wire endpoints, Story Packet gates and production hardening.
- [`BRAND_KIT.md`](BRAND_KIT.md) and [`fort-lauderdale/brand/`](fort-lauderdale/brand/) — brand rules, social masters and newsletter assets.
- [`brand/florida-signal-logo-avatar-kit-2026-08-16/`](brand/florida-signal-logo-avatar-kit-2026-08-16/) — approved website, newsletter and social lockups/avatars plus the vector-master production brief.
- [`assets/photos/README.md`](assets/photos/README.md) — licensed Adobe Stock provenance and usage restrictions.

## Data standard

Charts and rankings use the public event date—such as permit `applied_date`, Clerk `recording_date_iso` or a company registration date. Pull, cache and enrichment timestamps describe freshness only; a batch arrival never substitutes for the underlying event date.

The public CMS adapter accepts only sourced, approved or cleared output. Storm Watch cites NOAA/NHC and is not an official warning service.

Powered by Graham & Gold LLC.
