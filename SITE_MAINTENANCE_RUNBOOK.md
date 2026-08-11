# Florida Signal site maintenance runbook

This runbook owns the public site's code and presentation. It does not replace source collectors, enrichment jobs or human editorial review.

## Automated checks

`.github/workflows/site-health.yml` runs:

- on every pull request;
- after changes land on `main`;
- manually; and
- hourly against `https://thefloridasignal.com`.

The browser suite verifies that:

- non-map pages initialize without Leaflet;
- Briefs exits its connecting state and reports the real editorial-wire condition;
- Method and Broward Record replace placeholder freshness text;
- the headline permit total comes from an exact snapshot; and
- a planner estimate is visibly marked `≈` and labeled before citation;
- the production API hostname answers `/api/health` during scheduled/manual monitoring;
- Mailchimp remains configured, the private CMS remains explicitly closed, data health returns
  source clocks without internal errors and the public meetings feed is non-empty; and
- data health contains both the `broward` verified SFTP clock and the `clerk-preliminary`
  AcclaimWeb clock with their evidence labels intact.

On a failed scheduled/manual production run, the workflow opens or updates one GitHub issue and uploads the Playwright report, trace and screenshots for 14 days.

## Local release check

```sh
npm ci
npm test
```

`npm test` runs the signal/publication-safety suite, Python API tests and browser checks against an isolated local server on port 4183. It must not reuse a developer preview on port 4173.

To test the deployed site explicitly:

```sh
SITE_BASE_URL=https://thefloridasignal.com npm run test:browser
```

## Incident response

1. Confirm whether the failure is static hosting, JavaScript, API/DNS, or upstream data.
2. Preserve the failing workflow URL, screenshot, trace, response status and source timestamps.
3. Do not change data merely to make a check green.
4. For a frontend regression, reproduce locally, add or tighten a browser assertion, then repair through a pull request.
5. For API/DNS failure, verify DNS, TLS, `/api/health`, service state and API logs before touching the client.
6. For stale data, identify the owning schedule and last successful source event span. Never substitute page-render time.
7. For conflicting or missing source fields, quarantine the affected output and retain raw text/provenance.
8. Close the incident only after the production monitor passes and the underlying clock/count is independently checked.

API host checks:

```sh
dig +short @ns39.domaincontrol.com api.thefloridasignal.com A
curl -fsS https://api.thefloridasignal.com/api/health
curl -fsS https://api.thefloridasignal.com/api/data-health
ssh florida 'systemctl show florida-signal-public.service -p ActiveState,SubState,Result,ExecMainStatus'
ssh florida 'sudo nginx -t; systemctl is-active certbot.timer'
```

`/api/health` proves that the boundary is reachable; it does not prove that every source is fresh.
Read each event/system clock in `/api/data-health`. A 502 from `/api/storms` currently means the
official NHC origin blocked the server host; the client must show a source-check state and an
official link, never infer “no storm” from that transport failure.

For Broward Clerk data, read the two cards independently. `current + preliminary` means the early
AcclaimWeb lane is operating; it does not extend the verified SFTP coverage date. `delayed +
verified` can mean the collector checked successfully but the Clerk has not released a newer
authoritative file. Confirm `system_time`, `event_through`, `verification` and the source run before
declaring a failure.

## Ownership boundaries

| Layer | Owner / mechanism | Automatic publication allowed? |
|---|---|---|
| Static site | GitHub Pages from `main` | Code deploy only after tests/review. |
| Public API | Always-on service behind `api.thefloridasignal.com` | Responses only; no narrative publication. |
| Source collection/enrichment | Pipeline repository and verified server/database schedules | Records may flow under source rules; conflicts stay quarantined. |
| Public briefs | Data Wire plus named human editor | No. Human approval required. |
| Site monitor | GitHub Actions | May report incidents; may not edit source data or merge its own repair. |

Static code deploys from `main` through GitHub Pages. The Python API runs from a clean production
checkout on the droplet and must be updated with the fast-forward/test/restart sequence in
`ops/droplet/README_PUBLIC_API.md`. There is no autonomous AI agent with merge or editorial authority.

## Stop-the-line failures

- A capped sample or planner estimate appears as an exact total.
- A source says current without a defensible event/system clock.
- Preliminary Clerk rows appear without a visible `PRELIMINARY` evidence label or are combined into the verified total.
- A non-map page crashes because a map library is absent.
- Briefs or CMS substitutes draft/older content after an adapter failure.
- Signup reports success without durable server-side acceptance.
- A map location cannot be tied to cited coordinates or official geography.
- Automation attempts a duplicate writer or overwrites raw source evidence.
