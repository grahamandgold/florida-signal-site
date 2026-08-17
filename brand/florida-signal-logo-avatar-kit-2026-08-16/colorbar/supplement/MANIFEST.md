# Florida Signal — colour-bar supplement

Supplement to the approved colour-bar package. Contains only the files omitted from that
download. Nothing here changes any approved layout, copy, dimension or logo geometry.

Not published, posted or uploaded.

---

## 1 · Newsletter replacement images

Drop-in replacements. Every file keeps the **exact pixel dimensions of the asset it
replaces**, so the Mailchimp master needs no edit and cannot reflow — the HTML sets
`width="340"` on the masthead and `width="200"` on the footer, and both files remain at 2×
those display widths.

| Path in ZIP | Dimensions | Replaces |
|---|---|---|
| `newsletter/img/masthead-lockup.png` | 680 × 385 | stacked reverse, mono towers |
| `newsletter/img/footer-lockup.png` | 400 × 84 | compact reverse, mono towers |
| `newsletter/img/lockup-compact-reverse.png` | 2470 × 516 | compact reverse master |
| `newsletter/img/lockup-stacked-reverse.png` | 1405 × 795 | stacked reverse master |
| `newsletter/img/emblem-navy.png` | 791 × 783 | divider emblem, light sections |
| `newsletter/img/emblem-white.png` | 791 × 783 | divider emblem, dark sections |

All six verified against these dimensions at export time.

**Install:** copy the `newsletter/img/` folder over the existing one. Do not rename.

> `emblem-navy.png` is used at **20px, 50% opacity, `aria-hidden`** as a rule ornament. It
> now carries the official towers for consistency, but at that size they are not
> individually legible. That is expected and is not a brand impression.

---

## 2 · Social template SVG composition masters

Editable artboards matching the approved PNG templates exactly — same dimensions, same
layout, same copy. Every text element is live `<text>`. **The logo is a linked complete
raster asset, never traced or converted to paths.**

| Path in ZIP | Artboard | Lockup referenced |
|---|---|---|
| `brand/templates/linkedin-facebook-1200x627.svg` | 1200 × 627 | `./assets/fs-lockup-compact-reverse-colorbar-2470.png` |
| `brand/templates/instagram-square-1080x1080.svg` | 1080 × 1080 | `./assets/fs-lockup-compact-reverse-colorbar-2470.png` |
| `brand/templates/instagram-story-1080x1920.svg` | 1080 × 1920 | `./assets/fs-lockup-stacked-reverse-colorbar-1405.png` |
| `brand/templates/x-landscape-1600x900.svg` | 1600 × 900 | `./assets/fs-lockup-compact-reverse-colorbar-2470.png` |

### Referenced assets — included, so the SVGs render after extraction

| Path in ZIP | Dimensions |
|---|---|
| `brand/templates/assets/fs-lockup-compact-reverse-colorbar-2470.png` | 2470 × 516 |
| `brand/templates/assets/fs-lockup-stacked-reverse-colorbar-1405.png` | 1405 × 795 |

Links are relative (`./assets/…`) and resolve from the SVG's own folder. Keep
`assets/` as a sibling of the four SVGs. All four were opened and verified: viewBoxes match
the PNG dimensions and every asset link resolved at full natural size.

### Lockup placement — do not alter

| Artboard | x, y | Placed size |
|---|---|---|
| LinkedIn / Facebook | 72, 64 | 330 × 69 |
| Instagram square | 80, 80 | 340 × 71 |
| Instagram Story | 360, 200 | 360 × 203.7 |
| X landscape | 96, 88 | 380 × 79 |

### Type

Positions were measured off the rendered PNG artboards, so baselines and line breaks match.

- Headline — `Newsreader, Georgia, 'Times New Roman', serif`
- Labels, source line, URL — `Archivo, 'Helvetica Neue', Helvetica, Arial, sans-serif`

Neither is embedded. Install **Newsreader** and **Archivo** (both Google Fonts) before
editing, or the artboard falls back to Georgia and Helvetica and the metrics shift.

### Colour

| Hex | Use |
|---|---|
| `#071B2E` | field |
| `#41D7E9` | module label, accent gradient end |
| `#1767FF` | accent gradient start |
| `#FFFFFF` | headline |
| `#93AFC6` | source line |
| `#7FA3C0` | URL |

The accent bar is a `linearGradient` with `id="accent"`, left to right.

### Editorial copy

Bracketed placeholders — `[ MODULE LABEL ]`, `[ ONE-SENTENCE VERIFIED FINDING ]`,
`[ SOURCE · RECORD ID · DATE ]`. Identical to the approved PNGs. These are templates, not
posts; no Florida Signal reporting is invented anywhere in this package.

---

## Not touched by this supplement

The approved share card, both LinkedIn banners, the AJ Gill avatar decision, the company
avatar, and every historical archive remain exactly as delivered.
