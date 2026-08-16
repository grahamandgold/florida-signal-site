# Florida Signal vector-master brief

## Objective

Create a true vector master of the approved Florida Signal emblem and lockups without changing the signature geometry.

## Authoritative reference

Use `sources/mark-full-color.png` as the geometry reference. Also use `sources/mark-white.png` and `sources/mark-navy-mono.png` to confirm knockout and one-color behavior.

The finished mark must preserve the exact Florida silhouette, building forms, negative spaces and proportions. Do not add an arrow, smooth the state into a generic outline, stretch the peninsula, or reinterpret the building shapes.

## Production method

1. Rebuild the emblem as clean closed Bézier paths in Adobe Illustrator, Affinity Designer or Inkscape.
2. Use manual path refinement. Automatic image tracing may be used only as a starting point, never as the final artwork.
3. Sample the approved colors directly from the full-color source. Do not introduce gradients, shadows or new colors.
4. Build full-color, Atlantic-navy mono and white-reverse symbols.
5. Recreate the horizontal, compact and stacked lockups. Keep an editable-type master and a distribution copy with type converted to outlines.
6. Use a transparent artboard with documented clear space and no hidden raster images.

## Required deliverables

- `fs-symbol-master.ai`
- `fs-symbol-full-color.svg`
- `fs-symbol-navy-mono.svg`
- `fs-symbol-white.svg`
- Horizontal, compact and stacked lockups in SVG and print-ready PDF
- One editable master with live type
- One outlined master with no external font dependency
- A 4096 px transparent PNG proof sheet

## Acceptance test

- Overlay the vector on `sources/mark-full-color.png` at the same dimensions and 50% opacity. The silhouette, towers and negative spaces should remain visually stationary.
- Inspect at 1600%, then test at 1024, 400, 180, 32 and 16 pixels.
- Confirm there are no stray points, open paths, embedded raster images, clipping mistakes or added arrow forms.
- Confirm the white version works on Atlantic navy and photography.
- Record the typeface, color values, clear-space rule and creation date in the final handoff.

Do not replace the approved website exports until this overlay test passes.
