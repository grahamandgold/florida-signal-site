# Florida Signal brand kit

Florida Signal is a live development-intelligence newsroom for Fort Lauderdale and Broward County, published by Graham & Gold LLC.

## Brand idea

**Development intelligence before the headline.** The Florida emblem is the signature: elegant, dimensional and recognizable at a glance. The visual system pairs an editorial serif with precise field-data typography, bright white space, live teal/cyan signals and controlled yellow/orange accents.

## Logo files

| Use | File |
|---|---|
| Primary horizontal lockup | `assets/lockup-horizontal-transparent.png` |
| Full-color emblem | `assets/mark-full-color.png` |
| Square/social emblem | `assets/mark-square.png` |
| White/reverse emblem | `assets/mark-white.png` |
| One-color navy emblem | `assets/mark-navy-mono.png` |

Keep clear space around the emblem equal to roughly one quarter of its width. Do not stretch, rotate, outline or place the mark in an unrelated circle. Use the square mark for avatars and the horizontal lockup for headers and partner placements.

## Core palette

| Token | Hex | Role |
|---|---|---|
| Florida Navy | `#071B32` | Headlines, navigation, authority |
| Deep Water | `#082A54` | Maps, intelligence surfaces |
| Signal Teal | `#009F91` | Live state, links, location |
| Current Cyan | `#00B8DC` | Motion, focus, secondary signal |
| Florida Sun | `#FFCF4A` | Data emphasis, sponsorship accent |
| Development Orange | `#FF6D3A` | Consequential change, alerts |
| Field Wash | `#EEF7FB` | Light data surfaces |
| Paper | `#FFFFFF` | Primary background |
| Storm Red | `#A81920` | Publisher-controlled Storm Watch only |

## Type

- Display/editorial: **Newsreader**, 400–600.
- Interface/data: **DM Sans**, 400–700.
- Headlines should feel editorial and specific. Labels are short, uppercase and letterspaced. Avoid pill-box tag clouds and generic AI-gradient styling.

## Voice

- Specific: name the address, neighborhood, filing type and event date.
- Sourced: every consequential claim links to the record.
- Field-ready: write for someone walking a block, touring a site or boarding a flight.
- Honest: say sample, snapshot, window or cumulative; never use batch time as the event date.

## Social templates

| Channel | Master | Best use |
|---|---|---|
| LinkedIn + Facebook | `brand/templates/linkedin-facebook-1200x627.svg` | Consequential filings, project changes, meeting outcomes |
| Instagram feed | `brand/templates/instagram-square-1080x1080.svg` | Neighborhood field notes, key numbers, map findings |
| Instagram Story | `brand/templates/instagram-story-1080x1920.svg` | Fast field intel, meeting reminders, Storm Watch updates |
| X | `brand/templates/x-landscape-1600x900.svg` | One sharp intelligence line with a cited detail |

The four SVG masters are portable: their Florida Signal artwork is embedded, so a downloaded template does not lose its emblem or lockup. Replace bracketed copy, keep text inside the existing line count, preserve the source/date line, and link the post to the canonical card or record. Live Graphic Desk exports are in `social/graphic-desk/`.

### Social publishing checklist

1. Duplicate the SVG master; never overwrite the clean original.
2. Replace every bracketed field. If a field is unavailable, remove the entire line rather than guessing.
3. Use the application, registration, recording or meeting date—not the cache/pull timestamp.
4. Export as PNG at the SVG’s native dimensions. Do not crop the perimeter accent or Florida Signal lockup.
5. Put the canonical Florida Signal URL in the post copy and preserve the source link on the destination page.
6. Check the rendered post on a phone before publishing; platform previews can crop the outer 5%.

Suggested caption order: **what moved → where → actual event date → why it matters → source/canonical link**. Keep hashtags restrained and geographic; the visual system should carry the brand.

## Newsletter

`brand/newsletter/florida-signal-daily-intel-brief.html` is a responsive, Mailchimp-safe shell for the Broward Audience. It contains a lead signal, three cited briefs, Neighborhood Field Note, Meeting Watch, Diagram of the Day and a clearly separated sponsorship position.

Never send without editor review. Never expose API keys, private notes, subscriber ZIPs or unpublished CMS drafts.

### Mailchimp setup

1. Create or open the **Broward Audience** campaign and choose a custom-code email.
2. Paste the complete newsletter HTML into Mailchimp’s code editor. Do not paste it into a rich-text block.
3. Keep Mailchimp’s `*|FNAME|*`, `*|DATE:F j, Y|*`, `*|UPDATE_PROFILE|*`, `*|UNSUB|*` and `*|LIST:ADDRESS|*` merge tags intact.
4. Upload `assets/lockup-horizontal-transparent.png` to Mailchimp Content Studio and replace the template's relative logo `src` with the hosted HTTPS URL. The relative path is intentionally used only so the repository preview has a visible logo.
5. Replace every bracketed editorial field and every placeholder `href` with the canonical Florida Signal URL for that item.
6. Send Mailchimp’s desktop and mobile test, verify every source link, then send an internal proof before scheduling.

The email stacks its header and two-column modules below 600px, uses table layout and inline presentation styles for broad email-client support, and retains a plain, descriptive alt label on the Florida Signal lockup. The sponsor position is visually separated from editorial content.
