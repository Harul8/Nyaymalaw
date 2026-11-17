# Where Nyaymalaw stands

*Proposed under D229 (plan AN.54), 17 Nov 2026, to live at `docs/CURRENT_STATE.md` once the owner accepts it. It holds the facts
that change - the branch, the models, the spending limits and the state of the build - so that CLAUDE.md can keep only the rules
that do not date. Correct it in the same commit as the change it records; the Advocate build plan stays the record of decisions
and evidence (P7), and where the two disagree the plan is checked first.*

As of 17 Nov 2026, evening.

## Branches and checkouts

| What | Where it is |
|---|---|
| Working branch | `redesigned-architecture` (the AN.48 redesign, from 9 Nov 2026). Every piece is committed and pushed here. `s0-foundations`, origin's default, is an ancestor of it and has not moved since; nothing has been merged back. |
| Hosting branch | `nyaymalaw-aws` (from 11 Nov 2026): the move to hosted machines, committed from a copy. The live checkout has never been switched to it. |
| Live checkout | `C:\Users\rahul\Nyaymalaw`, on `redesigned-architecture` at `23210d04` - applied on 17 Nov 2026 by the owner's word (D284). Never checked out, stashed or reset over a live file; new code reaches it only by the owner's word. |
| Build copy | `docs\NM-forensic-review` inside the live checkout: a checkout of its own on the same branch, where pieces are built and replayed before they are applied. It is ahead of the live checkout by the commits listed under "Built, not applied". |

## Servers

| Server | State |
|---|---|
| Pilot | Port 8000, `nm.app.main` from the live checkout, following the code on disk: an edit to `nm/` or `tests/` there restarts it and drops a turn in flight. Running on `23210d04`. |
| Development server | Port 8071 (`start.ps1`). Not started on the new build: its first start runs D241's sweeps on the development store and erases 26 papers of one account, received over 30 days ago and named by no conversation (D244). Starting it is the owner's call; a copy of both stores is kept in `.nm/backups`. |

## Models

| Step | Running code (`23210d04`) | Built, not applied |
|---|---|---|
| Writing the turn | The advocate's choice: 6 Luna (the default), Auto (Luna, moving a call to 6.1 Terra where the turn shows it needs it; AN.38), 6.1 Terra or 6.1 Sol | Two choices in plain words: 6 Luna for routine work (the default) and 6.1 Terra for complex matters (D270 as the owner decided it, D288); turns saved with Auto or Sol are shown as saved |
| Independent review | The chosen model runs every call of the turn, the review too (same-model review allowed on this installation) | 6.1 Terra reviews every turn whichever model wrote it (D289) |
| Embeddings | `text-embedding-3-large` | unchanged |

Code names the models (`nm/shared/model_config.py`), not the installation's settings. Prices per million tokens, input/output:
Luna $0.10/$0.50, Terra $1.00/$5.00, Sol $2.00/$10.00.

## Spending limits

- Product: no spending cap (P16); each advocate's allowance is granted by an operator and stops a turn when it is spent.
- Development: paid runs up to **$2 in all from 17 Nov 2026** (D283), for the runs it names. Spent: $1.529 - D198's live run
  $0.211, 49d's check $0.065 + $0.067, D200's measurement $0.665, the bounded live run of the finished build $0.521; about
  $0.47 left (plan AN.48 column 5 keeps the running total). Every other paid run needs the owner's word first.
- Earlier allowances (the $5 shared cap of 10 Oct 2026, its $1 for Luna-against-Sol comparisons, the 2 Nov and 17 Nov run
  allowances) are spent or superseded; they are recorded on the plan.

## The state of the build

What follows is a summary; each row of the plan holds the record, and `docs/proposed/D231/PIECES.md` lists every piece with a
status proposed from git.

- **Running (applied):** everything up to `23210d04` - AN.1-AN.47, AN.48's pieces 48a-48i, AN.49-AN.54 as far as built by the
  morning of 17 Nov, AN.57 57a (browser journeys on every push), AN.58 58a (the page's files sent compressed).
- **Built, not applied** (in the build copy, pushed; each replayed free against the recorded turn):
  - 49d corrected (D285, D286) and wired: new answers gather the case under headings (D291);
  - two models in plain words (D288) and Terra reviewing every turn (D289);
  - every message step by step unless it asks otherwise (D287, the owner's D269);
  - Search again offered at the stop, never done by itself (D282), with the step-record store's migration at first start;
  - the case account through the independent review (D290);
  - a finding that a piece misleads as a whole placed or said above it (D201).
- **Held back:** D291 and D290 are not to be applied until D293 is settled - the live run found the case account leaves out a
  requirement whose law rests on several passages even when every quotation is exact (AN.49).
- **Waiting on the owner:** applying the commits above; D293 (several passages of law for one requirement; touches the frozen
  board); the measured cost of Terra reviewing every turn (D289: about two to three times its estimate); D292 (the earlier-matter screens); D244 (the development server's first
  start); D259 (the contact details the public pages give); D232 (the engineer who reviews before launch, and the person to call
  when the server is down); D281 (the ten-matter run, once everything is ready); D229 and D231 themselves (these drafts).
- **Open:** browser acceptance of the redesign (D141); live semantic acceptance; the hosting itself (`nyaymalaw-aws`).
