# Florida Signal responsive logo handoff

This directory preserves the Claude Design refinement approved on August 15, 2026 and the production implementation derived from it.

## Source

- Claude Design project: `Logo redesign prototypes`
- Selected direction: **3c**, expanded into the **4-series** usage set
- Reference URL at handoff: `https://claude.ai/design/p/681bde22-8453-4401-ba05-29998127e73f?file=design_handoff_logo_lockup%2Flockup-reference.html`

Claude's reference supplied hero, header, reverse, cream, stacked, compact and mark-only states. Its core idea is one scalable component: changing `--fs-logo-size` adjusts the emblem, gaps, rule, wordmark and justified tagline together.

## Production decision

`logo-lockup.css` implements the selected proportions. It intentionally replaces Claude's screenshot-derived symbol PNG with the canonical repository artwork:

- light surfaces: `/assets/mark-full-color.png`
- dark surfaces: `/assets/mark-white.png`

Never substitute `assets/emblem-2026.png`, add an arrow, redraw the Florida silhouette or merge the mark with a control.

## Usage

```html
<a class="fs-lockup fs-lockup--header" href="/" aria-label="Florida Signal — Development Intelligence home">
  <img class="fs-lockup__mark" src="/assets/mark-full-color.png" alt="">
  <span class="fs-lockup__words" aria-hidden="true">
    <span class="fs-lockup__name"><span>Florida</span> <i>Signal</i></span>
    <span class="fs-lockup__rule"></span>
    <span class="fs-lockup__tagline" aria-label="Development Intelligence"><!-- one span per letter --></span>
  </span>
</a>
```

The production markup contains one span per tagline letter so the line exactly justifies to the wordmark width without brittle hand-tuned tracking.

## Size rules

- Hero/reference: `--fs-logo-size: 58px`
- Desktop header: up to `40px`
- Compact/mobile: `23–28px`
- Footer: `21–24px`
- Below 335 CSS pixels, hide the hairline/tagline rather than render unreadable microtype
- Below the compact wordmark threshold, use `.fs-lockup--mark-only`

Available modifiers: `.fs-lockup--reverse`, `.fs-lockup--stacked`, `.fs-lockup--mark-only`.
