# Florida Signal welcome email

This folder is the source of truth for the future-subscriber welcome email designed in Claude and deployed through Mailchimp.

## Contents

- `raw-claude/Welcome Letter.dc.html` — the original Claude Design export, preserved unchanged.
- `florida-signal-welcome-mailchimp.html` — a table-based, responsive Mailchimp build with dark-mode safeguards and required Mailchimp footer merge tags.
- `assets/` — every image referenced by either version of the welcome email.
- `dist/florida-signal-welcome-mailchimp.zip` — the Mailchimp Import ZIP artifact.

## Subscriber experience

The active Mailchimp automation flow sends two messages to future signups, in this order:

1. **Welcome to Florida Signal** — sends immediately.
2. **Latest Signal — Aug. 18, 2026** — sends the complete latest newsletter immediately after the welcome message.

The welcome message's **Read the latest Signal** button also points to the audience archive index:

`https://us2.campaign-archive.com/home/?u=224e87bfc7d2cd51e4b2f70a4&id=123540d751`

The social call to action links to the Florida Signal company page—not AJ Gill’s personal profile:

`https://www.linkedin.com/company/floridasignal/`

## Mailchimp settings

- Journey ID: `5649`
- Journey name: `Welcome Email — Florida Signal Subscribers`
- Re-entry: disabled; existing subscribers are not enrolled again
- Welcome campaign ID / web ID: `6475ab5d47` / `9304933`
- Welcome subject: `Welcome to Florida Signal`
- Welcome preview text: `Record-backed development intelligence for Fort Lauderdale and Broward County—plus the latest Signal.`
- Latest-issue campaign ID / web ID: `e6041f197c` / `9304936`
- Latest-issue subject: `Your Broward intelligence: $2.9M in votes + Zara filings`
- From name: `Florida Signal`
- Reply-to: `desk@thefloridasignal.com`
- Audience: `Florida Signal Subscribers`
- Trigger: joins the audience; future contacts only

## Latest-issue maintenance

The second email is a full HTML copy of the newest issue; it is not dynamically replaced by Mailchimp. After each newsletter is finalized and sent:

1. Pause the journey.
2. Open the second **Send email** step.
3. Replace its title, subject, preview text and custom-code HTML with the new edition.
4. Verify hosted images, required Mailchimp merge tags and the inbox preview.
5. Turn the journey back on and confirm both email steps are active.

Do not enable journey re-entry. That would resend the welcome sequence to existing contacts.

## Asset manifest

| File | Used for | Repository source |
| --- | --- | --- |
| `assets/fs-lockup-stacked-transparent.png` | Header lockup | `brand/florida-signal-logo-avatar-kit-2026-08-16/logos/fs-lockup-stacked-transparent.png` |
| `assets/emblem-color.png` | Light-background section marks | `mailchimp/florida-signal-newsletter-system-2026-08-16/template/img/emblem-color.png` |
| `assets/emblem-white.png` | Dark-background standards mark | `mailchimp/florida-signal-newsletter-system-2026-08-16/template/img/emblem-white.png` |

The Mailchimp build removes Claude’s `support.js`, custom `<x-dc>`/`<helmet>` elements, flexbox, CSS Grid and absolute positioning. The three database figures are fixed to equal-width, equal-height table cells so their baselines stay aligned across email clients.
