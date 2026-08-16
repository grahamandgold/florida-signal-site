# Florida Signal — production-hires lockups

Export correction. The approved lockup is visually unchanged — same emblem geometry, colors, type, alignment and clear space. This package only fixes **resolution**: the previously deployed horizontal file was 572×246 (wordmark ~360px), which blurs on Retina. These are re-exported at production resolution, tightly cropped to the approved clear space with no oversized transparent canvas.

The wordmark is live type, so it is razor-sharp at every size here. The emblem is your original 791×783 raster; files are built so the emblem never exceeds its native resolution (the 5020-wide horizontal renders the emblem at ~720px — within source), keeping it crisp.

## Lockup files (all tightly cropped)

| File | Pixels (W×H) | Background | Web use |
|---|---|---|---|
| `fs-lockup-horizontal-transparent-2510.png` | 2510 × 569 | transparent | **Landing-page header** — drop on white/cream |
| `fs-lockup-horizontal-transparent-5020.png` | 5020 × 1138 | transparent | Header on very large / 3× displays, hero, print |
| `fs-lockup-horizontal-navy-2510.png` | 2510 × 569 | Atlantic navy | Horizontal on navy sections |
| `fs-lockup-horizontal-navy-5020.png` | 5020 × 1138 | Atlantic navy | Same, large / print |
| `fs-lockup-compact-transparent-2510.png` | 2510 × 556 | transparent | **Landing-page footer** — no-tagline cut on white |
| `fs-lockup-compact-transparent-5020.png` | 5020 × 1112 | transparent | Footer on large / 3× displays |
| `fs-lockup-compact-navy-2510.png` | 2510 × 556 | Atlantic navy | Compact on navy footer |
| `fs-lockup-compact-navy-5020.png` | 5020 × 1112 | Atlantic navy | Same, large |
| `fs-lockup-stacked-transparent-2892.png` | 2892 × 1728 | transparent | Square-ish placements on light |
| `fs-lockup-stacked-navy-2892.png` | 2892 × 1728 | Atlantic navy | Square-ish placements on navy |

### Which file for the site
- **Header:** `fs-lockup-horizontal-transparent-2510.png`. The header renders the mark at roughly 30px tall CSS; on a 3× phone that's ~90px of real pixels, so a 2510px asset has enormous headroom and stays crisp. Serve the `-5020` if you ever place it larger than ~600px wide.
- **Footer:** `fs-lockup-compact-transparent-2510.png` — matches the approved no-tagline footer cut.
- Set the CSS display width and let the browser downscale; never upscale past the file's pixel width.

## Source emblem (`source-emblem/`)
Your three original files at 791×783, included so this package is self-contained: full color, white reverse, navy mono.

## On SVG
A true vector SVG is **not** included on purpose. The emblem you supplied is raster, not vector paths — auto-tracing it would change the artwork (edges, corner radii, the tower geometry), which you asked me not to do. Rather than fake a vector, these high-resolution PNGs are the faithful production assets. If you later locate the original vector (AI/EPS/SVG) for the emblem, send it and I'll produce true SVG lockups with the wordmark outlined — no artwork change.

## Verified before shipping
Each file was inspected at full pixel size: dimensions confirmed, transparent versions confirmed to have a genuine alpha channel (~88% fully transparent canvas), navy versions fully opaque, and the horizontal wordmark confirmed crisp at 5020px — clean letterforms and emblem edges, no blur.
