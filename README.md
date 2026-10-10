# Nyaymalaw

Software for practising advocates in India, designed to support the quality of
expert counsel's work. The advocate briefs NM, NM tests the file and offers a
considered view, and the responsible advocate reviews it. NM does not replace
professional responsibility or acquire authority to act by recommending a step.

**The original baseline started with documents and no code.** The repository
now contains an implementation; current scope and evidence are recorded in the
Advocate build plan worksheet, not inferred from this introduction. A previous
build reached 217 stories and 28 behavioural tenets and produced conversations
that were mechanically correct and professionally poor — asking a client who had
said *"yesterday"* for the date twice, dropping an assault into a possession
cause, and analysing a twelve-year limitation on a trespass a day old. Every
structural gate passed on that transcript. The specifications survive; the code
is being developed against a definition of done that the transcript would
have failed. Start with **Advocate build plan** in the
[implementation workbook](docs/Nyaymalaw_Implementation_Plan.xlsx).
The application currently starts with conversations paused. Citation and retrieval
helpers are retained in `nm/core_engine`; the unfinished M1 candidate is preserved
privately and is not served.

---

## The authority chain

The owner's current instructions govern scope. These records have distinct roles.

| | |
|---|---|
| [Implementation workbook](docs/Nyaymalaw_Implementation_Plan.xlsx), Advocate build plan | Current decisions, work queue, slice contracts, status, evidence and remaining work |
| Same workbook, legal brain | Linked capability intent and detail; older implementation notes are historical |
| [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md) | Standing safeguards and current working instructions |
| [Build guide](docs/BUILD_GUIDE.md) | Four proportionate playbooks: Start, Build, Test and Sign-off |
| [Baseline](docs/BASELINE.md), [defect shapes](docs/DEFECT_SHAPES.md), [golden set](docs/GOLDEN_SET.md) | Measured coverage, known failure mechanisms and evaluation design; check the stated date and scope |

`development_environment/archives/` preserves the previous specification, journey, architecture,
defect register and plan as historical evidence, not current authority.
The earlier PRD, PLAN.md, backlog registries and older workbooks are historical
planning inputs under P12. Some stay at their original paths because live tooling
still reads them. They do not decide the current build or certify the new engine.

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

See the Advocate build plan and [sign-off playbook](docs/playbooks/SIGN_OFF_A_CHANGE.md).

---

## Repository layout

| Folder | Holds |
|---|---|
| `nm/` | The advocate application, organised into shallow journey folders: Arrive, Open a matter, Legal brain, Work the file, Advise, Act, Carry, Close and Leave; `app/` wires and serves them, `shared/` owns common security and storage |
| `operations/` | Human-run administration commands: enrolment, invitation, professional approval, outbox, store migration and re-keying; these are not model tools |
| `pipeline/` | Flat, named offline legal-source acquisition, indexing and quality jobs, plus the curated Act manifest |
| `assurance/` | How production is proven and permitted: `gate/` (the per-task gate), `journeys/` (served and browser runs), `control_plane/` (backlog, evidence, release obligations, the plan view), `hooks/`, `specification/` (PRD source and generated specs) and `common/`, which declares these homes once |
| `docs/` | Current workbook and guidance, plus explicitly historical planning inputs retained for compatibility |
| `tests/` | Retained live safeguards; archived-brain tests are preserved separately and not collected |
| `development_environment/` | Archives, dated reviews, one-off and developer tooling, earlier worktrees — kept, not shipped. See its README |

Start with [the journey-first project map](docs/PROJECT_STRUCTURE.md), then the
README in the phase you want to review. Browser assets live beside their journey
owners; the server exposes only the explicitly approved browser files, never the
Python package. Each model tool has a `tool_<registered_name>.py` entry point.

The package is not installed into the interpreter, so a worktree never imports
another checkout's code. Tests set the path through `pyproject.toml`; scripts
put the repository root on the path themselves; `start.ps1` sets
`PYTHONPATH` for the server it starts. Run the gate from the root with
`python assurance/gate/check.py`, and install the hooks by path with
`git config core.hooksPath assurance/hooks`.

---

## The corpus

`legal_database/` is gitignored and contains large original and derived corpus
files. Use the dated [baseline](docs/BASELINE.md) and current source manifests
for measured counts and coverage; an older count or corpus label does not prove
legal applicability or currency. The product scope is Telangana and central law.

Attach it as a directory junction rather than copying it:

```powershell
New-Item -ItemType Junction -Path legal_database -Target "<path to the corpus>"
```

The old B-164 report inferred incomplete Acts from one lookup path. Later
analysis found that coverage must reconcile every store and identifier; one
thin copy is not proof that the corpus lacks the provision. Read the current
[measured baseline](docs/BASELINE.md) and distinguish not held, held but not
found, and not assessed. Coverage must be stated before it is relied on.
