# Project structure

This is a navigation map, not an implementation or acceptance verdict. The
**Advocate build plan** sheet of `Nyaymalaw_Implementation_Plan.xlsx` is the work
queue and holds the owner's decisions; the **legal brain** sheet holds capability
intent (owner decision, 10 October 2026).

On 19 October 2026 the owner had every tracked file the production pipeline does
not use deleted (decision P24): the archived engines and their tests, unconnected
modules in the journey folders, the old planning records and control plane, dated
reviews, and corpus jobs outside the Act-store build. They remain in Git history;
the last commit that holds them is `24d97355`.

## What production runs

```text
Nyaymalaw/
  nm/
    app/            compose, serve and launch the application, plus the browser page
    core_engine/    the engine: understanding, research, retrieval, citations,
                    grounded writing, independent review, rendering, the check at saving,
                    documents, checklist, limitation, calculation, voice, matter board
    arrive/         accounts, invitations, sessions and the mail outbox
    open_matter/    uploads, document isolation and text, media contracts, file scanning
    work_the_file/  the matter and loop-record contracts the engine still uses
    advise/         the answer, brief and released-turn receipt contracts
    leave/          sign-out
    shared/         model ports and adapters, budgets, storage and sealing, egress
                    policy, citation and gate contracts, the source layout
    Archives/legal_brain/  only the nine retrieval helpers and the citation
                    contracts that the Act-store corpus jobs import
    source_layout.json  every active module's role and the served browser assets
  operations/       the six operator commands (enrol, invite, outbox, professional
                    approval, store migration, re-keying)
  pipeline/         the Act-store corpus jobs and their inputs
```

`nm/app/main.py` is the entry point (`start.ps1` runs it). It reaches every module
under `nm/` except `Archives/` and two test doubles in `shared/`
(`model_scripted.py` and `model_replay.py`). Outside `nm/` the app reads three
files: `docs/blueprint/evaluations.json` (the media contract),
`docs/blueprint/processors.yaml` (the outbound-data inventory) and
`pipeline/instrument_copies.json`. The served app refuses to start if the Python
files under `nm/` (outside `Archives/`) differ from `nm/source_layout.json`, so a
new module is declared there in the same commit.

The corpus jobs in `pipeline/` build the stores the engine reads:
`fetch_india_code.py` fetches the Acts, `build_acts_v4.py` (with
`append_bare_acts.py`) builds the Act store and its indexes,
`record_retrieval_lineage.py` records what built the indexes,
`build_identity_index.py` builds the case identity index, and
`instrument_copies.py` chooses the stored copy of each instrument. `manifest.yaml`
is the curated Act manifest. Each is an offline job run deliberately, never
automatically.

## Around production

| Folder | Holds |
|---|---|
| `tests/` | Tests that exercise the production code, their shared setup (`conftest.py`), JavaScript checks of the browser code (`js/`), the sign-in feature files (`features/`) and one fixture |
| `assurance/` | The Git hooks that keep the code graph current (`hooks/`), the console helper the operator commands and corpus jobs use, and three test helpers: exact source segments, layout geometry, and the browser-journey harness |
| `development_environment/developer_tooling/` | The code-graph launcher (`crg_serve.ps1`, named in `.mcp.json`) and the vector refresh the hooks call |
| `docs/` | The plan workbook, the [build guide](BUILD_GUIDE.md) and its playbooks, this map, [BASELINE](BASELINE.md), [DEFECT_SHAPES](DEFECT_SHAPES.md), [GOLDEN_SET](GOLDEN_SET.md), [REVIEW_LINKS](REVIEW_LINKS.md), [LIMITATION_SCENARIOS](LIMITATION_SCENARIOS.md) and the two blueprint files the app reads |
| `legal_database/` | The corpus, a gitignored directory junction; never committed |
| `.nm/` | Private runtime data: matter store, keys, indexes, local evaluation records; never committed |

## Reading order

Read in the advocate's order: [Arrive](../nm/arrive/README.md),
[Open a matter](../nm/open_matter/README.md), the core engine
(`nm/core_engine/`), [Work the file](../nm/work_the_file/README.md),
[Advise](../nm/advise/README.md) and [Leave](../nm/leave/README.md).
[App](../nm/app/README.md) composes and serves them and [Shared](../nm/shared/README.md)
holds the common boundaries. Act, Carry and Close have no code today; SEQ.7–SEQ.9
build them afresh rather than reviving deleted modules.

Citation, provision-reference and frozen search-token patterns have one owner,
`nm/shared/citation_contracts.py`. Registered gates have one owner,
`nm/shared/gates_contracts.py`.

## Naming

- `*_contracts.py`: domain records and invariants.
- `*_port.py`: interfaces consumed through dependency injection.
- `*_adapter.py`, `store_*`, `model_*`, `mail_*`: concrete boundaries.
- `app/api.py` owns the shared route shell; `app/app.js` the browser controller.

Run from this checkout's root; the package is not installed into the interpreter.
