# Florida Signal — AI Handoff

Last verified: July 17, 2026

## Product contract

Florida Signal is Broward-wide, source-first development intelligence launching city by city. Fort Lauderdale is the first live desk. The product turns public records into useful, place-specific signals without overstating coverage, inventing interpretation or hiding the source window.

The public site is not a raw database dump and The Data Wire is not an autonomous publisher. Automated systems can collect, normalize, classify, geocode and draft. A human editor clears consequential narrative claims and every public brief must retain its cited source.

## Read these first

1. `README.md` — local start, CMS access and operating links.
2. `LIVE_DATA_OPERATIONS_HANDOFF.md` — sources, schedules, exact stat definitions and recovery steps.
3. `FLORIDA_SIGNAL_TAGGING_SYSTEM.md` — required city, county, neighborhood and topic fields.
4. `cms/README.md` — Data Wire schema, source gates and API contract.
5. `BRAND_KIT.md` and `SOCIAL_MEDIA_ASSET_GUIDE.md` — public visual and distribution rules.
6. `FLORIDA_SIGNAL_BUILD_REPORT.md` — implementation inventory and launch blockers.

## Non-negotiable data rules

- Use the underlying public event date for analysis: permit `applied_date`, instrument `recording_date_iso`, company application/registration date or scheduled meeting time.
- Pull, mirror, enrichment and publish times are freshness metadata only. A batch arrival never becomes the event date.
- Preserve the exact observed start and end date on every chart, map, ranking and share image.
- State sample caps. The newest 700 geocoded permits and a first-40 query are samples, not municipal totals.
- Do not call a source live/current when its public event span or source-health clock is absent or stale.
- Do not infer completed construction, storm damage, demand, ownership, contractor solicitation or causation from an application alone.
- Do not invent a neighborhood. Resolve it from the official City polygon; keep ZIP, corridor, municipality and county as separate fields.
- Every story/brief requires `city`; the current live value is `fort-lauderdale`. Public content URLs must stay under a city path.
- No source, no claim. Missing or uncertain facts are omitted, not filled with plausible text.

## Content object minimum

Every public content object should carry, even when not all fields are displayed:

- stable ID and canonical city-scoped URL;
- `city`, `county`, neighborhood/place and ZIP when resolved;
- content type and controlled topic tags;
- source name and direct public source URL;
- event date or event-date span;
- observed/system timestamp kept separately;
- coverage/sample note;
- verification status and editor state; and
- correction/history metadata after publication.

## System map

```text
Public sources
  -> collectors / public mirror
  -> normalized local datasets and Supabase-backed views
  -> enrichment (address, parcel, company, neighborhood, topic)
  -> source-health and editorial gates
  -> The Data Wire draft / approval queue
  -> city-scoped public site, maps, Data Room and share assets
  -> newsletter/social distribution with the same source window
```

The public site runs from `server.py` on port 4173. The private Data Wire runs from `cms/server.py` on port 8788. The Data Wire token belongs only in server environment/session storage. Never commit it or place it in public JavaScript.

## Data Room contract

The Data Room is investigation-first, not a gallery. Its order is:

1. live mapped filings and heat-density toggle;
2. **Now** — application pulse and work mix;
3. **Places** — neighborhoods, ZIPs, value and operator activity;
4. **Property** — Broward records, values and entity trails;
5. **Watch** — storm-relevant filings and meetings.

Every diagram has a visible date window, a direct destination to the underlying surface, Florida Signal branding, share/embed controls where appropriate and a Field Brief add action. The centered full-color emblem is branding; the document-plus icon is the report builder. Do not interchange them.

## Storm Watch contract

Storm Watch uses official NOAA/NHC material for weather context and clearly says Florida Signal is not an official warning service. Local permit classifications show recorded preparation/recovery-type applications; they do not prove storm damage, completed work or a forecast. When no named storm is active, the status is standby. Publisher-controlled activation can change the visual system and prominence, but it cannot change data definitions.

## Multi-city expansion

- One code pattern powers all cities; do not fork separate page logic.
- Fort Lauderdale is the only live desk in the public build.
- Other Broward municipalities use the shared coming-soon state with no dates or coverage promises.
- The CMS may prepare future markets, but Miami-Dade, Palm Beaches, Tampa Bay and Southwest Florida must not be promoted on the current public site.
- City selection is required on briefs and subscriber interests; Fort Lauderdale is preselected for the current desk.

## Safe implementation checklist

Before publishing any AI-assisted change:

- validate JavaScript, Python, JSON, SVG and local links;
- compare displayed values with their endpoint/dataset and retain zero days;
- confirm the event span and cap are visible;
- test desktop and a 390-pixel mobile viewport for overflow and readable contrast;
- test map popups, Street View/satellite links, share/embed and Field Brief actions;
- verify sponsor treatment cannot be confused with editorial content;
- confirm no private token, subscriber record or source credential entered the public bundle; and
- regenerate affected social exports only after the data refresh passes.

## Current production caveats

As of the verification date, the local health endpoint reports that CMS and Mailchimp production integrations are not configured. Some aggregate and Broward clocks are stale and Sunbiz does not expose enough source-health metadata to claim live status. See `LIVE_DATA_OPERATIONS_HANDOFF.md` for the exact snapshot and remediation sequence.

