# Florida Signal

Florida Signal is a source-first development-intelligence site for Fort Lauderdale and Broward County. It turns public permits, parcels, recorded instruments, companies, meetings and official storm information into searchable neighborhood intelligence, live maps, leads, graphics and a daily-brief signup.

## Run locally

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

Open the public site at `http://127.0.0.1:4173/` and The Data Wire at `http://127.0.0.1:8788/`.

### Unlock The Data Wire

1. Start `cms/server.py` with `DATA_WIRE_ADMIN_TOKEN` as shown above.
2. Open `http://127.0.0.1:8788/`.
3. Leave the market set to `broward`.
4. Paste the exact same token into **Private desk token** and choose **Open desk**.

The token is kept in that tab's `sessionStorage`; it disappears when the browser session ends. Never place it in public HTML, `app.js`, a screenshot or a committed `.env` file. The CMS starts empty on purpose and only approved, source-linked packets reach the public site.

The local server provides same-origin meeting, storm, CMS, agenda-recon and subscriber endpoints. Copy `.env.example` into your private runtime environment and supply credentials there; never commit secrets.

## Operating handoff

- [`FLORIDA_SIGNAL_BUILD_REPORT.md`](FLORIDA_SIGNAL_BUILD_REPORT.md) — source cadence, live versus scheduled updates, date methodology, CMS/Mailchimp state and production runbook.
- [`FLORIDA_SIGNAL_TAGGING_SYSTEM.md`](FLORIDA_SIGNAL_TAGGING_SYSTEM.md) — controlled site and CMS taxonomy.
- [`cms/README.md`](cms/README.md) — Data Wire endpoints, Story Packet gates and production hardening.
- [`BRAND_KIT.md`](BRAND_KIT.md) and [`brand-kit.html`](brand-kit.html) — brand rules, social masters and newsletter assets.
- [`assets/photos/README.md`](assets/photos/README.md) — licensed Adobe Stock provenance and usage restrictions.

## Data standard

Charts and rankings use the public event date—such as permit `applied_date`, Clerk `recording_date_iso` or a company registration date. Pull, cache and enrichment timestamps describe freshness only; a batch arrival never substitutes for the underlying event date.

The public CMS adapter accepts only sourced, approved or cleared output. Storm Watch cites NOAA/NHC and is not an official warning service.

Powered by Graham & Gold LLC.
