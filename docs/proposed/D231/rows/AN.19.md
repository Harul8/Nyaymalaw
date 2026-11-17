# AN.19 - Build: the Usage and plan window (P53, AN.17)

Row 249 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.19

## Item

Build: the Usage and plan window (P53, AN.17)

## Description

SEES: Usage and plan opens over the workspace from the usage chip, from a usage notice's See plans, and from a new item in the person menu, as the signed-off page draws it: YOUR USAGE - the allowance's name, the percentage left in words and a meter, and 'You are on the trial. Choose a plan below when you want more.' (at nothing left, the owner's words of P51); YOUR PLAN - Trial, 'You have no plan yet. Choose one below when you want more usage.', and 'No invoices yet'; CHOOSE A PLAN - Pro (₹5,000), Elite (₹10,000) and Enterprise (Custom, from ₹15,000 a month), each excluding GST, in exactly the public Plans page's words (a test pins the two together; the credits stay as the owner left them, blank). Pro and Elite cannot be chosen yet and say so ('Payment is not open yet'); Enterprise's Talk to us opens the About page. MUST NEVER: show usage as cents, credits or rupees (O21; the ₹ figures are the plans' prices); offer a purchase that does nothing without saying so; read anything but the percentage and the plan name from the server; keep one account's usage on screen after sign-out. DEVIATION FROM THE DRAWN PAGE, TO CONFIRM: it opens as a window over the workspace, as AI data sharing and Dictation do, rather than as a page replacing it, so the open matter, the draft and any answer in progress are untouched; and its closing line says NM 'shows you the plans' where the design says 'offers an upgrade', which is not true until payment exists. PIECES: index.html (the window and the menu item), app.css, app.js, each with its focused test. PASS: the offline tests pass and the owner sees it in their browser. FAILURE SCOPE: display only; the allowance and its refusals are unchanged. RECOVERY: revert the commits.

## Governs or depends on

P53; AN.17; O21; O24; O26

## Status

Agreed 26 Oct 2026 (O26). Building. | BUILT 26 Oct 2026, pieces 1-6: (1) 58f6f9cd index.html - the window (a dialog over the workspace, like AI data sharing and Dictation) with Your usage, Your plan, No invoices yet and Choose a plan, and the person menu's Usage and plan item; the chip and the notice keep their link to the public Plans page as the fallback; (2) c6ec5ccb app.css - the window in the signed-off design (three plans side by side, stacking below 900px, nearly full screen on a phone); (3) c83926b5 and (4) 72361b80 - the large percentage and the small word 'left'; (5) 23db8f13 app.js - opens from the chip, a notice's See plans (plain clicks only; a click with a modifier key keeps the link) and the person menu; fills the name, percentage, meter and sentence from the server alone, the owner's words at nothing left; shows what is known at once and then the server's current word; says so when the read fails; ignores an answer that arrives after closing, reopening or sign-out; sign-out closes it and puts the usage away; (6) 8d367d0a F-A-17 now names Usage and plan among the person menu's items (the sheet's current-requirement, must-do, scenario and executable-scenario cells, the feature file and the step, whose pattern had silently passed over a button with one more attribute). Pro and Elite say 'Payment is not open yet' and cannot be chosen; Enterprise's Talk to us opens the About page. DONE OFFLINE: tests/test_usage_plan_window.py (the window's contents; the plans in the app are the public Plans page's - shown to catch a changed price, promise or credits figure; no plan offered that cannot be had; usage never in cents, credits or dollars), tests/js/usage_plan.mjs (shown to catch eight mistakes); every script test and the page, sign-in, account and stylesheet tests pass. NOT YET: the owner's browser. TO CONFIRM (the two deviations in the contract): a window over the workspace rather than a page, and the closing line saying NM 'shows you the plans'.

## Column 7

4 Nov 2026, THE OWNER'S WORDS: "From usage and plan tabs - remove this point [XX] usage credits each month". Removed from Pro and Elite in the Usage and plan window and, as the window's plans are the public Plans page's word for word, from the public Plans page and the home page's plan cards; Enterprise keeps 'Usage credits and terms agreed with you'; the placeholder style it alone used went with it. The plan and public-site tests pass (65). Pushed; NOT applied to the running server - needs the owner's word.
APPLIED to the running server 4 Nov 2026 on the owner's word ("apply"): five files, health ready; the app, the home page and the Plans page as served no longer carry the line, Enterprise's line kept; all 15 saved conversations (19 answers) reopen.
