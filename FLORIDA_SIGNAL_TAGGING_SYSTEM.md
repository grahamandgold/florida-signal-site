# Florida Signal tagging system

Every publishable object carries machine-readable tags. The visible design uses restrained editorial lines and template changes rather than pill-shaped “AI tags.” This contract is shared by permits, neighborhood briefs, persona leads, agenda parcels, meetings, graphics, social cards, Field Reports and Florida Desk CMS stories.

## Place hierarchy: neighborhood first

The reader-facing place unit is the **official neighborhood**. County and city are routing parents; ZIP and corridors are additional lookup lenses. The stable hierarchy is:

`market:broward` → `county:broward-county` → `city:fort-lauderdale` → `neighborhood:victoria-park` → `zip:33301`

- A story cannot clear the public wire without a primary official neighborhood.
- A parcel or permit uses the City polygon resolver for its neighborhood; the desk does not infer one from a ZIP, mailing city, batch name or nearby landmark.
- When a record has defensible coordinates but the neighborhood layer has not resolved it, use `location-status:neighborhood-unresolved` and display “Neighborhood not yet resolved.”
- Multi-neighborhood and citywide analyses retain the same tags on each underlying item. They must not create a fictional neighborhood named “citywide.”

## Canonical namespaces

| Namespace | Purpose | Examples |
|---|---|---|
| `market:` | Expansion market | `broward` |
| `county:` | County routing parent | `broward-county` |
| `city:` | Municipal routing parent | `fort-lauderdale` |
| `neighborhood:` | Official hyperlocal place | `victoria-park`, `flagler-village` |
| `zip:` | Postal lookup lens | `33301`, `33304` |
| `topic:` | What the item concerns | `development`, `waterfront`, `storm-readiness`, `association-condo`, `demolition`, `roofing`, `corridor-transit` |
| `geography:` | Additional place or corridor lens | `las-olas-corridor`, `waterfront`, `central-business-district` |
| `entity:` | Public-record entity | `developer-name`, `contractor-name`, `association-name` |
| `source:` | Provenance family | `city-permit`, `broward-clerk`, `bcpa`, `sunbiz`, `legistar`, `nhc`, `florida-desk` |
| `persona:` | Useful reader/lead lens | `field-desk`, `broker-agent`, `developer`, `contractor`, `neighborhood-leader`, `owner-association`, `land-use-team` |
| `urgency:` | Time/attention state | `high-value`, `agenda-posted`, `agenda-watch`, `storm-watch` |
| `record-stage:` | What the public record actually shows | `application-filed`, `agenda-posted`, `parcel-resolved`, `minutes-posted` |
| `location-status:` | Resolution state | `neighborhood-unresolved`, `parcel-conflict` |
| `asset:` | Property/use context | `commercial`, `residential`, `condo`, `industrial`, `mixed-use` |
| `qualification:` | Lead qualification state | `operator-unlisted`, `new`, `high`, `storm`, `association` |
| `format:` | Presentation/output | `story`, `record`, `lead-card`, `neighborhood-brief`, `meeting`, `graphic`, `search-result`, `spotlight` |
| `template:` | Visual variant | `waterfront`, `storm`, `association`, `corridor`, `high-value`, `development` |

Tags use lowercase kebab-case. Geography must use the same official neighborhood name that the City polygon resolver returns. Do not invent a neighborhood from a ZIP, mailing city, batch name or nearby landmark.

## Neighborhood template rules

Neighborhood cards share one base component and use a tagged visual variant:

- `template:association` when a mapped public record contains defensible association/condo language;
- `template:waterfront` when mapped records include seawall, dock or marine work;
- `template:storm` when the current sample contains at least three storm-readiness records;
- `template:corridor` for named corridor/transit geographies such as Downtown or Flagler Village;
- `template:high-value` when the current records include the disclosed high-value threshold; and
- `template:development` as the sourced general-activity fallback.

The map shape is the official neighborhood polygon and its dots are actual mapped records in the displayed sample. Template styling never creates or changes data.

## CMS story contract

A CMS brief must provide a city plus the editorial dimensions explicitly. `city` is a required routing and publication field, not an inferred geography tag:

```json
{
  "city": "fort-lauderdale",
  "county": "broward-county",
  "neighborhood": "Flagler Village",
  "zip": "33301",
  "headline": "Source-grounded headline",
  "summary": "What changed and why it matters",
  "topic_tags": ["development", "corridor-transit"],
  "geography_tags": ["central-business-district", "brightline-corridor"],
  "entity_tags": ["public-record-entity-slug"],
  "source_tags": ["legistar", "city-permit"],
  "audience_tags": ["developer", "broker-agent", "neighborhood-leader"],
  "urgency_tags": ["agenda-posted"],
  "source_links": ["https://official-source.example/document"],
  "review_status": "approved",
  "wire_approved_at": "2026-07-17T10:00:00Z"
}
```

`audience_tags` remains the storage field for backward compatibility; public metadata emits the canonical `persona:` namespace. The public adapter normalizes fields into prefixed tags and returns both a flat `tags` array and grouped `taxonomy` object. County, city, primary neighborhood, source links, topic/place tags and approval gates remain mandatory. The Fort Lauderdale adapter rejects packets assigned to another city or missing a primary neighborhood.

## Agenda parcel tracker contract

An agenda tracker item uses the same place hierarchy and adds `item_number`, `folio`, coordinates, proposed action, packet page, lifecycle state, packet clues, attachment links, official renderings and—only when cited—an official outcome. “Agenda posted” is never treated as “approved.” Renderings are labeled proposal-packet images and do not prove final design, approval, financing, construction or timing.

## Display rule

- Use a small `Filed under`, `Lens`, `Watch` or `Field lens` line.
- Show at most three human-facing tags on a card.
- Keep the complete taxonomy in `data-signal-tags` and the CMS/API object.
- Never display raw confidence, model, agent or processing tags as editorial taxonomy.
- A tag may select a color/template; it may not manufacture a fact, location or urgency state.
