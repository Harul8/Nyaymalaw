# The conversation, end to end — as built

Companion to `ARCHITECTURE_AS_BUILT.md`, and derived the same way: **read out of
the code, not out of the plan.** Every stage below was taken from
`nm/app/consult.py::run` and the modules it calls. Where this document says
something is missing, that is a fact about the tree today, not a criticism of
the design.

**Why it is written this way round.** The D16 tenets are a checklist of
behaviours, not a path. Every defect found in this build's reviews lived
*between* tenets — a correct module and a served path that walked around it —
so the useful map is the one a message actually travels, with the joins visible.

A spec written before the code would have been worse than useless here: every
design written confidently in this build and not run was wrong somewhere only
measurement found — the urgency carry-forward rule, the reliance projection, the
claim that the candour lead carried no model text. A document derived from the
code cannot make that mistake, and the parts that are genuinely greenfield are
marked as such rather than imagined.

---

## One turn, as it runs

Fourteen stages, **eight places the turn can end**. The exits matter as much as
the stages: each one is a different answer, and each persists a different thing.

| # | Stage | What it decides | Persists | Can end the turn |
|---|---|---|---|---|
| 0 | *(before any stage)* | is the message empty | **nothing** | ✅ error |
| 1 | `reading the brief` | is this a matter at all | — | ✅ greeting |
| 2 | `checking for anything urgent` | AB-06 triage, carried forward over the file | `urgencies` | ✅ if the screen did not run |
| 3 | `screening for conflicts` | AB-03 parties → registry projection | `conflict` | ✅ if uncleared |
| 4 | `checking this is ours` | AB-02 competence, sticky | `competence` | ✅ if outside |
| 5 | `taking the account` | AB-07 propositions + knowledge basis | — | — |
| 6 | `what the client wants` | AB-08 aims and constraints | — | — |
| 7 | `retrieving the law` | scoped by cause; named provisions resolved | — | — |
| 8 | `working the file` | gates, gap queue, limitation | `limitation_*` | ✅ asks a question |
| — | *(no findings)* | nothing retrieved | — | ✅ says so |
| 9 | `mapping what must be proved` | AB-15 elements | — | — |
| 10 | `settling the theory` | AB-16 one sentence | — | — |
| 11 | `testing it against the other side` | AB-17 counter + response | — | — |
| 12 | `the difficult part` | AB-21 corrections + disagreements | — | — |
| 13 | `advising` | the draft, **buffered** | — | — |
| 14 | `checking it against our duty` | AB-01 screen | `duty_raised` | ✅ normal end |

**What the file carries between turns**, and therefore what makes turn 2
different from turn 1: `role`, `cause`, `conduct_on`, `limitation_article`,
`limitation_expires`, `turns`, `conflict`, `competence`, `engagement`,
`urgencies`, `duty_raised`. All of it survives a process restart, sealed.

**The order is load-bearing and was got wrong twice.** The emergency screen runs
before the conflict screen because D16.6 is prior to D16.3 — an advocate whose
client is being arrested tonight is not told to wait for a conflict check. The
substance is merged *after* the conflict screen, because merging first is how an
uncleared file came to hold a cause, a date and a role.

---

## Where the path is silent

These are the gaps a walk exposes that no single tenet owns. Ordered by where
they sit in the conversation rather than by tenet number, because that is the
order in which they block each other.

### A. The conversation cannot end

**Nothing in the tree decides that a matter is finished being discussed.** There
is no "ready to draft", no closure, no concluding turn — `run` answers, persists
and returns, and the next message starts the same fourteen stages again. Turn 40
looks exactly like turn 2.

This is the largest hole and it is upstream of drafting: drafting needs a
settled position to draft *from*, and nothing declares one settled.

### B. Nothing accumulates across turns except gates

The file carries the SCREENS. It does not carry the WORK: the theory, the proof
map, the account's propositions and the client's constraints are all computed
fresh each turn and thrown away. So:

* a proof map built on turn 3 is gone by turn 4;
* a theory the advocate accepted is re-derived, and may differ;
* AB-08's constraints have to be re-elicited from whatever the latest message
  happens to say.

`Conversation.conclusions` exists and holds four scalars, which is what AB-21's
correction path compares. Everything else is per-turn.

### C. The advocate cannot answer nm

Every human act nm requires has an endpoint or has nothing:

| Act | Surface |
|---|---|
| clear a conflict | `POST /matter/clearance` ✅ |
| record an engagement | `POST /matter/engagement` ✅ |
| release a competence limit | `competence.release` — **no endpoint** |
| resolve an urgency | `urgency.resolve` — **no endpoint** |
| override a duty finding | `duty.override` — **no endpoint** |
| record a decision | `decision.DecisionRecord` — **no endpoint, no caller** |

Four of six named human acts cannot be performed by a human.

### D. Drafting does not exist

AB-23 is `Not implemented`. There is a `nm/drafting` layer with a signature
boundary and no composer. Nothing turns a settled position into a document, and
nothing files one.

### E. The proof map cannot be trusted

AB-15's coverage gate is fed nothing, deliberately — nm has no independent
statement of what a cause requires, so the gate stays open and says so. That is
honest and it is not sufficient: a proof map whose elements come from the same
turn that placed them cannot support a conclusion.

---

## The build order this implies

Along the path, not by tenet number:

1. **Carry the work, not just the gates** (B). Everything downstream needs a
   position that survives a turn.
2. **The remaining human surfaces** (C). Four endpoints; each is small, and each
   turns an existing contract into something a person can actually do.
3. **A settled position, and an end to the conversation** (A). This is the new
   design work: what makes a matter ready, who says so, and what it means.
4. **Independent elements** (E), which is what makes a settled position mean
   anything.
5. **Drafting** (D), last, and the only part that is genuinely greenfield —
   so the only part that is specified before it is built rather than after.

**Each step re-runs the whole walk**, because the defects live at the joins and
a join cannot be tested until both sides exist. Closing a step and moving on is
what produced the two-owner defects this build keeps finding.
