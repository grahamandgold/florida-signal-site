Florida Signal — Grok enhanced homepage
========================================
Built from Claude’s files2/florida-signal-site (PREVIEW_13 lineage).
Claude originals were NOT modified:
  - Downloads/files2/florida-signal-site/
  - Downloads/florida-signal-PREVIEW_13.html

Open
----
Double-click:
  /Users/gillfillan/Downloads/florida-signal-site-grok/index.html

Or from Terminal:
  open /Users/gillfillan/Downloads/florida-signal-site-grok/index.html

What changed (Grok touches)
---------------------------
1. MOBILE HERO (main fix)
   Claude stretched the ultra-wide beach photo behind the entire Live Data
   stack. On a phone that crop became a washed building facade + sky.
   Grok:
   - Art-directed mobile/tablet crops (picture sources)
   - Fixed-height hero band on phone (photo only behind header → intro)
   - Live Data + stats sit on clean paper below the photo
   - Lighter scrim so sand / ocean / towers actually read

2. HEADER
   - Mark icon on phone (full lockup is too wide)
   - Compact “Brief” CTA + menu always visible
   - Full lockup + “Get the Free Weekly Brief” from tablet/desktop

3. LIVE DATA
   - Horizontal-scroll tabs on phone
   - Tighter type / panel padding on small screens
   - Trade grid 2×2 on phone

4. DESKTOP / TABLET
   - Improved object-position + scrim for coastline
   - Same editorial system Claude built (ticker, Live Data flip panels,
     stats, desk, charts, meetings, signup, etc.) kept intact

Assets
------
  assets/fort_laud_beach.jpeg          desktop full
  assets/fort_laud_beach_mobile.jpeg   phone crop (ocean + beach + towers)
  assets/fort_laud_beach_tablet.jpeg   tablet crop
  assets/DOWNTOWN_ft_lauderdale.jpeg  signup band
  assets/lockup-horizontal-transparent.png
  assets/mark-square.png

Visual QA shots (Playwright)
----------------------------
  shots/final-mobile.png
  shots/final-desktop.png
  shots/final-tablet.png
  shots/COMPARE-FINAL.png   (Claude vs Grok mobile side-by-side)
