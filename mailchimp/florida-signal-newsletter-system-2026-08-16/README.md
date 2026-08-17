# Florida Signal Mailchimp newsletter system

Archived and production-reviewed on 2026-08-16 from the Claude Design project **Florida Signal Newsletter Build**.

## What is here

- `template/fs-master.html` — reviewed Mailchimp master and component library.
- `template/config-*.html` — example busy, property-led, and quiet-week configurations.
- `template/preview-images-off.html` — image-blocking fallback preview.
- `template/img/` — retina brand and share-button assets used by the templates.
- `raw-claude/` — untouched source files downloaded before production corrections.
- `project-pages/` — Claude Design project pages, including the later social-share revision.
- `previews/` — full-length, detail, strip, mobile, and production-review renderings.
- `pdf/` — portable review copies.
- `dist/` — Mailchimp import packages. Use the filenames containing `colorbar`; the original
  August 16 ZIPs are retained only for provenance.

## Mailchimp build status

- Saved reusable master: **Florida Signal — Modular Master v1** (template ID `11470430`).
- Saved send configuration: **Florida Signal — Busy Week v1** (template ID `11470431`).
- Saved colour-bar master: **Florida Signal — Modular Master v2 Colorbar** (template ID `11470432`).
- Unsent campaign draft: **Florida Signal — Founding Edition** (campaign ID `9304907`), switched to the v2 colour-bar master on 2026-08-16.
- Audience: **Florida Signal Subscribers**; no send or schedule was performed.
- Verified From identity: **Florida Signal** `<desk@thefloridasignal.com>`.
- `thefloridasignal.com` is verified and authenticated in Mailchimp.
- Open, HTML-click, plain-text-click, and Google Analytics link tracking are enabled on the draft.
- Mailchimp's final preview reports **83 KB / 102 KB** and **not at risk of Gmail clipping**.
- The full component-library master measured 113 KB after Mailchimp processing, so it remains a reusable source template and is not the campaign send configuration.

## Production corrections applied

- Uses `Florida Signal` as the sender identity and `desk@thefloridasignal.com` for tips, corrections, and replies.
- Uses Mailchimp-native archive, forward, profile, unsubscribe, and social-share merge tags.
- Includes accessible heading structure, real table headers for tabular records, descriptive image alternatives, dark-mode metadata, and minimum-contrast caption colors.
- Includes UTM hooks on Florida Signal site links while leaving public-record source links untagged.
- Keeps every editorial module bounded by exact `START MODULE` / `END MODULE` comments.
- Adds icon-only LinkedIn, Facebook, and email share controls at the top and bottom with accessible labels and 40px-plus touch targets.
- Uses the official Claude colour-bar masthead, footer lockup and divider emblems at the original pixel dimensions.
- Shows the Graham & Gold, LLC registered office once in the footer: `2222 W Grand River Ave, Suite A, Okemos, MI 48864`.

## Before any live send

1. Duplicate a configuration; never send the component-library master directly.
2. Remove unused modules and the entire component-library block.
3. Replace every bracketed placeholder, `[CAMPAIGN_SLUG]`, subject, and preheader.
4. Confirm the Mailchimp From name is `Florida Signal`, the From and reply-to address is `desk@thefloridasignal.com`, and open/click tracking is enabled.
5. Confirm that Mailchimp account/audience settings also use `2222 W Grand River Ave, Suite A, Okemos, MI 48864`; do not add a second address line to the template.
6. Reconfirm Mailchimp still shows `thefloridasignal.com` as authenticated before the first live send.
7. Send seeds to Gmail web/mobile, Apple Mail on iPhone, and Outlook; check images-off, dark mode, links, merge tags, and 390px width.

No campaign in this archive is authorized for sending.
