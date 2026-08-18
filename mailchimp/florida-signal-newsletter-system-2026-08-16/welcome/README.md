# Florida Signal welcome email

This folder is the source of truth for the future-subscriber welcome email designed in Claude and deployed through Mailchimp.

## Contents

- `raw-claude/Welcome Letter.dc.html` — the original Claude Design export, preserved unchanged.
- `florida-signal-welcome-mailchimp.html` — a table-based, responsive Mailchimp build with dark-mode safeguards and required Mailchimp footer merge tags.
- `assets/` — every image referenced by either version of the welcome email.
- `dist/florida-signal-welcome-mailchimp.zip` — the Mailchimp Import ZIP artifact.

## Subscriber experience

The welcome message is intended to send immediately to future signups only. Its **Read the latest Signal** button points to the audience archive index so it continues to surface the newest published issue without editing the automation:

`https://us2.campaign-archive.com/home/?u=224e87bfc7d2cd51e4b2f70a4&id=123540d751`

The social call to action links to the Florida Signal company page—not AJ Gill’s personal profile:

`https://www.linkedin.com/company/floridasignal/`

## Mailchimp settings

- Subject: `Welcome to Florida Signal`
- Preview text: `Record-backed development intelligence for Fort Lauderdale and Broward County—plus the latest Signal.`
- From name: `Florida Signal`
- Reply-to: `desk@thefloridasignal.com`
- Audience: `Florida Signal Subscribers`
- Trigger: joins the audience; future contacts only; send immediately

## Asset manifest

| File | Used for | Repository source |
| --- | --- | --- |
| `assets/fs-lockup-stacked-transparent.png` | Header lockup | `brand/florida-signal-logo-avatar-kit-2026-08-16/logos/fs-lockup-stacked-transparent.png` |
| `assets/emblem-color.png` | Light-background section marks | `mailchimp/florida-signal-newsletter-system-2026-08-16/template/img/emblem-color.png` |
| `assets/emblem-white.png` | Dark-background standards mark | `mailchimp/florida-signal-newsletter-system-2026-08-16/template/img/emblem-white.png` |

The Mailchimp build removes Claude’s `support.js`, custom `<x-dc>`/`<helmet>` elements, flexbox, CSS Grid and absolute positioning. The three database figures are fixed to equal-width, equal-height table cells so their baselines stay aligned across email clients.
