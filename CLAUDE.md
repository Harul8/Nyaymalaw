# Working on Nyaymalaw

This repository begins with documents and no code. What follows is carried
forward from a build that reached 217 stories and was then deleted — not the
code, which was the part that failed, but the rules that were learned by paying
for them. Every one exists because the same mistake recurred and cost real time.

---

## The authority chain

**Live documents — these bind, in this order.**

| | |
|---|---|
| `docs/Nyaymalaw_PRD.docx` | **The specification, and the source of truth.** Code is the verified build output. Organised on the JOURNEY axis, not by topic, so a slice of work is a contiguous cut. Every feature carries DOES / NEVER / PRODUCES / EVAL — a feature that cannot fill all four goes to the parking list, not into the build |
| `docs/Nyaymalaw_Project_Plan.xlsx` | Ten vertical slices over 26 weeks, 53 tasks, 56 evals, the cumulative-regression rule, the weekly error-analysis ritual, and the measured baseline |
| `docs/BASELINE.md` | What the corpus actually holds, **measured**. Standing product decisions about coverage. No claim about the corpus is made without checking here first |
| `docs/DEFECT_SHAPES.md` | The eleven shapes distilled from 164 reproduced defects, each with the check that refuses it. **Read before designing any control** |
| `docs/GOLDEN_SET.md` | **25 conversations** on verified corpus authority — 31 anchors, 42 provisions, all read back. Tagged by suite, tier, area and **earliest slice**, so a run is a filter (`smoke` every commit, `slice-N` at a slice close, `full` on approval) rather than all 25 every time |

**Archived — reference, not authority.** `docs/Archives/` holds the previous
build's specifications: `PRD.md` (28 advocate tenets in D16), `JOURNEY.md` (the
journey and its rubric), `GOLDEN_SCENARIOS.md`, `ARCHITECTURE.md`,
`DEFECT_REGISTER.md` (all 164 entries in full), `BACKLOG.md`, `NM_Build_Plan.xlsx`.

They are **mined, never reinstated wholesale.** The rule for moving something
from `Archives/` into a live document: it comes with the check that makes it
enforceable, or it stays archived. The previous build's failure was not bad
rules — it was a hundred good rules with no runner, so they became aspirations.
A rule you cannot run is not a requirement.

**And every measured claim in `Archives/` is re-measured before it is relied
on.** Three of them were checked on 29 August 2026 and were wrong — see
`docs/BASELINE.md` §"What the archive got wrong".

---

## What "done" means, and what it does not

**A tenet is not done because the code looks right, and not because a structural
property holds.** The previous build had twelve mechanically-checked properties —
persisted, survives restart, cannot be bypassed, has a production caller — and
every one of them passed on a transcript where the product asked a client who
had said *"yesterday"* for the date twice, dropped an assault into a possession
cause, and analysed a twelve-year limitation on a trespass a day old.

**The twelve measured the plumbing. The client drinks the water.**

So the definition of done is `docs/Archives/JOURNEY.md` §5: a stage passes its own rubric
standalone, then the journey portfolio passes end to end with no hand-authored
inter-stage state. Structural checks remain, as a **linter**. They are necessary
and they are not the bar.

---

## Before any code change

### 1. Generalised fixes only — never scenario-specific patches
The test: **can you state the fix without naming the specific Act, section,
case, atom type, or phrase that exposed it?** If not, it is a patch, and the
next unseen input fails the same way.

Worked example worth keeping: an unretrievable Schedule Article looked like a
missing entry in an atom-priors table. The real defect was that `table.get(kind,
0.0)` made *any* unlisted atom type score worse than every listed one. One is a
patch that helps one atom type; the other fixes every atom type that will ever
exist. Prove it by **deleting the patch and re-measuring** — if the number holds,
the fix was general.

### 2. Every fix lands with an invariant test that states the RULE
Not the scenario. The test is what prevents the regression; the fix alone does
not. A test that asserts current behaviour is not an invariant — roughly fifteen
had to be rewritten in one session, **including one that asserted the very defect
it was meant to catch**. When a test breaks on a change, decide which of the two
was wrong before touching either.

### 3. Measure before diagnosing, and say which it is
A cause that has been measured and a cause that sounds right are different
things. Three confident diagnoses in a row were wrong on one retrieval gap, and
each was excluded only by instrumenting the pipeline stage by stage. **Never
report a hypothesis in the voice of a finding.**

### 4. Ask what refuses the second copy
The question is not "where is the other copy" but **"what makes a second copy
impossible?"** A prompt system with two owners meant a change described as
"global" landed in half the product, and it bit twice. If nothing structurally
refuses the duplicate, that is the defect — not the duplicate.

### 5. Renames must be swept, and pyflakes is not enough
A rename left a live call site that raised `NameError` on every matter for
weeks. A conditionally-assigned local crashed every advising turn.

```bash
python -m pylint --disable=all --enable=E0601,E0606 --score=n <package>
```

### 6. A broad `except` must not hide a bug
Failing open is usually right, but `except Exception` that logs a warning made a
`NameError` look like a model failure and silently suppressed a whole feature.
Catch programming errors separately and log them at ERROR with a traceback.

### 7. Verify on the bytes, not the return value
40/40 offline passed while every served turn crashed. **Every defect the first
external review found lived between a correct module and the served path.** A
guard that is right in the core and wrong in the composition root is not a guard.

### 8. An absent input must never read as success
The single most repeated defect, in four separate controls: a screen that could
not run returned the shape of a clean result. Three states, always — held, not
held, **not assessed** — and the third must be visible in the output, not only
in the type.

---

## Standing constraints

- **Never run the golden or e2e evals without explicit per-run approval**,
  including targeted re-runs. One approval covers a bounded batch, not an
  open-ended licence.
- **Never auto-run long pipeline steps** — train, features, predict, backtest,
  index builds. Report and stop; the user runs these.
- **Ask before destructive or irreversible actions.** Deleting corpus rows
  counts. Removing a junction with `Remove-Item` can recurse into the target —
  use `cmd /c rmdir`, which removes the reparse point only.
- Routine model calls use the cheap tier; reserve the expensive one for where it
  changes the answer.
- Do not summarise at the end of a response, and do not narrate before acting.

---

## The previous build — `C:/Users/rahul/Agentified NM`

**No code comes from there. Not a file, not a function, not a pattern.**
That tree is the build that reached 217 stories and produced advice an
advocate could not use. Importing any of it reintroduces the assumptions
that failed, and they are not obvious on inspection — that is what made
them expensive the first time.

**Data and measurements outside `legal_database/` may be used.** Two
artefacts were surveyed on 29 August 2026 and both were declined:

| Artefact | Verdict |
|---|---|
| `.nm-artefacts/dense/` — 437MB, 284,447 provisions | **REFUSED.** Built with `sentence-transformers/all-MiniLM-L6-v2` at **384 dimensions**; this product queries with `text-embedding-3-large`. Querying an index across embedding models does not error — it returns plausible, confidently wrong neighbours, and every answer downstream inherits that silently |
| `.nm-artefacts/provisions.json` — 170MB, 292,986 provisions | **NOT TAKEN.** It is a re-extraction of the same source `chunks.db` already serves. Adding a fourth store of one dataset is the "three stores, three answers" defect, not a fix for it |

**The dense index is only knowable as unusable because it shipped an
`identity.json`.** That is the entire argument for defect shape S11, and it
is now enforced by `nm/knowledge/artefact.py` — using that real artefact as
the counterexample its test must reject, because a synthetic fixture would
prove only that the check compiles.

---

## The corpus

`legal_database/` is **22GB, gitignored, and attached as a directory junction**
(see README). It is scoped to **Telangana and the Union of India** — an answer
about Kerala law out of it is confidently wrong and nothing downstream catches
that.

**Two measured traps, both the same shape — a wrong lookup that answers
confidently:**

1. **Search the right index.** `case_name` holds party names, so a subject
   search against it returns zero and zero reads exactly like "not in the
   corpus". Bail returned **0** by name across all 33,791 cases and **1,452**
   against the summaries. Limitation Act Articles are `schedule_article` atoms
   in the chunks layer, absent from parents. **A zero result must name the index
   it came from** (`B-163`).

2. **THREE STORES, THREE ANSWERS, NONE CANONICAL.** The same Act is held under
   two id conventions — `the_specific_relief_act_1963` (13 sections) and
   `UNION OF INDIA_1963_1_THE SPECIFIC RELIEF ACT, 1963` (**all 44**) — and
   `legal.db` is a third view that agrees with neither (Limitation Act: declares
   32, holds 169). **Query one store and you will report a gap that is not
   there.** This superseded `B-164`, which recorded "Acts are partially
   ingested" from the thin copy alone. **Never state coverage from one store.**
   Figures live in `docs/BASELINE.md`, measured, with the store named.

---

## Tooling

**Use the Write tool for any script containing escape sequences.** Heredocs
mangle `\n`, `\b` and `\uXXXX` — `\b` became a literal backspace and broke a
regex silently. This recurred four times in one session.

Git Bash converts Windows paths in arguments to native commands, which
corrupts `mklink` targets. Use the PowerShell tool for anything path-shaped.

---

## Pushing

All work goes to **`origin` → https://github.com/Harul8/Nyaymalaw**.

The corpus is gitignored and must stay that way — twelve files exceed GitHub's
100MB hard limit and one is 3.9GB. Never `git add -f` under `legal_database/`.

## The code graph — use it before scanning files

**Status, measured 29 August 2026.** Narrow scope with the graph, then read the
source. The graph may be stale or may not model a relationship; **when the graph
and the source disagree, the source wins**, and an empty graph result means
"not indexed" or "not statically visible", never "does not exist".

| | |
|---|---|
| Graph | **WORKING** — 84 nodes, 1,878 edges, 25 files, 7 Leiden communities |
| Semantic search (embeddings) | **NOT WORKING** — see below. Full-text search works and is used instead |
| MCP tools | **WORKING** after restart — `query_graph_tool`, `get_impact_radius_tool`, `detect_changes_tool`, `build_or_update_graph_tool`, `get_architecture_overview_tool` all verified |

```bash
code-review-graph update --brief                      # after edits; hooks also do this
code-review-graph search <term>                       # FTS over nodes
code-review-graph query callers_of <qualified_name>   # also callees_of, imports_of,
                                                      # importers_of, tests_for,
                                                      # children_of, inheritors_of,
                                                      # file_summary
code-review-graph impact --file <path>                # blast radius
code-review-graph dead-code                           # no callers / no test references
code-review-graph architecture                        # communities and cohesion
```

`query` refuses an ambiguous name and lists candidates rather than guessing —
re-run with the `qualified_name` it returns.

**`search_mode: "none"` MEANS THE SEARCH COULD NOT ANSWER — NOT THAT THE CODE
IS ABSENT.** Measured, both on the CLI and through `semantic_search_nodes_tool`:

| Query | mode | result |
|---|---|---|
| `implements` — matches a node NAME | `fts` | 2 nodes |
| `status inflation check ...` — a concept | **`none`** | **0 nodes** |

Without embeddings there is no conceptual search: FTS matches node names only,
and a natural-language query returns **zero**. **Zero here reads exactly like
"not in the codebase", which is defect shape S3** — the trap that has already
produced three false gaps in this project against the legal corpus.

*The rule: a `search_mode: "none"` result is "the graph could not answer", and
the next step is Grep, never a conclusion that the code does not exist.*

**Embeddings are deliberately deferred, not forgotten.** `--provider local`
crashes in the tool's venv (`OPENSSL_Uplink: no OPENSSL_Applink`) inside
`SentenceTransformer` model loading — a torch/OpenSSL DLL conflict, not a
code-review-graph defect, and it reproduces with the model already cached and
fully offline. Chasing it is the wrong trade: the declared stack is OpenAI, so
the fix is `code-review-graph embed --provider openai` once `NM_MODEL_API_KEY`
is set. Until then, FTS covers lookup by name and keyword.

**`igraph` and `jedi` are installed** into the tool venv, which removes two
degraded paths: community detection now runs Leiden rather than a file-based
fallback, and Python call resolution is enriched. Reinstalling the tool with
`--force` and a different extras list **drops the extras not named** — install
them together or they silently disappear.

---

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**This project has a knowledge graph. Start with the code-review-graph
MCP tools to narrow scope, then read the source.** The graph is cheaper than scanning files and
gives you structural context (callers, dependents, test coverage) that file search cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes_tool` or `query_graph_tool` instead of Grep
- **Understanding impact**: `get_impact_radius_tool` instead of manually tracing imports
- **Code review**: `detect_changes_tool` + `get_review_context_tool` instead of reading entire files
- **Finding relationships**: `query_graph_tool` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview_tool` + `list_communities_tool`

### Verify in the source

- Narrow scope with the graph, then read the source. Do not change code from graph output alone.
- For any non-trivial change, read the implementation and the relevant tests before concluding.
- Verify the exact source when touching behavior, database logic, migrations, retries, fallbacks,
  recovery, or compatibility code.
- When the graph and the source disagree, the source wins. The graph may be stale or may not
  model that relationship.
- An empty graph result can mean "not indexed" or "not statically visible", not "does not exist".

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes_tool` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context_tool` | Need source snippets for review — token-efficient |
| `get_impact_radius_tool` | Understanding blast radius of a change |
| `get_affected_flows_tool` | Finding which execution paths are impacted |
| `query_graph_tool` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes_tool` | Finding functions/classes by name or keyword |
| `get_architecture_overview_tool` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes_tool` for code review.
3. Use `get_affected_flows_tool` to understand impact.
4. Use `query_graph_tool` pattern="tests_for" to check coverage.
<!-- /code-review-graph MCP tools -->
