# DG-14 — one board and a readable conversation

22 September 2026. Diagnostic registered in Before Build before implementation.
Base remains 43f80a9 plus the existing uncommitted work. No commit or push.

## Delivered

- Desktop: one full-height sidebar, navigation above the matter board, signed-in
  identity/workspace and profile at its foot. Right pane is the conversation,
  compact title and composer. A scripted-rehearsal warning, when applicable,
  remains visible rather than being hidden to obtain a full-height measurement.
- One DOM-owned board moves between the desktop sidebar and the narrow-screen
  drawer. There are no cloned account/board states. Home, matter list, opening,
  Case file, History and Preparation retain their navigation.
- Removed duplicate issue cards and the recorded-issue count. No stored issue or
  opening record was deleted. Client/opponent still come from the recorded
  matter; the removed card's `our_client_is` actually represented procedural role.
  It is not evidence that a known client is a plaintiff or defendant.
- Stale-deadline value and warning now remain on the single board as well as the
  matter list. Removing issue cards must not remove the old date from view.
- Answer bodies render as paragraphs in the validated answer's order. Internal
  section/type/signal headings are not shown. Substantive warnings, disclosures,
  dates, references and default-open supporting passages remain. Metrics stay in
  the existing on-demand audit. No extra model paraphrase rewrites verified text.
- Historical response text remains unchanged and explicitly historical. Cleaner
  layout does not repair the earlier advisory/posture question or other DG-13
  content. These remain open.

## Controlled verification (not live-model judgment)

- Initial focused run: 26 checks, one test-assumption failure. The rehearsal
  banner correctly occupied 32.6px; the new layout test had incorrectly demanded
  y=0 even in a scripted environment. The corrected test requires the banner to
  remain visible and accounts for its measured height.
- Broad selected run (`dg14-regression.xml`): 115 checks, six failures, no skips.
  Two correction phases assumed My work reopened a chat instead of the matter
  list; one expected the removed internal progress sentence; three expected
  submitted text to remain in the composer. Earlier heading-based expectations
  had also been replaced with exact answer-body/history comparisons.
- Affected-suite rerun (`dg14-recheck.xml`): all 33 checks pass, no skips.
  This includes all correction phases, context/race/permission-retry checks and
  the new presentation witnesses. Retry-envelope equality, single recorded
  instruction, withheld-answer protection and stale-date assertions remain.
- Latest result per distinct test across those two files: 115 passing, zero
  unresolved failures/errors/skips. This is not a new full Class-A run or an
  evidence promotion. The earlier failed records are retained.
- JavaScript syntax, targeted Python lint and changed-file whitespace checks
  pass. Workbook scenario reconciliation remains 19 executable subsets among
  91 planned features, with 72 gaps honestly retained.
- Code Review Graph search/relationship inspection used; current index refreshed
  without paid embeddings. Search used its available keyword/FTS fallback.

## Actual Chrome observation

User's existing signed-in Chrome session at http://localhost:8071/, synthetic
matter `SYNTHETIC LIVE 01 — family title and new access obstruction` only.
Server restarted with existing configuration, encryption key and cumulative
GPT-4o mini budget ledger intact. No new live-model submission for this UI pass.

At the observed 1536 x 674 CSS viewport:

- right conversation x=304, y=0, width=1232, height=673.6;
- compact title height=44.8; profile button x=13.6, y=613.7, height=42;
- profile opened upward, wholly inside the viewport;
- duplicate issue cards=0; internal answer headings/type labels=0;
- History showed one saved turn, five answer-body paragraphs and zero internal
  element labels; its recorded-response warning remained;
- Case file's opening record retained the synthetic client, both recorded
  opposing parties, advice/research-only scope and no proceedings reported;
- composer remained empty after reload/re-entry. No original message was resent.

DG-13 and the five-matter live-quality acceptance remain open. Zero of five
matters are accepted complete. Qualified review is still deferred; BK-85-AC3
remains NOT_RUN. This record claims presentation verification, not legal quality.

## Owner follow-up — compact navigation

The owner requested the four navigation destinations in one compact row. The
desktop navigation is now a segmented control with complete labels, a visible
current-page state and unchanged keyboard operation. No icons replace the names.
Eleven focused checks pass (`dg14-compact-tabs.xml`), including navigation at
390, 768, 821, 1024, 1280 and 1536px. Python lint also passes. The initial 42px
height assertion caught 0.8px excess padding; the padding was reduced, not the
acceptance threshold.

Actual signed-in Chrome confirms all four buttons on y=72.3125, each 36px high
with unclipped text. The full control is 41.6px high. The board begins at
y=183.1125 instead of 234.6125, returning 51.5px to the matter area. The server
was refreshed with its existing data and evaluation ledger; no new model call,
matter submission, permission change, commit or push was made.
