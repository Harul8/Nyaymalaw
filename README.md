# Nyaymalaw

An expert advocate, for practising advocates in India. The relationship is
instructing advocate to senior counsel: the advocate briefs NM, NM returns a
considered and committed view, and the advocate decides what to do with it.

**This repository starts with documents and no code, deliberately.** A previous
build reached 217 stories and 28 behavioural tenets and produced conversations
that were mechanically correct and professionally poor — asking a client who had
said *"yesterday"* for the date twice, dropping an assault into a possession
cause, and analysing a twelve-year limitation on a trespass a day old. Every
structural gate passed on that transcript. The specifications survive; the code
is being written again against a definition of done that the transcript would
have failed.

---

## The authority chain

Read in this order. Each is bound by the one above it.

| | |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | What the product is and what "good" means. **D16 holds the 28 advocate-behaviour tenets.** |
| [`docs/JOURNEY.md`](docs/JOURNEY.md) | The advocate's journey end to end, nine phases, and the three-layer rubric that closes each stage |
| [`docs/GOLDEN_SCENARIOS.md`](docs/GOLDEN_SCENARIOS.md) | Six conversations, each built on a real judgement, together forcing ~21 principles. The gold eval |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Design intent, carried forward for reference rather than as a commitment |
| [`docs/DEFECT_REGISTER.md`](docs/DEFECT_REGISTER.md) | **164 defects that were actually reproduced.** The part of the previous build worth keeping |
| [`docs/NM_Build_Plan.xlsx`](docs/NM_Build_Plan.xlsx) | Stories, tenets and registers |

`docs/reference/` describes the build being replaced. It is a measured record of
what that system did, not a design to follow.

---

## What "done" means here

Not that the code looks right, and not that a structural property holds. A stage
is done when a real conversation passes its rubric:

1. it passes **standalone** — the floor on every turn, plus the stage's own
   DOES / CARRIES / NEVER items;
2. the **journey portfolio** passes — canonical, outage, conflict, emergency,
   restart and non-matter journeys, with **no hand-authored inter-stage state**:
   every stage receives what the preceding served interaction actually produced;
3. only then does the next stage begin.

Structural checks — layering, exception discipline, dead-guard detection — are a
**linter**. They are necessary and they are not the bar. Every one of them passed
on the transcript that caused this rewrite.

See [`docs/JOURNEY.md`](docs/JOURNEY.md) §5.

---

## The corpus

`legal_database/` is **22GB and gitignored**. Twelve files exceed GitHub's 100MB
limit; `caselaws_v2.index` is 3.9GB on its own. It holds 33,791 judgements
(29,510 Supreme Court, 4,280 Andhra Pradesh High Court) and 1,600+ bare Acts,
scoped to **Telangana and the Union of India**.

Attach it as a directory junction rather than copying it:

```powershell
New-Item -ItemType Junction -Path legal_database -Target "<path to the corpus>"
```

**Known, and it matters (`B-164` in the register): Acts are partially ingested
and nothing reports the partiality.** The Specific Relief Act 1963 holds 13 of
44 sections; the Muslim Women (Protection of Rights on Divorce) Act 1986 holds
one section of seven; BNSS 2023 holds 162 of 531. An advocate asking about a
missing section gets nothing, and nothing-found is indistinguishable from
no-such-remedy. Coverage must be stated before it is relied on.
