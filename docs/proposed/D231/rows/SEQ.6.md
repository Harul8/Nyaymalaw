# SEQ.6 - Documents and source-linked summaries

Row 163 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

SEQ.6

## Item

Documents and source-linked summaries

## Description

Implement E6 upload custody/readability and E4 faithful summaries, then integrate uploaded passages into the same context/extraction/review boundaries. Preserve page locations, document instructions as data, revisions, missing pages and uncertainty. Handle progressive bundles. Supplied legal documents can be summarised; their legal use still requires the corpus authority boundary.

## Governs or depends on

SEQ.4-SEQ.5; E6/S6; E4/S4; P11/P14/P19

## Status

Documents built (item 6, 15 Oct 2026): ClamAV check, sealed custody, local reading and Luna reading of scans and photos, documents as a question's material, cited pages, Documents tab; notes in G161 (SEQ.4). Open (round of 15 Oct, G164): reading-pane AI marker, resident ClamAV, daily definitions, Telugu/Hindi/handwriting measurement. | REFRESHED 26 Oct 2026 (checked in the code): of the items listed open on 15 Oct, the marker for pages read by AI (nm/app/api.py, 'Read by AI from a scan or photo'; nm/app/brain-sources.js, 'read by AI from a scan'), the virus check kept running from the start of the app and the daily refresh of its definitions (nm/app/composition.py) are built. Still open: the measurement of Telugu, Hindi and handwriting, which needs a paid run. | CORRECTION 26 Oct 2026 (AN.25): 'the virus check kept running from the start of the app' holds only where the store folder is an absolute path; with the live relative '.nm/matters' the resident scanner could not start (clamd: 'LogFile requires full path'), so every scan reloaded the definitions. Repaired by AN.25 P1.

## Notes

Protect the core evidence chain before expanding input formats. Plain-source usability precedes OCR variants.

## Column 7

2026-10-15 Built as item 6; its decisions, pieces and live check are recorded in G161 under 'ITEM 6'. Open items are listed in G164 (open items round). | 2026-10-16 DEFECT FOUND IN THE OWNER'S END-TO-END RUN (a two-page Word police complaint attached from the owner's account): the receipt said '24 of 30 pages read; scanned pages were not read'. Measured cause: the local Word reader returns one unit per paragraph, and the intake (nm/app/documents.py) turned every unit into a page and every empty paragraph into a 'scanned page with no text layer' waiting for the AI page reader, which cannot draw Word pages. Every ordinary Word file has empty paragraphs. DECISION: only a PDF page with no text layer is a scan for the AI to read; a Word document has no fixed pages and is kept as one page, its paragraphs in order with empty ones skipped; a text file's form-feed parts stay pages, empty parts skipped. A Word or text file with no words at all is unread with that reason, not sent to the AI. | 2026-10-17 FOUND IN THE OWNER'S END-TO-END RUN (synthetic three-page FIR scan attached from the owner's account): the attachment said 'No page could be read' with no reason and no way to try again, while the record said every page was waiting ('the AI could not read this page just now; it can be read again'). A direct call and a second read through the app then read all three pages, so the failure was passing - but its cause was lost: the page reader keeps the advocate's reason and logs nothing, and the voice-note transcriber has the same shape. DECISIONS: (1) each reader logs the provider failure's kind and message at its owner, never page text or words heard; (2) an attachment whose pages or recording wait for the AI shows why, with a 'Read again' (recording: 'Transcribe again') button that asks the same reader again; what was already read stays, and a message can still be sent with the pages unread, which the turn then lists as unread with their reason.
