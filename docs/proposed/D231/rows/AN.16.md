# AN.16 - Build: the public site at nyaymalaw.in - the homepage and six pages, served by the app (P52)

Row 243 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.16

## Item

Build: the public site at nyaymalaw.in - the homepage and six pages, served by the app (P52)

## Description

SEES: nyaymalaw.in opens the homepage; How it works, What it holds, Trust, Plans, About and Legal open from its menu and footer; Sign in and Create account open the app. PROPOSED (Claude, within the agreed one-deployment decision): the public pages are declared browser assets at their own addresses and the app moves to /app, with the password-reset link following it. MUST NEVER: let a public page read a matter or need a session; claim anything the product does not do (the pages use the product's own notices). PIECES: the asset server (one file), the pages (declared assets), the reset link (api.py), each with tests. Not started.

## Governs or depends on

P52; O19; O23

## Status

Agreed 25 Oct 2026 (O23). Not started; the move of the app to /app to be confirmed with the owner. | BUILT 25 Oct 2026: piece 1 (8d2df7bb) the homepage and the six pages as static pages of the app (nm/site: one style sheet, no script, nothing from another host, links only to the site and the app, blanks blank, usage as a trial allowance), declared in the manifest; piece 2 (b84315f7, static_assets.py and api.py, one inseparable change) the addresses - / the homepage, /how-it-works, /what-it-holds, /trust, /plans, /about, /legal, and the app at /app - and the password-reset link at /app#reset=; piece 3 (4651d9a5, app.js) Create your account opens the register card through /app#register; pieces 4-5 (98b7852f, 0d7e241d) the sign-in page's wordmark leads back to the homepage. DONE OFFLINE: asset serving (each address serves its page, the homepage is not the app, undeclared addresses are 404), password reset, sign-in features, CSRF on every unsafe route, the new public-site test (214 passed together); the browser journeys' visits moved to /app (not run). NOT YET: the owner's browser; the move to /app is the owner's to confirm (bookmarks to the old address now open the homepage, whose Sign in opens the app). | CONFIRMED 25 Oct 2026 (O24 item 1): the app at /app. And the owner's statement (O24): the public site is not separate - the local server opens on the homepage and every page follows from it, so the same thing deploys as it is. As built: one server serves the homepage at /, the six pages, the sign-in and the tool at /app; start.ps1 opens the homepage. CHECKED OFFLINE 25 Oct 2026: a walk from /, following every link on every page, reached all seven pages, the site's style sheet, the app and its assets, each answered 200 by the one server. A public deployment changes settings only (its public address for the reset links, email delivery, registration switched on, HTTPS in front), not the pages or the code. | 26 Oct 2026, piece 6 (a4f23178): start.ps1 says what the one server serves and that it opens the homepage. | AMENDED 26 Oct 2026 by O28/AN.22: a public page may run one script of ours that asks only who is signed in (and ends a sign-in on request); it still reads no matter and needs no session.
