# AN.18 - Build: the design's fonts served by the app itself (no font service)

Row 245 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.18

## Item

Build: the design's fonts served by the app itself (no font service)

## Description

SEES: Source Serif 4 and Source Sans 3 drawn from the app's own server. NEEDS: the asset server to serve font files (today it serves only .css, .html, .js and .svg), the font files under their open licence, and their declaration. Not started.

## Governs or depends on

P52; AN.13

## Status

Proposed 25 Oct 2026. Not started. | AGREED 25 Oct 2026 (O24 item 3). Building: Source Serif 4 and Source Sans 3 (SIL Open Font License 1.1) as .woff2 files declared like every other browser asset; the asset server and the layout owner admit .woff2 as font/woff2; the app's and the site's style sheets name them with @font-face pointing only at this server. | BUILT 26 Oct 2026, pieces 1-7: (1) 1bd49b62 nm/shared/source_layout.py owns the media types a browser asset may be and admits .woff2 as font/woff2, the list otherwise closed; (2) 256adfa6 nm/app/static_assets.py reads them and serves a declared font byte for byte; (3) 4d822215 the eight fonts - Source Serif 4 (4.004) and Source Sans 3 (3.052), Adobe, SIL Open Font License 1.1, unmodified variable-weight subsets (Latin and Latin Extended, upright and italic) from the @fontsource-variable packages 5.3.1 - in nm/app/fonts with OFL.txt, declared; .gitattributes marks .woff2 binary; (4) e85ae666 nm/app/fonts/fonts.css declares the faces once, from /static only, Latin Extended (the rupee sign) loading only when used; (5) 8889b88f the app's page links it first; (6) c4ca0e80 the app's style sheet says so; (7) cc07fa1c every public page links it too (pages and generator, a rebuild byte-identical). DONE OFFLINE: asset serving (25 declared), the new font tests, the public-site tests, the style sheet guards; every font the sheet names comes back 200 as font/woff2 from the one server. NOT YET: the owner's browser.
