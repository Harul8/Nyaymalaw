# Journey-first project structure

This is a navigation and ownership map, not an implementation or acceptance
verdict. The **Advocate build plan** sheet of `Nyaymalaw_Implementation_Plan.xlsx`
is the work queue and holds the owner's decisions; the **legal brain** sheet holds
capability intent (owner decision, 10 October 2026). Before Build and the
Implementation Plan sheet's LB rows are history. Existing code is arranged for
review in journey order; an empty or small phase does not prove its requirements
are complete.

## The served brain today: none, while the core engine is built

On 10 October 2026 the owner archived the brain that was being served and asked for
a clean-slate core engine built from the Advocate build plan (decision P9). Until
the core engine's turn ships, the application serves accounts, sessions and the
workspace, and **conversations are paused**: `POST /api/turn` answers with a plain
notice and saves nothing, and every earlier conversation and matter is kept and
listed as history.

| Folder | State |
|---|---|
| `nm/core_engine/` | The new engine under active SEQ.1–SEQ.9 construction. Retains citation and retrieval helpers; `conversation.py` owns the new exact transcript and atomic receipt contract. No turn is served yet. The private M1 candidate supplies reviewed reference ideas only. |
| `nm/Archives/brain/` | The brain served until 10 October 2026. Not the current turn engine; preserved for historical work |
| `nm/Archives/legal_brain/` | The earlier brain. Not the current turn engine; retained corpus tools and application modules still import some helpers |
| `development_environment/archives/tests-for-archived-brains/` | Tests that guarded the archived brains, kept for reference; not collected |

Citation, provision and search-token patterns have one owner,
`nm/shared/citation_contracts.py`.

Planning custody and the exact retained/moved tooling inventory are recorded in
[the 10 October archive map](../development_environment/archives/planning-20261010/README.md).
The old PRD, registry and generated-plan paths remain where compatibility tools
still read them; they no longer own new work. Archived prompt experiments are
reference files, not supported launch commands for the current engine.

Current implementation priority is SEQ.1-SEQ.9 on Advocate build plan: core turn
ownership/context/persistence, exact case and statute identity, retrieval,
grounded response preparation and source reading, sustained matter work,
documents/summaries, checked computations/drafting, audio transcription, then
later practice and closure. The earlier M1 checkpoint remains private reference
work. The owner resumed implementation on 10 October, with a shared $5 API
development cap; this does not by itself activate the served turn.

`work_the_file/projections_api.py` retains historical independent read helpers.
Its former board function is explicitly retired and cannot return an empty
success. A new matter-board contract belongs to SEQ.5; restoring removed brain
imports is not an activation path.

## Start here

```text
Nyaymalaw/
  nm/
    app/              compose, serve and launch the application
    arrive/           account, registration, identity and access
    open_matter/      opening, screens, intake and media admission
    core_engine/      the new engine, being built: citations (E1) and retrieval (E2) so far
    Archives/brain/   the brain served until 10 Oct 2026, reference only
    Archives/legal_brain/   earlier brain; some corpus/application helpers remain dependencies
      understand/     message intent, context, party/posture and dispute binding
      retrieve/       held law, sources, searches, citations and legal coverage
      reason/         proof, theories, adverse material and source-backed needs
      procedure/      procedural conditions and conditional calculations
      verify/         grounding, independent checks and publication boundaries
      communicate/    responses, references, workspace and safe progress
      orchestrate/    reasoning loops, delegation, tools and continuation
      evaluate/       private evaluations, execution capture and replay
      common/         single shared guidance, read and citation owners
    work_the_file/    facts, chronology, disputes, requirements and deadlines
    advise/           recommendations, options, decisions and reassessment
    act/              permitted actions, drafting and hearing preparation
    carry/            service and handover
    close/            closure, retention and erasure contracts
    leave/            session termination
    shared/           security, models, storage and common contracts
    source_layout.json
  operations/         named human-run administrative commands
  pipeline/           named offline acquisition, indexing and quality jobs
  assurance/          gate, journeys, control plane, hooks and spec generators
  tests/              existing cross-phase, regression and invariant suite
  docs/               requirements, workbook, blueprint, guides and records
  development_environment/  preserved reviews, archives and developer tools
  legal_database/     existing external corpus junction; not moved or committed
  .nm/                private runtime data and local evaluation records
```

Journey folders, including `core_engine/`, are flat. The archived earlier
brain is the one exception: eight shallow capability folders plus `common/`, all
flat inside. Each README indexes the real files by responsibility.
There is no second application under `backend/` and no separate UI code tree.
Assurance keeps its existing purposeful gate/journey/control-plane homes: those
are build controls, not user-journey stages. Tests remain shared so existing
cross-phase protections are not split or quietly dropped.

## Numbered review map: the advocate's order

These numbers guide review; the physical folder names and imports are unchanged.
An advocate can revisit earlier stages, and legal reasoning itself is iterative.

| Review position and phase | Main owners to read first |
|---|---|
| 01 — [Arrive](../nm/arrive/README.md) | `store_directory.py`, `store_pending_accounts.py`, `professional_access.py`; account routes currently remain in `app/api.py` |
| 02 — [Open a matter](../nm/open_matter/README.md) | `opening_contracts.py`, `commission_contracts.py`, `screens.py`, `intake.py`, `quarantine.py`, `document_permission.py` |
| 03 — Legal brain (being rebuilt in `nm/core_engine/`) | `citations.py`, `retrieval.py`; `nm/Archives/brain/` and the [earlier brain](../nm/Archives/legal_brain/README.md) are reference only |
| 04 — [Work the file](../nm/work_the_file/README.md) | `casefile.py`, `file_mutation.py`, `dispute_agenda.py`, `deadlines.py`, `summary.py` |
| 05 — [Advise](../nm/advise/README.md) | `advice_contracts.py`, `options.py`, `reassessment.py`, `relief.py` |
| 06 — [Act](../nm/act/README.md) | `action.py`, `drafting.py`, `hearing.py` |
| 07 — [Carry](../nm/carry/README.md) | `handover.py`, `service.py` |
| 08 — [Close](../nm/close/README.md) | `closure_contracts.py`, `retention.py`, `retention_contracts.py` |
| 09 — [Leave](../nm/leave/README.md) | `sign_out.py`; served logout and cookie removal remain in `app/api.py` |

The rest of this section describes the EARLIER brain, kept for reference. It is
grouped by responsibility, not by a fixed cognitive sequence.
Its [03.00–03.08 reading map](../nm/Archives/legal_brain/README.md) begins with shared
guidance, then follows understanding, retrieval, reasoning, procedure,
verification, communication, orchestration and evaluation. The index gives
actual per-folder populations and each capability README lists every file with
its purpose. Descriptive filenames distinguish contracts, ports, adapters,
native source owners, reasoning services and actual tool entry points.

Common files stay in [legal_brain/common](../nm/Archives/legal_brain/common/README.md) only
when they genuinely serve multiple capabilities. Capability-specific contracts
are not moved into a generic contracts folder, and there is no parallel tool dump.
The historical turn lives at `nm/Archives/legal_brain/orchestrate/turn.py`;
`controlled_brain.py` beside it is also historical. Neither is a replacement for
the current core-engine turn merely because an old tool still imports a helper.

## Naming and boundaries

- `*_contracts.py`: domain records and invariants.
- `*_port.py`: interfaces consumed through dependency injection.
- `*_sources.py`: native knowledge-source interpretation and lookup owners.
- `*_adapter.py`, `store_*`, `model_*`, `mail_*`, `speech_*`: concrete boundaries.
- `*_api.py`: HTTP entry points; `app/api.py` still owns the shared route shell.
- `tool_<registered_name>.py`: the actual definition/handler entry point for one
  model-facing tool, including child-only tools where applicable.

Factories still compose tools into the existing registries. Files are not
automatically granted permission merely because their names start with `tool_`.
Shared mutation, grounding and permission services remain single owners; a tool
file delegates to them rather than cloning their implementation. Human commands
are not renamed as model tools and are never admitted by model-file discovery.

`app/api.py` and `app/app.js` retain their cross-phase shells. Splitting these
large controllers is separate behavioural work, not hidden in this migration.
The co-located UI assets and exact routes are listed by the owning phase index.
The browser receives only the closed asset map in `nm/source_layout.json`.

## Architecture, evidence and safe maintenance

The role map distinguishes domain, ports, core, knowledge, adapters, bootstrap,
edge and infrastructure regardless of physical folder. The existing import
matrix remains enforced by `assurance/gate/layercheck.py`; a journey-to-journey
import is permitted only if its semantic dependency direction is permitted.
Whole-product sweeps use the physical source population and explicit roles,
never a vanished `core/` folder or a hand-picked subset that can pass vacuously.

`assurance/common/journey_layout.json` records the initial journey migration's
original identities and roles. `assurance/common/legal_brain_layout.json` records
the later legal-brain substage moves. `nm/source_layout.json` owns the actual current
module and browser-asset destinations; the historical manifests are not live
import aliases. Their pre-move hashes are custody information, not fresh passing
evidence. Existing result artifacts are not relabelled as passing
against renamed code. Generated workbook sources and historical evidence retain
their own reconciliation and freshness checks.

Run from this checkout's root. `start.ps1` now starts `nm.app.main`; the module
entry point is also `python -m nm.app.main`. No new model-processing approval,
budget, data-sharing grant or legal sign-off is created by reorganisation.

The pre-move source checkpoint is local at `.nm/reorganisation/originals/`.
Its initial evidence-directory filter accidentally omitted the original
`adapters/evidence/corpus.py`; that implementation was moved intact and remains
in `nm/Archives/legal_brain/retrieve/corpus_evidence.py`, but its original raw bytes are not in the
checkpoint. Do not describe the checkpoint as a complete original-source backup
or silently reconstruct that file to certify baseline tests. Retired empty
package shells and caches are kept
under `.nm/reorganisation/retired/`, not deleted. The corpus junction, private
matter data, credentials and budget ledgers stay in their original locations.
