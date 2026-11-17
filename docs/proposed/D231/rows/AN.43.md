# AN.43 - 5 Nov 2026: each conversation in the history listed under a short title of at most ten words - crisp and apt, written by the model from the matter's details, naming the client where they are known - instead of its first message

Row 278 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.43

## Item

5 Nov 2026: each conversation in the history listed under a short title of at most ten words - crisp and apt, written by the model from the matter's details, naming the client where they are known - instead of its first message

## Description

THE OWNER'S WORDS, 5 Nov 2026: "Conversation history -- put a small name to the matters in the list instead of large text -- may be just put party / client name - max 10 words title for the matter"
Claude found (read-only, 17 saved conversations): first messages run from 2 words to about 2,900; only the 4 newest understandings mark which party is the client (research v13 on), the 13 older list the parties without it; 5 have no understanding at all. Claude proposed a title made by code (client v. other side; else the first dispute's name; else the message's first ten words), Rename on each line, the title as the open conversation's heading, and asked whether titles change later. THE OWNER'S WORDS, 5 Nov 2026: "when client names are not available or details are not available - let the model put a appropriate title based on the matter details --- I don't particularly want a tempate for this, but more of a crisp and appropriate title for it"

DECISIONS (agreed 5 Nov 2026):
D81. The conversation history lists each conversation under a short title of at most ten words instead of its first message; the first message stays readable on hover.
D82. The model writes the title from what is known of the matter - crisp and apt, no template - naming the client (the party) where the matter makes them known, and where names or details are not available still giving an appropriate title from what there is. Code checks only what is mechanical: one line, not empty, at most ten words. It uses no name or fact it was not given.
CLAUDE'S PROPOSALS, not yet changed by the owner (built so, for the owner to see in the browser): (a) the title is written with the conversation's first answer, as soon as NM has understood the matter, and NM does not rewrite it afterwards - except once, where the first was written before any matter was understood (a greeting) and a later message brings one; (b) conversations saved before this get their title with their next message, or all at once in a small paid run on the owner's word; (c) where there is no title yet, the first ten words of the first message stand, with an ellipsis.
OPEN, for the owner: Rename on each line (the advocate's own title always wins); the same title as the open conversation's heading, which today says 'New matter'.
MUST NEVER: a name or fact not in the messages or papers; one conversation's names on another's line; the wrong party called the client; a title over ten words.
PASSING (the owner's browser acceptance): each line of the history one short title; the client named where known; old conversations titled once they are next used (or after the run); hovering shows the first message.
Claude asked (5 Nov 2026): title the conversations saved before in one small paid run, or each with its next message; Rename on each line, and the title as the open conversation's heading. THE OWNER'S WORDS, 5 Nov 2026: "1 - Yes 2 - put the heading just once in the begining, after the first message is saved, till the NM names it, we can put <empty title> and once NM names it, let it stay that way"
DECISIONS (agreed 5 Nov 2026):
D83. The conversations saved before are titled now, all at once, in one small paid run - one short call each - on the owner's word.
D84. An open conversation shows its title once, at its beginning, from when its first message is saved: an empty title until NM names it, and once NM names it, it stays as named. NM never writes a conversation's title again - this replaces Claude's proposal (a), which wrote it a second time where the first came before any matter was understood.
Rename on each line: not asked for; not built.

## Governs or depends on

O29 (the history, ten at a time); AN.41 D66-D67 (a conversation in the history from Send; the understanding saved about a minute in); 13 Oct 2026 (reasoning loops, natural prompts); AN.39 D60 (the board and the pane - not touched)

## Status

AGREED 5 Nov 2026 (D81-D84). BUILT and APPLIED 5 Nov 2026 (43a-43e); the conversations saved before titled (D83). Browser acceptance open.

## Notes

WHAT EXISTS, read in the code 5 Nov 2026: the history line (api _derived_line, kept per file signature as history-line-1) carries the first message as its preview, which the page shows whole as the line's title (app.js historyChatRow); the understanding (research v13 on) marks the client among its parties.
PIECES: titles (a new core module: the model's title and code's mechanical check), conversation (the title kept beside the conversation, on the running turn's own versions), turn (the title asked for once the understanding is known, beside the research, never holding the answer up), composition (the title written on the turn's model port, metered as any call), api (the history line carries the title - its kept lines read again), app.js (the line shows the title, the first message on hover).

## Column 7

BUILT 5 Nov 2026 (pushed; NOT applied):
43a (titles, a new core module declared in the source layout; reasoning; conversation): the model writes the title from the advocate's messages and, where NM has understood the matter, its parties (the client marked), disputes and summary - nothing else - in a loop of its own: think, write, check against what it was given, correct; code checks one line, not empty, at most ten words, and asks once more, saying why, where the first falls short; a failure leaves no title. Kept beside the conversation with whether it was written from an understanding of the matter.
43b (turn, composition): asked once the matter is understood, where the conversation has no title (or one written before any matter was understood), beside the research on the turn's own model port - metered as any call, never holding the answer up (a finished answer waits at most 60 s for it) - and saved on the turn's own versions.
43c (api, app.js): the history line carries the title (its kept lines read again); each line shows it, or until there is one the first message's first ten words, the first message itself on hover.
TESTS: tests/test_conversation_titles.py (7), tests/js/history_titles.mjs; the tests of the turn, the served turn, the effort table, the history and the layout pass (410 in 21 files, one page test failing as on the earlier code). Not run: a paid run of the title on real matters - its wording is unmeasured until the next message, or a run on the owner's word for the conversations saved before.
BUILT 5 Nov 2026 (pushed; NOT applied):
43d (turn, conversation, api, app.js, app.css; D84): the title once, at the conversation's beginning, from when its first message is sent - an empty heading until NM names it, then as named; NM never writes it again (the second writing of Claude's proposal (a) removed); the page reads it when the turn's saved work moves on - the title's save says so - and after an answer, by a small route that reads the saved file alone.
43e (operations/title_conversations.py; D83): the operator's run - each untitled conversation of an account titled with one short call on the account's own AI permission and allowance, metered as any call; refuses to start while an answer is being worked on; prints counts only.
RUN 5 Nov 2026 on the owner's word ("1 - Yes"), on the owner's account (the other four conversations in the store are test accounts'): 13 conversations, 13 titled, 14 calls - one title was over ten words and was asked for again - USD 0.0028 (usage record); titles of 4 to 10 words. Read by Claude, not recorded here: each names the matter apt and short; where the older understanding had not marked the client, a title may lead with another party's name (it never calls them the client).
TESTS: test_conversation_titles.py (9), tests/js/history_titles.mjs; page tests all pass but register_steps and render_turn_partition (failing on the earlier code too). Not run: the browser journeys (their browser is not installed here).
APPLIED 5 Nov 2026, 13:50 IST (owner: "apply"), with AN.39's reading-pane fix. FAULT IN THE APPLY: 43a declared the titles module as core without moving the layout's expected count of core modules (34 to 35), so the layout check refused and every page answered with an error from about 13:50 to 13:54 IST, when the corrected count (89f2c799) was put live; one further restart at 13:55 when its test was written into the checkout. No answer was being worked on (the store and the server's in-flight count checked first). A test now loads the shipped layout as the app does (it fails on the earlier count); the layout tests before checked only fixtures. After: every page and the reading pane's script served; all 17 saved conversations (21 turns) reopened read-only, none unreadable.
