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
  operations/       the operator commands (enrol, invite, outbox, professional
                    approval, store migration, re-keying, titling old conversations,
                    usage) and the measurement of old against new search vectors
  pipeline/         the corpus jobs (Acts and judgments) and their inputs
```

`nm/app/main.py` is the entry point (`start.ps1` runs it). It reaches every module
under `nm/` except `Archives/` and two test doubles in `shared/`
(`model_scripted.py` and `model_replay.py`). Outside `nm/` the app reads three
files: `docs/blueprint/evaluations.json` (the media contract),
`docs/blueprint/processors.yaml` (the outbound-data inventory) and
`pipeline/instrument_copies.json`. The served app refuses to start if the Python
files under `nm/` (outside `Archives/`) differ from `nm/source_layout.json`, so a
new module is declared there in the same commit.

The Admin area (plan AN.46; owner decisions of 7 Nov 2026) is one page, `nm/app/admin.html`
with `admin.css` and `admin.js`, opened from the person menu in a tab of its own. It shows
usage, balance and consumption beside the account facts they belong to, diagnostics, the held
law's description, and who has done what - never a conversation, matter, file or record. There
is one sign-in, the workspace's. An account is an Advocate until an Admin sets its user type to Admin
on the Users page (the very first Admin is made with `operations/admin.py`), and the server's
settings (`NM_ADMINS="email:admin,email:view-only"`) may name admins too, at either level, which the
page does not change. The page and its three files are served only to admins (the one static
router's gate; a signed-out visit is sent to the sign-in, an advocate gets the 404 of a name that is
not there), the workspace's top bar shows an Admin button to an admin by itself, and every
`/api/admin/` address answers an advocate with the same 404.
`nm/app/admin_api.py` is the router (handed the edge's own sign-in and cross-site pieces, so it
imports nothing from `api.py`), `admin_views.py` builds each page from named allowed fields and
refuses a payload with a forbidden key, and `admin_changes.py` is the one path every change takes
(level, password given in this session, a one-line reason, a first and a second audit entry).
The Admin area has ports of its own, so the directory port the sign-in edge holds still cannot
list accounts: `nm/arrive/admin_port.py` names them, and `admin_directory.py` (accounts, sessions,
the suspension mark), `admin_usage.py`, `admin_turns.py`, `admin_checks.py`, `admin_library.py`
and `store_admin.py` carry them. Its own stores are `admin.sqlite` (the audit chain and the
password check) and `turn-events.sqlite` (one content-free line per finished turn, written by
`composition.run_turn`; `store_turn_events.py`). `admin_access.py` reads the settings' roster. Acts are
staged and read, free, from the Library page (`admin_staging.py`, which runs `pipeline/check_bare_acts.py`
on files copied into a folder of their own); the append itself stays the owner's offline job below,
run with the server stopped.

The corpus jobs in `pipeline/` build the stores the engine reads:
`fetch_india_code.py` fetches the Acts, `build_acts_v4.py` (with
`append_bare_acts.py`) builds the Act store and its indexes,
`embed_acts_wording.py` makes the Acts' vectors again from each passage's own
wording (the line that names it left out), `cut_judgments.py` cuts a judgment on the
court's own printed paragraphs and `build_judgments_v3.py` builds the judgment store
anew with it (each passage carrying its court, the judgment's own citations, the cases
and the provisions it cites, and its kind), `classify_judgment_paragraphs.py` names the
kinds still unknown with a model (a paid run the owner limits and applies),
`record_retrieval_lineage.py` records what built the earlier indexes (each store built
since writes its own record), `build_identity_index.py` builds the case identity index,
and `instrument_copies.py` chooses the stored copy of each instrument. `manifest.yaml`
is the curated Act manifest and `act_aliases.json` the owner's list of the short forms
judgments use for an Act (only the aliases marked checked resolve a name).
`operations/compare_retrieval.py` puts composed legal questions to the Acts' earlier and
new vectors and reports the ranks, before the owner swaps. Each is an offline job run
deliberately, never automatically; a store changes what the search reads only at its
swap, with the server stopped.

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
