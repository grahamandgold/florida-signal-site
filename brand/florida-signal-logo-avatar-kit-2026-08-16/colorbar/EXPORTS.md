# Florida Signal — colour-bar mark · canonical package

Brand name is **Florida Signal** (never "The Florida Signal"). Personal profile is **AJ Gill**.

The blue/teal tower bars are now the official mark treatment across every active application.

---

## Method — read this first

There is **no vector wordmark anywhere in this project**. The share-card SVG you supplied is a composition file: it references the logo as a raster `<image>`, not as paths. So the only way to honour "do not retype, respace or redraw" was:

> **Colour substitution on the existing artwork's own pixel grid.**

For every asset the emblem's bounding box was measured in the source file, cleared, and refilled with the same emblem in official colours at exactly the same rectangle. Verification that this preserved geometry:

- The colour and reverse emblems share an **identical ink box** — `20,20 → 751×743`. Same pixels, different palette.
- Every emblem slot detected across 13 lockups matched the emblem aspect of **1.0102** (measured range 1.0085–1.0203).
- Every insertion is a **downscale** from the 751px source. Nothing was upscaled or invented.

No silhouette was redrawn. No wordmark was retyped. No spacing changed. No arrow was added.

## Canonical palette

Read directly off the approved emblem — exactly three opaque values.

| Hex | Role |
|---|---|
| `#052a54` | Florida body (light backgrounds) |
| `#0175b7` | Blue tower |
| `#0aac9a` | Teal tower |
| `#FFFFFF` | Florida body (reverse) |
| `#071B2E` | Atlantic navy field |

Separator strokes are fully transparent in the source and stay transparent, so the field colour shows through on any background.

---

## Package contents

**`/lockups`** — working lockups. Light cuts (`-light-`) were already compliant and are byte-for-byte copies. Reverse cuts (`-colorbar-`) are new.

**`/masters`** — 2×/4× high-resolution. Light masters at 2510/5020/2892 copied unchanged; navy colour-bar masters generated at the same sizes.

**`/emblem`** — symbol only, both polarities, at 32 / 180 / 192 / 256 / 400 / 512 / 1024.

**`/avatars`** — square tiles, white and navy fields, same seven sizes.

**`/icons`** — `favicon-32`, `apple-touch-icon-180`, `icon-192`, `icon-512`, plus navy variants.

**`/applications`** — exact-size finals for every live surface.

**`/social`** — post masters: LinkedIn/Facebook 1200×627, Instagram square 1080, Instagram Story 1080×1920, X 1600×900. Editorial copy is bracketed placeholder — these are templates, not posts.

**`/compliant-unchanged`** — assets that already carried the official towers, copied without modification.

---

## Manifest

### ALREADY COMPLIANT — unchanged
Copied byte-for-byte. Nothing regenerated.

- `fs-avatar-white-400.png` — **application C**, the company avatar
- `fs-symbol-full-color-1024.png`
- `fs-lockup-horizontal / compact / stacked -light-*` (all sizes incl. 2510 / 5020 / 2892)
- `fs-emblem-color-791.png`
- `ajgill-avatar-blue-circle-1024.png` — **application E**, see the rejection below

### REPLACEMENT REQUIRED — done
Each was a white or navy monochrome silhouette.

| Asset | Size | Application |
|---|---|---|
| `florida-signal-share-1200x630.png` | 1200 × 630 | A — lockup swapped only |
| `florida-signal-linkedin-company-banner-1128x191.png` | 1128 × 191 | B |
| `aj-gill-linkedin-banner-1584x396.png` | 1584 × 396 | D |
| `newsletter/img/masthead-lockup.png` | 680 × 385 | F — updated in place |
| `newsletter/img/footer-lockup.png` | 400 × 84 | F — updated in place |
| `newsletter/img/lockup-compact-reverse.png` | 2470 × 516 | F |
| `newsletter/img/lockup-stacked-reverse.png` | 1405 × 795 | F |
| `newsletter/img/emblem-navy.png` · `emblem-white.png` | 791 × 783 | F |
| `favicon-32` · `apple-touch-icon-180` · `icon-192` · `icon-512` | — | G |
| `fs-social-*` × 4 | — | H |
| `fs-lockup-*-navy-colorbar-*` | 902–5020 | canonical family |

### HISTORICAL / ARCHIVE — DO NOT TOUCH
Kept for provenance. Do not re-export or upload.

- `exports/production-hires/` — v1 lockup package
- `exports/production-hires-v2/` — v2 spacing correction
- `exports/linkedin/` — pre-safe-zone drafts
- `exports/linkedin-final/` — the mono-tower LinkedIn set this package supersedes
- `exports/avatars/fs-avatar-navy-*.png` — monochrome tiles
- `uploads/` — source material as received

---

## Verification performed

- **32px legibility** — blue and teal stay distinct on white and on navy. Proof: `_proof-icons-32px.png`.
- **Share card at iMessage width** — bars still register at 320px. Headline only; no "Monday Brief", no "Human-verified public records", no duplicated tagline.
- **LinkedIn rail 340×92** — lockup unclipped, 93px clear each side of the 706px safe window.
- **AJ Gill mobile crop** — content spans x 322–1262 inside the 292–1292 window; the profile photo lands on scrim only.
- **Newsletter** — layout and copy untouched; only the four image files changed, at identical pixel dimensions, so no reflow.

## One rejection — AJ Gill avatar (application E)

**The colour bars were tested and turned down.** Proof: `_proof-ajgill-32px-test.png`.

The electric-blue field is the problem, not the mark. Against `#1767FF` the blue tower `#0175b7` loses nearly all separation. At 32px the peninsula collapses into a single green blob and the Florida silhouette stops reading — measurably worse than the current solid-white mark, which stays crisp at every size.

**The existing `ajgill-avatar-blue-circle-1024.png` is unchanged and should stay in use.** The same bars pass comfortably on white and navy, which is why every other icon adopts them.

## Known limits

- Reverse **transparent** lockups top out at their native 2470 / 1405 px. A higher-resolution transparent reverse would mean chroma-keying the navy plate off the 5020 master, which leaves dark fringing on photo backgrounds. Use the navy-plate masters at 2510 / 5020 when you need more resolution on a solid field.
- `newsletter/img/emblem-navy.png` is a **20px decorative divider at 50% opacity**. It now carries the official towers for consistency, but at that size and opacity the bars are not individually legible. It is `aria-hidden` ornament, not a brand impression.
- Nothing in this package has been published, posted, sent or uploaded.
