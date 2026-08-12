# Florida Signal — Social Media Asset Guide

Last verified: July 17, 2026

## Brand files

- Primary horizontal logo: `assets/lockup-horizontal-transparent.png`
- Full-color Florida emblem: `assets/mark-full-color.png`
- Square/social emblem: `assets/mark-square.png`
- Reverse and one-color emblems: `assets/mark-white.png` and `assets/mark-navy-mono.png`
- Complete visual rules: `BRAND_KIT.md`
- Licensed photo inventory and required labels: `assets/photos/README.md`

Use the horizontal logo when the words must be readable. Use the full-color emblem as a centered signature/crest inside maps and diagrams. Keep it readable with clear space and the correct full-color or reverse treatment. Never add an arrow, stretch, crop or recolor the emblem, and never use a CTA arrow or the report-builder document icon as branding.

## Channel masters

| Channel | Master | Size |
|---|---|---:|
| LinkedIn / Facebook link post | `brand/templates/linkedin-facebook-1200x627.svg` | 1200 × 627 |
| Instagram square | `brand/templates/instagram-square-1080x1080.svg` | 1080 × 1080 |
| Instagram story / reel cover | `brand/templates/instagram-story-1080x1920.svg` | 1080 × 1920 |
| X landscape | `brand/templates/x-landscape-1600x900.svg` | 1600 × 900 |

Live Data Room PNG exports are in `social/graphic-desk/`. Their city-scoped share pages are in `fort-lauderdale/share/`.

## Regenerate live diagram exports

Run the public site first, then:

```bash
NODE_PATH=/Users/gillfillan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules \
  /Users/gillfillan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  social/export_graphic_desk.cjs http://127.0.0.1:4173
```

Export only after the related source refresh and visual QA pass. Do not publish an old image with a new caption.

## Required content on every data graphic

- Florida Signal logo or centered full-color emblem;
- city/place and controlled topic label;
- exact event-date window or “through” date;
- sample/cap language when applicable;
- concise source/method line;
- canonical Florida Signal URL; and
- enough contrast to read the smallest text on a phone.

The social crop may simplify supporting copy, but it may not remove the date window, cap or source context.

## Caption formula

1. Lead with the useful signal in plain language.
2. Name the city/neighborhood and date window.
3. Say what the number is—and what it is not—when classification or a sample is involved.
4. Link to the underlying map, record, brief or Data Room view.
5. End with one action: investigate, add to Field Brief or join the 6:15 Brief.

Example:

> Fort Lauderdale permit applications rose across the Jul 13–16 filing window, led by Victoria Park in the newest 700 mapped records. This is application activity, not completed construction. Open the neighborhood map: [city-scoped URL]

## Sharing behavior on the site

- Maps use a centered Florida Signal badge and a consistent right-side social rail.
- Data Room graphics provide X, LinkedIn, Facebook, native share, embed and Field Brief actions where appropriate.
- Permit, meeting and neighborhood records can be added to a Field Brief. The document-plus icon is the report builder.
- Promotional carousel cards link to their destination and intentionally omit duplicate share controls.
- Every share URL must be city-scoped and retain the underlying item ID or section anchor.

## Newsletter distribution

The reusable preview/template is at `fort-lauderdale/brand/newsletter/daily-intel-brief.html`. Recommended morning modules are:

1. five top signals;
2. today’s public meetings with verified agenda/stream links;
3. diagram of the day;
4. neighborhood/ZIP movement;
5. Broward record and company movement;
6. Storm Watch only when useful; and
7. a single Field Brief / live map call to action.

Mailchimp is not configured in the current local runtime. Do not claim automatic sync until `/api/health` reports `mailchimp_configured: true` and the city/topic interest fields have been verified end to end.

## Accessibility and rights

- Provide descriptive alt text that states the finding and date window, not “graphic.”
- Do not put essential meaning in color alone.
- Keep body/supporting type at a phone-readable size.
- Adobe Stock images are licensed project assets; preserve the provenance labels in `assets/photos/README.md` and do not redistribute source files as a stock library.
