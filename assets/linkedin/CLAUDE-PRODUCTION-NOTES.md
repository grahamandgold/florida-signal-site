# Florida Signal — LinkedIn graphics, production exports

Brand name is **Florida Signal** (never "The Florida Signal"). Personal profile is **AJ Gill**.

Every logo and avatar in this package is a complete Claude Design export placed **unchanged** downstream. Claude produced the colour-bar variants by colour substitution on the existing artwork's pixel grid; no mark was retyped, traced, respaced or reassembled, and the Florida/tower geometry is untouched. The aerial photograph is your original file, cropped only to fill the banner.

---

## Final files — upload these

| File | Size | Where it goes |
|---|---|---|
| `florida-signal-linkedin-company-banner-1128x191.png` | 1128 × 191 | Florida Signal company page → cover image |
| `fs-avatar-white-400.png` | 400 × 400 | Florida Signal company page → logo |
| `aj-gill-linkedin-banner-1584x396.png` | 1584 × 396 | AJ Gill profile → background photo |
| `aj-gill-avatar-blue-circle-1024.png` | 1024 × 1024 | AJ Gill profile → photo |

**Proof sheet:** `proofs/florida-signal-colorbar-rollout-proof-sheet.png` — final colour-bar applications, desktop/mobile crops and small-size checks.

Individual crop proofs (reference only, do not upload): `_proof-rail-340x92.png`, `_proof-mobile-390x106.png`, `_proof-ajgill-desktop.png`, `_proof-ajgill-mobile-390.png`.

---

## The safe-zone rule

LinkedIn scales a cover image to **fill** its container height, then crops the sides. The company banner renders at roughly **340 × 92** in the admin rail — which exposes only the **centre 706px of 1128**. Anything within ~210px of either edge is discarded.

Both banners are composed so all critical content sits inside the centre 60%, clear of the avatar overlay in the lower-left.

| Banner | Content occupies | Safe window | Margin |
|---|---|---|---|
| Company 1128 × 191 | x 492–892 | x 211–917 | 281px left / 25px right |
| AJ Gill 1584 × 396 | x 322–1262 | x 292–1292 | 30px each side |

Measured in the live document, not estimated.

## Company banner decisions

**Horizontal lockup, not the stacked masthead.** At 191px tall the stacked cut forces the wordmark small enough that it breaks up in the rail crop. The final revision places Claude's complete `footer-lockup.png` unchanged at x 492, y 53 at its native 400 × 84 size. The centre-right placement clears both the avatar overlay and the admin-rail crop.

Claude's final pixel comparison found **0 of 33,600 lockup pixels different** from the source `footer-lockup.png`. The rail proof measured 12.0px clearance to the right edge and 11.3px clearance from the avatar.

**No tagline on the artwork.** LinkedIn prints the page tagline directly under the company name, within about 40 vertical pixels of the banner. Repeating it would state the same sentence twice, and at rail scale banner copy renders around 6px tall.

**Seamless field.** The complete lockup is produced on the same `#071B2E` field as the banner, with no visible plate edge.

## Company avatar decision

The navy monochrome icon was replaced with the **full-colour mark on white**. On a navy tile the silhouette ran edge to edge with no surrounding field and read as a dark blob at page-avatar size. On white it has air, and the blue and teal tower accents identify the brand down to 32px. Proofed at 160 / 100 / 72 / 48 / 32.

## AJ Gill banner decisions

**Your photograph, unchanged.** `broward-aerial.jpg` full-bleed at `object-position: 50% 55%`, which holds the Port Everglades inlet, the beach, the barrier island and downtown in the haze. No filter, no replacement.

**Transparent reverse lockup.** Claude's complete compact reverse colour-bar cut has a genuinely transparent background and sits over the photograph without a visible plate.

**Balanced scrim.** Navy runs 26% at the top to 97% at the foot. The photograph stays clearly legible across the upper third; the headline holds contrast without the image being flattened into wallpaper.

**Headline preserved verbatim:** *I read Broward's public record so you don't have to.*

**Avatar overlap verified.** In `_proof-ajgill-desktop.png` the profile photo lands on photograph and scrim only — it never touches the lockup or either line of the headline.

---

## Upload notes

- Upload at the exact pixel sizes above. LinkedIn re-compresses; starting at spec size avoids a second resample.
- The two final banner upload files are true-colour RGB PNGs with no alpha channel. Claude's lossless AJ Gill conversion changed 0 of 627,264 visible pixels from the fully opaque source.
- The company logo is square with a white field — LinkedIn applies its own rounded-corner mask. Do not pre-round it.
- The AJ Gill photo is already circle-masked; LinkedIn applies roughly a 1.1× crop, which the existing export accounts for.
- Uploaded and visually verified on 2026-08-16. LinkedIn's optional page-edit post was declined; no post or invitation was created.
