# Florida Signal Brief launch handoff · August 15, 2026

## Decision

Florida Signal is launching newsletter-first.

- Root `/` is the signup-first public home for the **Florida Signal Brief**.
- The complete research site remains at `/fort-lauderdale/` and rolls out gradually.
- `/newsletter/` redirects to `/` so earlier links keep working.
- Nothing in the research site was deleted or replaced.
- No newsletter may be sent without explicit human approval of the final immutable edition.

## Recovery point

The pre-switch site is preserved in the remote repository at the annotated tag
`full-site-v1-pre-newsletter-root-2026-08-15` (commit `bc8c62e`). Detailed recovery commands are in
`archive/full-site-v1-2026-08-15/README.md`.

## Landing-page contract

The landing page is mobile-first, uses the approved Florida Signal emblem, and keeps
`DEVELOPMENT INTELLIGENCE` on one uninterrupted line. It uses Atlantic navy, electric blue, aqua
and white; there is no tan field, decorative arrow-emblem or automatic modal.

On August 15, the root masthead, Privacy masthead and landing-page footer adopted the Claude Design
3c/4-series responsive lockup: a stronger tagline justified to the full wordmark width, a controlled
hairline and documented horizontal/reverse/stacked/compact states. The reusable source and visual
reference are preserved in `brand/logo-lockup-2026/`. Production always loads the canonical
`assets/mark-full-color.png`; the screenshot-derived prototype symbol is not shipped.

The product name does not hard-code a cadence. The page states the launch schedule separately as
“Free every Monday morning to start,” allowing a later daily edition without a rebrand. The first
phone viewport contains the promise, Broward scope, email field, primary button and trust line. The
page has exactly two signup forms, one real desk diagram as product proof, a direct Method link, a
Privacy page and a deliberately secondary link to the research site.

Verified locally on August 15:

- 390 × 844 viewport: 390-pixel document width, no horizontal overflow;
- first signup/trust line ends at 576 pixels;
- no broken images;
- mocked signup posts the established `florida-signal-brief-launch` source;
- `/newsletter/` resolves to `/`;
- `tests/browser/newsletter.spec.js`: five passing checks;
- full Playwright suite: 22 passing checks before the privacy-page assertion was added; and
- `tests.test_server`: five passing API tests.

## Signup and sending boundary

The form posts to `/api/subscribe`; on the production hostname, `landing.js` uses
`https://api.thefloridasignal.com/api/subscribe`. The page collects email first and does not require
a ZIP code. A successful mock returns “You’re in. Watch for Monday’s brief.”

Mailchimp remains a downstream delivery service. A working landing page does not authorize a
campaign send. Test-device review, final subject/preview text, all source receipts and the human
send approval remain separate gates.

## First edition

The active worksheet is `newsletter/editions/2026-08-17-working-draft.md`.

At the August 15 check, the private desk contained 175 new Candidates: 25 evidence-ready and 150
blocked. None was approved and the Brief Bank was empty. Meeting Watch reported 20 upcoming rooms;
Agenda Watch narrowed that to eight watched upcoming meetings, including four Fort Lauderdale
public bodies on Tuesday, Aug. 18. Permit applications and preliminary Broward recordings were
current through Aug. 14; the authoritative verified Broward feed was delayed at Aug. 11.

Those facts support a small, transparent founding issue. They do not support calling every record a
Signal. If no Lead Signal clears direct-source review, publish a short **What we checked** module
rather than padding the edition.

## Next editorial actions

1. Open and report the Aug. 18 official agendas and their decisive attachments.
2. Choose one lead only after What changed / Why it matters / Proof / Unknown / Next is complete.
3. Move approved modules into the Brief Bank for Monday, Aug. 17.
4. Build the Mailchimp test artifact and inspect phone, desktop, dark mode and Outlook rendering.
5. Approve subject, preview, edition body, links and send time as one human gate.
6. Send only after that approval; then publish one LinkedIn launch post and measure signups.
