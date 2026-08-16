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

The completed Claude Design refinement was implemented on August 15 rather than shipped as an
isolated mockup. The public page now uses its decision-focused deck, ZIP-enabled signup, simplified
navigation, four-part Signal anatomy, readable coverage proof, mobile Place Lens crop/expand action,
top-of-page “Built by a veteran journalist. AI-assisted; journalist-approved.” credibility line and
Graham & Gold, LLC footer attribution. The
research site remains preserved at `/fort-lauderdale/` but is deliberately not linked from the
launch landing page yet.

On August 16, Claude Design produced the corrected raster brand package directly from the canonical
791 × 783 emblem artwork, then issued a dedicated production-hires correction after the first
lockups proved too small for Retina delivery. The landing-page masthead now uses the v2 tightly
cropped 2510 px horizontal lockup with a 5020 px `srcset` tier; its underline is raised 8.6 px and
the rule-to-tagline gap tightened 3.5 px at the 440 px website size. The footer uses the equivalent
compact pair
without `DEVELOPMENT INTELLIGENCE`; and the existing 32 px and 180 px avatars power the favicon and
Apple touch icon. The old 572 px-equivalent export and the reconstructed HTML/CSS lockup are no
longer loaded by the landing page. The original kit plus the complete 14-file production-hires
package and untouched source ZIP are preserved in
`brand/florida-signal-logo-avatar-kit-2026-08-16/`; the production-hires and production-hires-v2
folders and ZIPs are also on
the Desktop. The emblem geometry is untouched and contains no added arrow. The source emblems in the
new package are byte-for-byte identical to the canonical files. A true SVG was intentionally not
fabricated because the available emblem is raster; `VECTOR_MASTER_BRIEF.md` defines the remaining
SVG/AI production and overlay-acceptance work.

The landing-page evidence strip uses conservative, durable lower bounds from the Aug. 15 aggregate
snapshot: 130K+ permit applications, 200K+ Broward instruments, 2.4M+ permit workflow events and
110K+ mapped applications. It separately names Sunbiz exact matching, FDEP, FAA and meeting watch;
it does not imply that those sources are joined, enriched or current merely because they are indexed.

The product name does not hard-code a cadence. The page states the launch schedule once as
“Delivered Mondays at 7 a.m. ET. More timely alerts as the desk expands,” allowing a later
daily edition without a rebrand. The first phone viewport contains the promise, Broward scope,
email and ZIP fields, primary button and trust lines. The page has exactly two signup forms, one real
desk diagram as product proof and a direct Privacy link. Research, Method and Corrections remain
preserved but are intentionally absent from the focused launch navigation.

Verified locally on August 15:

- 390 × 844 viewport: 390-pixel document width, no horizontal overflow;
- first signup/trust line ends at about 637 pixels;
- no broken images;
- mocked signup posts the established `florida-signal-brief-launch` source;
- `/newsletter/` resolves to `/`;
- `tests/browser/newsletter.spec.js`: six passing checks, including the approved image lockups;
- full Playwright suite: 22 passing checks before the privacy-page assertion was added; and
- `tests.test_server`: five passing API tests.

Production-hires integration was reverified on August 16:

- every one of the 13 PNGs decodes successfully and matches the dimensions in
  `production-hires-v2/EXPORTS.md`;
- all transparent lockups have a genuine alpha channel, all navy lockups are fully opaque and the
  three packaged source emblems match the canonical originals byte for byte;
- actual 5020 px pixels were inspected at 100% and 200%; the approved geometry is unchanged and the
  wordmark, underline and tagline have clean edges;
- 390 × 844 viewport: 390-pixel document width, no broken images, complete 362 × 82 masthead and
  220 × 49 footer lockup, with the first signup/trust line ending at 785 pixels;
- the 2510 px header source provides more than twice the required physical pixels at the measured
  width on a 3× display; and
- `tests/browser/newsletter.spec.js`: six passing checks against the isolated local production
  worktree; the full public browser suite passed 19 checks with five private-desk checks skipped by
  design; and a separate browser gut-check found meaningful content with no error overlay or page
  errors.

## Signup and sending boundary

The form posts to `/api/subscribe`; on the production hostname, `landing.js` uses
`https://api.thefloridasignal.com/api/subscribe`. Both signup points require email and a five-digit
ZIP code so geographic interest is captured from launch. A successful mock returns “You’re in.
Watch for the next brief.”

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
