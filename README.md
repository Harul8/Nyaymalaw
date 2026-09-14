# Nyaymalaw

Software for practising advocates in India, designed to support the quality of
expert counsel's work. The advocate briefs NM, NM tests the file and offers a
considered view, and the responsible advocate reviews it. NM does not replace
professional responsibility or acquire authority to act by recommending a step.

**The original baseline started with documents and no code.** The repository
now contains an implementation; current coverage and proof are recorded in
the backlog, not inferred from this introduction. A previous
build reached 217 stories and 28 behavioural tenets and produced conversations
that were mechanically correct and professionally poor — asking a client who had
said *"yesterday"* for the date twice, dropping an assault into a possession
cause, and analysing a twelve-year limitation on a trespass a day old. Every
structural gate passed on that transcript. The specifications survive; the code
is being developed against a definition of done that the transcript would
have failed. Start with the [current delivery plan](docs/PLAN.md).

---

## The authority chain

Read in this order. Each is bound by the one above it.

| | |
|---|---|
| [PRD](docs/Nyaymalaw_PRD.docx), authored in `assurance/specification/prd/` | Intended features and professional behaviour; regenerate the document and machine-readable feature contracts together |
| [Current plan](docs/PLAN.md) and [`docs/backlog/`](docs/backlog/) | Journey contracts, professional standards, waves, release profiles, current implementation and evidence |
| [End-to-end workbook](docs/Nyaymalaw_End_to_End_Project_Plan.xlsx) | Generated reader view; never an independent status editor |
| [Build guide](docs/BUILD_GUIDE.md) | Four proportionate playbooks: Start, Build, Test and Sign-off |
| [Baseline](docs/BASELINE.md), [defect shapes](docs/DEFECT_SHAPES.md), [golden set](docs/GOLDEN_SET.md) | Measured coverage, known failure mechanisms and evaluation design; check the stated date and scope |

`development_environment/archives/` preserves the previous specification, journey, architecture,
defect register and plan as historical evidence, not current authority.
`docs/Nyaymalaw_Project_Plan.xlsx` similarly preserves the original slice
baseline; the current W0–W7 plan is maintained in the registries.

---

## What "done" means here

Not that the code looks right, and not that a structural property holds. A stage
is done when a real conversation passes its rubric:

1. it passes **standalone** — the floor on every turn, plus the stage's own
   DOES / CARRIES / NEVER items;
2. the **journey portfolio** passes — canonical, outage, conflict, emergency,
   restart and non-matter journeys, with **no hand-authored inter-stage state**:
   every stage receives what the preceding served interaction actually produced;
3. close only the evidenced scope. Independent foundation work may proceed;
   a dependent feature still needs its integrated journey proof. Deployment
   requires its own environment-specific release conditions and approval.

Structural checks — layering, exception discipline, dead-guard detection — are a
**linter**. They are necessary and they are not the bar. Every one of them passed
on the transcript that caused this rewrite.

See the [current plan](docs/PLAN.md) and [sign-off playbook](docs/playbooks/SIGN_OFF_A_CHANGE.md).

---

## Repository layout

| Folder | Holds |
|---|---|
| `backend/` | The advocate service. `backend/nm/` is the Python package `nm` (domain, ports, core, adapters, knowledge, edge, bootstrap); `backend/operations/` holds commands a person runs against the live service — enrol, invite, professional approval, re-key, store migration |
| `frontend/` | The advocate UI the backend mounts at `/` |
| `pipeline/` | The end-to-end legal-knowledge pipeline, run as offline jobs: `acquisition/` → `indexing/` → `quality/`, and the curated Act manifest the server reads |
| `assurance/` | How production is proven and permitted: `gate/` (the per-task gate), `journeys/` (served and browser runs), `control_plane/` (backlog, evidence, release obligations, the plan view), `hooks/`, `specification/` (PRD source and generated specs) and `common/`, which declares these homes once |
| `docs/` | Live documents and the delivery registries |
| `tests/` | The whole verification suite |
| `development_environment/` | Archives, dated reviews, one-off and developer tooling, earlier worktrees — kept, not shipped. See its README |

The package is not installed into the interpreter, so a worktree never imports
another checkout's code. Tests set the path through `pyproject.toml`; scripts
put the repository root and `backend/` on the path themselves; `start.ps1` sets
`PYTHONPATH` for the server it starts. Run the gate from the root with
`python assurance/gate/check.py`, and install the hooks by path with
`git config core.hooksPath assurance/hooks`.

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

The old B-164 report inferred incomplete Acts from one lookup path. Later
analysis found that coverage must reconcile every store and identifier; one
thin copy is not proof that the corpus lacks the provision. Read the current
[measured baseline](docs/BASELINE.md) and distinguish not held, held but not
found, and not assessed. Coverage must be stated before it is relied on.
