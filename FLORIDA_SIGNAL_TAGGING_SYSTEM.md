# Florida Signal tagging system

Every publishable object carries machine-readable tags. The visible design uses restrained editorial lines and template changes rather than pill-shaped “AI tags.” This contract is shared by permits, neighborhood briefs, leads, meetings, graphics, social cards and Florida Desk CMS stories.

## Canonical namespaces

| Namespace | Purpose | Examples |
|---|---|---|
| `topic:` | What the item concerns | `development`, `waterfront`, `storm-readiness`, `association-condo`, `demolition`, `roofing`, `corridor-transit` |
| `geography:` | Official named place | `victoria-park`, `downtown-fort-lauderdale`, `33301`, `broward-county` |
| `entity:` | Public-record entity | `developer-name`, `contractor-name`, `association-name` |
| `source:` | Provenance family | `city-permit`, `broward-clerk`, `bcpa`, `sunbiz`, `legistar`, `nhc`, `florida-desk` |
| `audience:` | Useful reader lens | `field-desk`, `broker`, `developer`, `contractor`, `development-intelligence` |
| `urgency:` | Time/attention state | `high-value`, `agenda-posted`, `agenda-watch`, `storm-watch` |
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
  "headline": "Source-grounded headline",
  "summary": "What changed and why it matters",
  "topic_tags": ["development", "corridor-transit"],
  "geography_tags": ["downtown-fort-lauderdale", "broward-county"],
  "entity_tags": ["public-record-entity-slug"],
  "source_tags": ["legistar", "city-permit"],
  "audience_tags": ["developer", "broker"],
  "urgency_tags": ["agenda-posted"],
  "source_links": ["https://official-source.example/document"],
  "review_status": "approved",
  "wire_approved_at": "2026-07-17T10:00:00Z"
}
```

The public adapter normalizes the fields into prefixed tags and returns both a flat `tags` array and grouped `taxonomy` object. City, source links, topic/geography tags and approval gates remain mandatory. The Fort Lauderdale public adapter rejects a packet assigned to any other city.

## Display rule

- Use a small `Filed under`, `Lens`, `Watch` or `Field lens` line.
- Show at most three human-facing tags on a card.
- Keep the complete taxonomy in `data-signal-tags` and the CMS/API object.
- Never display raw confidence, model, agent or processing tags as editorial taxonomy.
- A tag may select a color/template; it may not manufacture a fact, location or urgency state.
