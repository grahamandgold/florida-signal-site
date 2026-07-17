# Florida Signal

Florida Signal is a source-first development-intelligence site for Fort Lauderdale and Broward County. It turns public permits, parcels, recorded instruments, companies, meetings and official storm information into searchable neighborhood intelligence, live maps, leads, graphics and a daily-brief signup.

## Run locally

```bash
python3 server.py --bind 127.0.0.1 --port 4173
```

Open `http://127.0.0.1:4173/`.

The local server provides same-origin meeting, storm, CMS, agenda-recon and subscriber endpoints. Copy `.env.example` into your private runtime environment and supply credentials there; never commit secrets.

## Operating handoff

- [`FLORIDA_SIGNAL_BUILD_REPORT.md`](FLORIDA_SIGNAL_BUILD_REPORT.md) — source cadence, live versus scheduled updates, date methodology, CMS/Mailchimp state and production runbook.
- [`FLORIDA_SIGNAL_TAGGING_SYSTEM.md`](FLORIDA_SIGNAL_TAGGING_SYSTEM.md) — controlled site and CMS taxonomy.
- [`assets/photos/README.md`](assets/photos/README.md) — licensed Adobe Stock provenance and usage restrictions.

## Data standard

Charts and rankings use the public event date—such as permit `applied_date`, Clerk `recording_date_iso` or a company registration date. Pull, cache and enrichment timestamps describe freshness only; a batch arrival never substitutes for the underlying event date.

The public CMS adapter accepts only sourced, approved or cleared output. Storm Watch cites NOAA/NHC and is not an official warning service.

Powered by Graham & Gold LLC.
