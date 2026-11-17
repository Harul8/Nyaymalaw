# Where Nyaymalaw stands

*Proposed under D229 (plan AN.54), 17 Nov 2026, to live at `docs/CURRENT_STATE.md` once the owner accepts it. It holds the facts
that change - the branch, the models, the spending limits and the state of the build - so that CLAUDE.md can keep only the rules
that do not date. Correct it in the same commit as the change it records; the Advocate build plan stays the record of decisions
and evidence (P7), and where the two disagree the plan is checked first.*

As of 17 Nov 2026, night.

## Branches and checkouts

| What | Where it is |
|---|---|
| Working branch | `redesigned-architecture` (the AN.48 redesign, from 9 Nov 2026). Every piece is committed and pushed here. `s0-foundations`, origin's default, is an ancestor of it and has not moved since; nothing has been merged back. |
| Hosting branch | `nyaymalaw-aws` (from 11 Nov 2026): the move to hosted machines, committed from a copy. The live checkout has never been switched to it. |
| Live checkout | `C:\Users\rahul\Nyaymalaw`, on `redesigned-architecture` at the branch's tip - the code applied on 17 Nov 2026, night, by the owner's word (D295), at `694bc758`; later commits change only the plan and these drafts. Never checked out, stashed or reset over a live file; new code reaches it only by the owner's word. |
| Build copy | `docs\NM-forensic-review` inside the live checkout: a checkout of its own on the same branch, where pieces are built and replayed before they are applied. |

## Servers

| Server | State |
|---|---|
| Pilot | Port 8000, `nm.app.main` from the live checkout without following code (`operations/pilot.ps1`). Not running since the evening of 17 Nov 2026 (its window was closed during a start); started again by the owner's own launcher, it runs the applied build. |
| Development server | Port 8071 (`start.ps1`). Started by the owner at 14:45 on 17 Nov 2026 on `23210d04`; its first start ran D241's sweeps on the development store (D244). Not running now. |

A copy of both stores from before each apply is kept in `.nm/backups` (never committed).

## Models

| Step | Applied (`694bc758`) |
|---|---|
| Writing the turn | Two choices in plain words: 6 Luna for routine work (the default) and 6.1 Terra for complex matters (D270 as the owner decided it, D288); turns saved with Auto or Sol are shown as saved |
| Independent review | The model the turn is written on: Luna unless the advocate chose Terra (D294, which withdrew D289's fixed Terra reviewer on the live run's cost; the owner: "lets use Luna only, and use Terra sparringly in complex situtations that Luna may not handle properly") |
| Embeddings | `text-embedding-3-large` |

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

- **Applied:** everything up to `694bc758` - AN.1-AN.47, AN.48's pieces 48a-48i, AN.49 (49d corrected and wired: new answers
  gather the case under headings, D285, D286, D291; a requirement's law a list of passages, D293), AN.50-AN.54 as built, AN.51's
  D290 (the case account through the independent review), D201 and D294 (Luna only), AN.52's D282 (Search again offered at the
  stop, never by itself), AN.57 57a, AN.58 58a, D287 (step by step unless a message asks otherwise) and D288 (two models).
- **Built, not applied:** nothing.
- **Decided, not built:** D292 (the screens of a matter saved before conversations, with the Legal library, Home and
  Preparation screens, deleted with their skipped browser checks) - applied at the owner's next word once built and checked.
- **Waiting on the owner:** starting the pilot; D259 (the contact details the public pages give); D232 (the engineer who
  reviews before launch, and the person to call when the server is down); D281 (the ten-matter run, once everything is ready);
  D229 and D231 themselves (these drafts).
- **Open:** browser acceptance of the redesign (D141); live semantic acceptance - no served turn has yet made a gathered case,
  and whether the model splits a requirement's law into its passages under D293 is measured only by a live run; the hosting
  itself (`nyaymalaw-aws`).
