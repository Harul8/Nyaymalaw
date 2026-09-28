# Journey-first project structure

This is a navigation and ownership map, not an implementation or acceptance
verdict. Before Build in `Nyaymalaw_Implementation_Plan.xlsx` still owns the
requirements. Existing code is arranged for review in journey order; an empty or
small phase does not prove its requirements are complete.

## Start here

```text
Nyaymalaw/
  nm/
    app/              compose, serve and launch the application
    arrive/           account, registration, identity and access
    open_matter/      opening, screens, intake and media admission
    legal_brain/
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

Smaller journey folders are flat. Legal brain is the bounded exception: eight
shallow capability folders plus `common/`, all flat inside. Each README indexes
the real files by responsibility.
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
| 03 — [Legal brain](../nm/legal_brain/README.md) | `understand/route.py`, `retrieve/search_authority.py`, `reason/proof.py`, `procedure/limitation.py`, `verify/verifier.py`, `communicate/preview_display.py`, `orchestrate/controlled_brain.py` |
| 04 — [Work the file](../nm/work_the_file/README.md) | `casefile.py`, `file_mutation.py`, `dispute_agenda.py`, `deadlines.py`, `summary.py` |
| 05 — [Advise](../nm/advise/README.md) | `advice_contracts.py`, `options.py`, `reassessment.py`, `relief.py` |
| 06 — [Act](../nm/act/README.md) | `action.py`, `drafting.py`, `hearing.py` |
| 07 — [Carry](../nm/carry/README.md) | `handover.py`, `service.py` |
| 08 — [Close](../nm/close/README.md) | `closure_contracts.py`, `retention.py`, `retention_contracts.py` |
| 09 — [Leave](../nm/leave/README.md) | `sign_out.py`; served logout and cookie removal remain in `app/api.py` |

The legal brain is grouped by responsibility, not by a fixed cognitive sequence.
Its [03.00–03.08 reading map](../nm/legal_brain/README.md) begins with shared
guidance, then follows understanding, retrieval, reasoning, procedure,
verification, communication, orchestration and evaluation. The index gives
actual per-folder populations and each capability README lists every file with
its purpose. Descriptive filenames distinguish contracts, ports, adapters,
native source owners, reasoning services and actual tool entry points.

Common files stay in [legal_brain/common](../nm/legal_brain/common/README.md) only
when they genuinely serve multiple capabilities. Capability-specific contracts
are not moved into a generic contracts folder, and there is no parallel tool dump.
The legacy turn path remains `legal_brain/orchestrate/turn.py`;
`legal_brain/orchestrate/controlled_brain.py` is not silently substituted for every
client path by reorganising source.

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
in `legal_brain/retrieve/corpus_evidence.py`, but its original raw bytes are not in the
checkpoint. Do not describe the checkpoint as a complete original-source backup
or silently reconstruct that file to certify baseline tests. Retired empty
package shells and caches are kept
under `.nm/reorganisation/retired/`, not deleted. The corpus junction, private
matter data, credentials and budget ledgers stay in their original locations.
