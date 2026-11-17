# AN.40 - 4 Nov 2026: a message sent while its files are still being read waits for them - Send greyed, with Cancel - and goes by itself once they are read, instead of a 'wait' message

Row 275 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.40

## Item

4 Nov 2026: a message sent while its files are still being read waits for them - Send greyed, with Cancel - and goes by itself once they are read, instead of a 'wait' message

## Description

THE OWNER'S WORDS, 4 Nov 2026: "when files are attached, and while they are being read, if SEND button is clicked, then greyout SEND button and once file scanning / reading is done send them automatically, instead of saying files are being read so wait kind of message --tell me what you will do first"
Claude proposed the plan below, with two choices and a recommendation for each (what goes if the advocate types on; what happens when a file fails). THE OWNER'S WORDS, 4 Nov 2026: "Go ahead" - both recommendations taken.
DECISIONS (agreed 4 Nov 2026):
D61. Send (or Enter) pressed while any attached file is still being uploaded, converted or read holds the message: Send is greyed and reads "Sends when read...", with Cancel beside it; the line under the files says the message will go as soon as the files are read; each file keeps showing its own progress. Once nothing is being read the message goes by itself, through the same path a pressed Send takes (the copies' second look, the documents, the model and effort chosen).
D62. What goes is what is in the message box when the reading ends: the advocate can still correct it while waiting (owner: recommendation taken).
D63. If a file read meanwhile could not be used (failed or held) or came back with pages not read (an error, or AI data sharing off), nothing is sent: Send works again and the line under the files names the file and says why (owner: recommendation taken). Anything else that stops a pressed Send (a recording still running, too many files, an empty box, sending paused) stops it too, with today's words.
D64. The same hold for words added while NM was answering, and for answers sent from NM's questions window: they wait for the files and go by themselves, instead of returning to the box. Cancel stops the waiting message and leaves the words and files as they were; opening another conversation cancels it, so it never goes in a conversation other than the one it was sent in; nor after the advocate signs out. The matter board and the reading pane (frozen, D60) are not touched.

## Governs or depends on

AN.25 (scanned pages read as a background job); AN.37 (the questions window, D44); 15 Oct 2026 (adding to a question while it is worked on); AN.39 D60 (the board and the pane frozen - not touched here)

## Status

AGREED 4 Nov 2026 (D61-D64). BUILT (4cdc0ac6) and APPLIED to the running server 4 Nov 2026 on the owner's word ("Apply"), with AN.39. Open: browser acceptance.

## Notes

WHAT EXISTS, read in the code 4 Nov 2026: a message sent while a file is converting, uploading or being read is refused with "Wait until the attached documents have been read." (attachmentsBlockSend, checked by send); the words stay in the box and Send must be pressed again. Words added while NM was answering return to the box if a file is still being read when the answer is saved; the questions window says the same "wait" words.
PIECE: one page file (nm/app/app.js) with a page test: the hold, its release when a file's upload or reading ends or a file is removed, the greyed Send with Cancel, and the cancels; built in a copy of the tree, applied only on the owner's word.

## Column 7

BUILT 4 Nov 2026 (4cdc0ac6), one page file (nm/app/app.js) in a copy of the tree, published by a temporary index; not applied. send() holds a message while any file is uploading, converting or being read (after today's other checks: a recording running, a file held or failed, too many files); Send is painted by one function (paintSend): greyed 'Sends when read...' with Cancel beside it; the line under the files says the message will go as soon as they are read. releaseHeld, asked whenever an upload or reading ends or a file is removed or added failed, sends through send() once nothing is being read: the box's words (D62), or words sent another way as they are (D64: words added while NM answered, answers from the questions window). It does not send - Send works again, the line names the files - if a file read meanwhile failed, was held, or came back with a note or pages left for the AI (D63; files already read when Send was pressed count as seen); nor with an empty box, paused sending or anything a pressed Send refuses. Cancel, opening another conversation (selectIntent) or a signed-out session let it go; words sent another way return to their own conversation's box or draft.
CHECKS: a new page test (tests/js/send_when_read.mjs) runs the actual send(), attachments and hold over invented files: sent by itself with the box's words as edited; not sent for a file not fully read, Send back; a file read before Send not held against it; Cancel; words sent another way go as they are, and return above the box's words when let go; another conversation; an empty box; a recording. Four broken versions of the hold each fail it. Seven page tests that pin Send updated (harness state, the questions window's check, the usage pin). Every page test, the questions-window and sign-in tests: 103 passed, 1 failed - register_steps.mjs, failing the same way before AN.39. The board and pane pin (D60) still passes: neither is touched.
NOT RUN: the browser; the full suite.
APPLIED 4 Nov 2026 with AN.39 (one restart; see AN.39's note). NOT RUN: the browser.
