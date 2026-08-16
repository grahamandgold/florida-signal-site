# Florida Signal — production-hires-v2

Spacing correction only. This supersedes `production-hires` (v1). The v1 folder is left in place, untouched, for comparison.

## What changed
The underline and DEVELOPMENT INTELLIGENCE moved **up as a unit**, and the gap between the rule and the tagline **tightened**. Nothing else was touched.

Measured at the real 440 px masthead size:

| | Before (v1) | After (v2) | Delta |
|---|---|---|---|
| Wordmark → rule | 11.6 px | 3.0 px | **raised 8.6 px** |
| Rule → tagline | 9.3 px | 5.8 px | **tightened 3.5 px** |
| Tagline net movement | — | — | up 12.1 px |
| Lower-block height | 72.3 px | 60.2 px | −12.1 px |

Both deltas land inside the requested 8–10 px and 3–4 px ranges. The change is expressed in `em`, so it scales proportionally at every export size.

## Verified unchanged
Measured identical before and after at the same render size: **rule width 354 px**, **wordmark width 354 px**, **tagline width 354 px**. Lockup width is byte-identical at export scale (2510 px in both v1 and v2). Emblem geometry, wordmark typeface and weights, letter-spacing, tagline size and tagline tracking, and all colours (Atlantic navy `#0A2134`, electric blue `#1868FF`, aqua `#57D6D1`, rule `#C3CCD8` / white 34%) carry over untouched. No arrow, no redraw, no new typeface.

Only the overall height changed — 569 → 556 px on the horizontal, 1728 → 1644 px on the stacked — which is the correction itself.

## Files

### Revised — horizontal
| File | Pixels (W×H) | Background | Web use |
|---|---|---|---|
| `fs-lockup-horizontal-transparent-2510.png` | 2510 × 556 | transparent | **Landing-page header** |
| `fs-lockup-horizontal-transparent-5020.png` | 5020 × 1112 | transparent | Header at 3× / hero / print |
| `fs-lockup-horizontal-navy-2510.png` | 2510 × 556 | Atlantic navy | Horizontal on navy |
| `fs-lockup-horizontal-navy-5020.png` | 5020 × 1112 | Atlantic navy | Same, large / print |

### Revised — stacked
| File | Pixels (W×H) | Background | Web use |
|---|---|---|---|
| `fs-lockup-stacked-transparent-2892.png` | 2892 × 1644 | transparent | Square-ish placements, light |
| `fs-lockup-stacked-navy-2892.png` | 2892 × 1644 | Atlantic navy | Square-ish placements, navy |

### Unchanged — compact / no-tagline
Carried over from v1 byte-for-byte. The compact cut never renders the rule or tagline, so the correction does not apply to it.

| File | Pixels (W×H) | Background | Web use |
|---|---|---|---|
| `fs-lockup-compact-transparent-2510.png` | 2510 × 556 | transparent | **Landing-page footer** |
| `fs-lockup-compact-transparent-5020.png` | 5020 × 1112 | transparent | Footer at 3× |
| `fs-lockup-compact-navy-2510.png` | 2510 × 556 | Atlantic navy | Compact on navy footer |
| `fs-lockup-compact-navy-5020.png` | 5020 × 1112 | Atlantic navy | Same, large |

### Source emblem (`source-emblem/`)
Canonical originals at 791 × 783 — full colour, white reverse, navy mono. Included so the package is self-contained.

## Which file for the site
- **Header:** `fs-lockup-horizontal-transparent-2510.png`. Rendered ~440 px wide on desktop and ~30 px tall in the mobile masthead; at 3× that is well inside the file's resolution.
- **Footer:** `fs-lockup-compact-transparent-2510.png` — unchanged from v1.
- Use `-5020` only if the placement exceeds ~600 px wide. Set the CSS display width and let the browser downscale; never upscale past the file's pixel width.

## Verified before shipping
Rendered dimensions confirmed in the DOM before capture; exported pixels inspected at full size and at 2× crop. Letterforms and emblem edges are clean, transparent files carry a genuine alpha channel, navy files are fully opaque. The horizontal wordmark occupies 2270 px of the 2510 px canvas — roughly 6× the pixels it needs on a 3× mobile masthead.

## Still not included: SVG
The supplied emblem is raster, not vector paths. Auto-tracing would alter the artwork, so no SVG is provided. Send the original vector (AI / EPS / SVG) and I will produce true SVG lockups with the wordmark converted to outlines, with no artwork change.

## Not deployed
Nothing has been pushed to the site. The landing page still references the v1 assets pending your review.
