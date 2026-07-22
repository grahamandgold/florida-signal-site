# Florida Signal product correction and launch truth

**Verified:** July 22, 2026 ET

**Scope:** public-site branch `codex/methodology-mobile-stories`

**DNS/GoDaddy:** intentionally untouched

This is the current product and operating handoff. It supersedes older public-site copy or notes that describe a single “next pull” clock, imply that Agenda Recon is already populated, call a sequence of records causal, or present the 700-row map sample as a complete universe.

## Product north star

Florida Signal is a neighborhood-first research and lead-discovery product. Every useful surface must answer:

1. **What changed?** Name the exact application, instrument, agenda item, meeting or official-source update.
2. **Where?** Lead with the official neighborhood, then retain ZIP, city and county metadata.
3. **Who should care?** Identify the useful persona without claiming demand or intent.
4. **Why does it matter?** Explain the investigation or decision the record should prompt.
5. **What can the reader do?** Open the cited record, focused map, official packet or Field Report.

Automation finds and organizes candidates. A record is not a conclusion, and automated extraction is not an autonomous publisher.

## What is working now

- Public permit records load from Supabase and use `applied_date` as the event clock.
- The newest mapped permit sample is capped at 700 rows for phone performance and visibly names its returned date span and limitation.
- The multi-source Signals layer reloads bounded data by map view and supports source, verification, time-window, amount and work-type filters.
- Permit descriptions receive deterministic plain-English headlines while the exact official scope remains visible.
- Map cards fit a 390px phone, expose 46px actions, and preserve source links.
- Each map now has a contextual key: permit applications, meeting rooms or agenda parcels. Room pins explicitly say they are not project parcels.
- Meeting rows load automatically, show city/county, identify agenda-posted versus source-watch state, and retain official links.
- Data Room diagrams recompute from current returned data, show source/date windows, identify useful personas, explain impact and deep-link to the corresponding filtered map.
- The signup requires only email and ZIP. Interest preferences are optional and default to Fort Lauderdale/all topics.
- The Field Report acts as the report “cart”: permits, signals, diagrams, meetings, agenda parcels and stories can be collected, opened, removed, copied, shared or printed.
- The CMS already has source, claim, editor, taxonomy and publication gates. Story publication now requires a primary official neighborhood.

## Mobile Field Edition

Mobile no longer leads with an auto-flipping promotional signal rail. It opens with **Explore around you now** and provides:

- persona lenses for developer, broker/agent, contractor, neighborhood leader and owner/association;
- Around Me browser-only location search;
- neighborhood, meeting, property, contractor, resilience, demolition and work-type tools;
- live counts from the current mapped sample; and
- a persona Lead Generator that ranks three current research candidates, explains the bounded reason for the ranking, opens the exact filing and adds it to a Field Report.

Lead rankings are research triage. They are not contracts, approvals, solicitations, owner intent, demand forecasts or recommendations.

## Desktop Analyst Workspace

Desktop retains the wider comparison, methodology, record-join, map and Data Room experience. Both device modes name the difference: mobile is field-first and location-aware; desktop is analysis-first and comparison-oriented. They use the same source records and taxonomy.

## Shared taxonomy

The canonical hierarchy is:

`market` → `county` → `city` → `neighborhood` → `zip`

Other namespaces include `topic`, `persona`, `source`, `record-stage`, `urgency`, `entity`, `asset`, `qualification`, `format` and `location-status`. See `FLORIDA_SIGNAL_TAGGING_SYSTEM.md`.

Neighborhood is the visible place unit. County and city are routing parents. The system must display “Neighborhood not yet resolved” rather than infer a neighborhood from ZIP, mailing city or nearby landmark.

## Agenda Parcel Tracker: interface ready, ingestion not connected

The public tracker and CMS contract can carry:

- meeting and item number;
- cited packet page/source hash;
- proposed action;
- address, folio, coordinates, official neighborhood and ZIP;
- tracker lifecycle;
- cited packet clues;
- official attachment/rendering URLs;
- an official outcome and outcome source, only when posted; and
- focused parcel-map and Field Report actions.

The public interface is intentionally empty today because the upstream agenda collector-to-clearance boundary is not connected. Current observed state: 20 meeting rooms watched, zero future packets reported by the public endpoint, zero cleared agenda properties and zero public hot topics. Existing engine monitoring evidence from the private system is not the same as a populated public feed. Do not describe Agenda Recon as live until packets and cleared items reach `/api/agenda-recon`.

## Feed schedule and automation truth

The header rotates the next scheduled source operation rather than showing one misleading global countdown:

| Feed/process | Schedule shown by the public product | Meaning |
|---|---|---|
| Meeting calendar display | every 15 minutes | Dates and official links; not item extraction |
| Permit public mirror | every 30 minutes | Mirror freshness; not a new event date |
| Agenda source watch | 6:30 a.m., 12:30 p.m., 4:30 p.m. ET | Packet monitor; no topic without evidence clearance |
| Clerk records | 9:30 a.m. ET | Broward recorded-document source cycle |
| Permit source intake | 10:00 p.m. ET | City application intake |
| Business filings | 11:30 p.m. ET | Division of Corporations enrichment |
| Freshness audit | 7:00 a.m. and 5:00 p.m. ET | Independent clocks checked |

NHC current-storm data refreshes separately. Event dates, source publication dates, successful pull times, mirror times and enrichment times remain distinct.

## Legal and methodology guardrails

- Permit application ≠ issuance, approval, inspection, construction or completion.
- Recorded instrument ≠ beneficial ownership, motive, arm’s-length transaction, development intent or causal trigger.
- Shared parcel/address/name ≠ affiliation, control, responsibility or causation.
- Declared permit value ≠ audited cost, financing, market value or economic impact.
- Agenda posting ≠ recommendation, vote, approval, outcome or final design.
- Proposal renderings ≠ approved or final renderings.
- Sequence between a land record and later permit is chronology only unless additional cited evidence supports a relationship.

The public product is a research resource, not legal, title, appraisal, engineering or investment advice. An independent Florida land-use attorney should review launch copy and disclaimers before a paid/public expansion.

## Known launch blockers

1. Connect the agenda packet collector, item extraction, parcel resolver and human clearance output to the public `/api/agenda-recon` path.
2. Configure the deployed CMS URL and populate/test the first neighborhood-tagged approved story. The local tables currently contain no public story.
3. Configure and verify the production email provider sync. Current server configuration does not expose the Mailchimp key; local subscriber storage is not the finished delivery system.
4. Keep `api.thefloridasignal.com`/GoDaddy untouched until the product, data and mobile gates pass and the owner explicitly authorizes DNS work.
5. Run the launch-day external-source/link check from the deployed environment; bot protections can make a local automated result inconclusive.

## Verification completed in this branch

- `node --check app.js`
- `node --check signals.js`
- `python3 -m py_compile server.py cms/server.py`
- `node --test tests/signals.test.js` — 88 passed
- `python3 -m unittest discover -s tests -p 'test_*.py'` — 6 passed
- static internal crawl — 365 references / 74 unique local URLs; no broken public-site HTTP route
- dynamic desktop route crawl — 25 routes/query states, no horizontal overflow; one non-map Leaflet initialization defect found and fixed
- mobile 390×844 browser checks — no horizontal overflow; 13 toolkit actions; three persona leads; Field Report add/open; exact permit popup with five actions contained inside the viewport
- Data Room — 10 cards, 10 persona labels, 10 impact blocks and 10 deep links
- Meetings — 20 jurisdiction labels; distinct meeting-room and agenda-parcel keys; truthful empty Agenda Recon state

## Deferred, not forgotten

- A richer story editor/CMS experience remains secondary to data integrity, agenda ingestion and mobile field utility.
- Static share images should be re-exported only after a verified data refresh. Live pages must never present a static image as a live count.
- Expand city by city only after neighborhood resolution, source authority, schedules and story taxonomy are explicit for the new desk.
