# Claude Design visual audit — August 11, 2026

Status: completed read-only audit. Claude Cowork used the installed Claude Design plugin skills
`design-critique`, `accessibility-review`, and `ux-copy`, plus the connected Chrome extension. It
made 40 read-only Chrome inspection actions and did not edit, publish, export, or schedule anything.
The cleanup brief below was then sent to the existing Claude Design project as a new turn.

## Outcome

The editorial thinking is stronger than the interface. The lead narrative, evidence limits,
unknowns, provenance states, source clocks, proposal-versus-execution distinction, queue funnel and
Human Decision Gate are premium newsroom work. They are currently buried inside a dense monitoring
console: tiny uppercase monospace labels, repeated status clocks, simultaneous rails, too many
objects, undefined jargon, weak progressive disclosure and a phone layout that still behaves like a
compressed desktop.

## Ranked findings

### P0 — fix before handoff

1. The canonical Florida Signal emblem does not render in the masthead or Field mock. Restore the
   exact approved asset; do not draw, crop, recolor or substitute it.
2. Candidate Detail's ownership/permit timeline overlaps its clustered July/August labels. Use
   ordinal spacing, real date labels, a compressed-time marker and staggered captions.
3. Intelligence Lab claims model identities are blind while printing the model names in every card
   footer. Hide identities until the explicit reveal action.
4. Plausible clocks, scores and a pulsing LIVE state can make illustrative content look real. Add a
   persistent global illustrative-data notice and change LIVE to LIVE (example).
5. At roughly 370–490 logical pixels, workstation views overflow horizontally. The masthead clips,
   multi-column text collapses to one word per line, subtitles truncate, display type stays too
   large, the status rail disappears and later nav tabs have no overflow cue.

### P1 — complete in the cleanup pass

6. View navigation preserves the previous scroll position. Reset to the top on every view change.
7. The right rail is repeated/decorative on most views and clips in Data Explorer. Replace it with
   one plain-language status chip and an on-demand panel; keep a useful Refine panel in Explorer.
8. Pipeline clocks surround the one useful alert with noise. Lead with “All sources current except
   FDEP (3 days 4 hours behind)” and disclose raw clocks only on request.
9. Persistent blurred Pro content and a second pinned upsell create visual noise. Reduce to one
   clean contextual upgrade link.
10. Acronyms and specialist terms are not defined: FDEP, FAA, NOC, CRA, P&Z, GIS, CFN, BLD, PRE,
    SLA, folio, lis pendens, encumbrance, quitclaim, as of pull and precision.
11. The S1–S5 model has three competing label systems. Standardize one name per stage everywhere.
12. Record → Candidate → Signal → Story is implied but never shown. Add a compact stage rail to the
    queue and candidate views.
13. Live Desk shows roughly 30 simultaneous data objects. Keep what changed, what matters and what
    needs attention; move detailed freshness and anomalies behind disclosures.
14. Views have too many competing calls to action. Use one filled primary action per view.
15. The newsletter journey is a fragment at the bottom of Live Desk. Create a Brief flow with draft
    → review → schedule → sent; human review remains the primary action.

### P2 — subsequent refinement

16. Typography reads as a terminal. Reserve monospace for identifiers/clocks; use readable sans
    text at 12–13px for labels and 15–16px for body copy.
17. Muted secondary text likely misses contrast requirements and several controls are below 44px.
    Measure contrast in source code and verify keyboard/focus behavior outside the Design sandbox.
18. Several charts are decorative or unexplained. Keep the useful queue funnel/detector yield;
    label or remove sparklines, show real receipt coverage and label graph nodes.
19. Search is syntax-first. Accept plain language, parse it into visible field chips and expose
    Refine on the triage queue.
20. Field is a phone mock inside a desktop canvas, not yet a true mobile product. Preserve the rule
    that irreversible approval, corrections/retractions and sending remain on the workstation.

## Do not lose

- Lead narrative and Impact / Why you care.
- What it does not say and Unknowns with explicit resolution paths.
- Verified / As of pull / Preliminary / Unknown / Stale states, receipts and independent clocks.
- The proposal-versus-execution definition.
- Human Decision Gate wording and behavior.
- Agenda Watch's stage explainer.
- Queue Funnel's honest discard-rate explanation.
- Model cost transparency, without letting model output become evidence.

## Coverage and limits

- Desktop: Live Desk, Agenda Watch, Data Explorer, Triage Queue, Candidate Detail, Intelligence Lab
  and Field inspected end to end at about 1500 × 690 pixels.
- Mobile: conclusive visual checks at about 370 and 490 logical pixels using 200% Design-canvas zoom.
  This exercised responsive CSS but was not real iPhone/Safari device emulation.
- Candidate Detail received the deepest phone review; Intelligence Lab was checked at both narrow
  widths. Field was inspected as the embedded phone mock.
- The hidden Design Notes tab was discovered but not opened.
- The sandboxed cross-origin preview blocked DOM/computed-style, keyboard, focus and screen-reader
  testing. Contrast values are visual estimates until measured in the source.
- Only the free tier, 120-minute service-level setting and blind-Lab-on state were reviewed.
- Interactive state-changing actions were intentionally not exercised.

## Cleanup brief sent to Claude Design

The Design turn was instructed to make the product high-end, boutique, calm and editorial; optimize
for immediate ADHD-friendly orientation; fix the emblem, timeline, blind Lab, illustrative-state
labeling and 390-pixel layout first; collapse the repeated rail; reduce Live Desk density; explain
acronyms; expose the editorial stages; build the Brief journey; improve typography, contrast and
touch targets; label meaningful charts; accept plain-language search; and preserve all evidence,
provenance and human-publication gates. It was explicitly told not to add data sources, metrics,
automation, publishing, exporting or schedules.

The exact prompt remains in the Claude Design project history and in the Claude Cowork audit session
named **Florida Signal Data Wire audit**. This file records the durable requirements without copying
Claude's full multi-page prompt verbatim.

## Cleanup outcome

Claude Design completed the cleanup pass after the audit. The illustrative prototype now has:

- a persistent example-data warning and a non-pulsing `Live (example)` state;
- a reduced Live Desk, on-demand source-status panel and independently reachable Refine controls;
- a rebuilt ownership timeline with ordinal spacing, staggered labels and a narrow stacked form;
- blind model identities, plain-language detector labels and a labelled disagreement scale;
- consistent S1-S5 language, Record → Candidate → Signal → Story rails and a dedicated Brief view;
- larger type and touch targets, simpler action hierarchy, labelled coverage meters and network nodes;
- responsive masthead, view subtitles, one-column narrow layouts and an overflow affordance for the
  seven workspace tabs.

The exact approved emblem is loaded from the repository's public `assets/mark-full-color.png` source.
Claude visually verified the masthead and Field header use the native 791 × 783 ratio with
`object-fit: contain`, visible overflow and no crop, recolor, distortion, clipping or added arrow.
A final narrow-canvas proof at roughly 422 logical pixels showed the responsive masthead and tab
overflow behavior working. This is still a Design prototype; none of its illustrative records,
scores, clocks or interface changes are production data or production code.
