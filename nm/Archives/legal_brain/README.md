# Legal brain

The legal brain is organised into eight shallow capability folders and one
shared-owner folder. This is navigation over implemented source, not a claim of
expert-quality acceptance. Before Build and current tests/evaluations govern that
claim.

## 03 — Choose the question you want to review

| Review position | Responsibility | Where to start | Implementation files | Browser assets |
|---|---|---|---:|---:|
| 03.00 | Shared guidance and contracts | [common/](common/README.md) | 11 | 0 |
| 03.01 | Understand the contribution | [understand/](understand/README.md) | 19 | 1 |
| 03.02 | Retrieve and inspect sources | [retrieve/](retrieve/README.md) | 48 | 0 |
| 03.03 | Assess disputes and possibilities | [reason/](reason/README.md) | 35 | 0 |
| 03.04 | Assess procedural conditions and calculations | [procedure/](procedure/README.md) | 42 | 0 |
| 03.05 | Check support and publication boundaries | [verify/](verify/README.md) | 17 | 0 |
| 03.06 | Explain and present checked work | [communicate/](communicate/README.md) | 10 | 4 |
| 03.07 | Run and coordinate bounded reasoning | [orchestrate/](orchestrate/README.md) | 21 | 0 |
| 03.08 | Measure and replay controlled execution | [evaluate/](evaluate/README.md) | 11 | 2 |

These numbers are reading positions, not Python package names or a runtime
pipeline. Each folder README indexes every physical implementation file and browser asset.
Each folder is flat; there are no further stage or layer folders. The root retains
only this index and [the package initializer](__init__.py).

## A reasoning loop, not a conveyor belt

These are reviewable responsibilities, not a fixed execution sequence. NM can
return to understanding, retrieval, assessment and verification as instructions,
facts, sources and permissions change. Orchestration owns that coordination;
evaluation measures it without becoming the normal-client approval path.

The legacy turn engine remains [orchestrate/turn.py](orchestrate/turn.py).
[orchestrate/controlled_brain.py](orchestrate/controlled_brain.py) is not silently
substituted for every client path by moving files. No evaluation grant, budget,
data-sharing permission or professional sign-off is created or renewed here.

## One owner, not copies

Genuinely shared guidance and contracts live in [common/](common/README.md).
Capability-specific contracts, ports, native source interpreters, adapters,
services and tool doors remain beside their capability and retain their distinct
architectural roles. Principles are authored once in
[LEGAL_BRAIN_PRINCIPLES.md](../../../docs/blueprint/LEGAL_BRAIN_PRINCIPLES.md) and
generated into [common/principles_generated.py](common/principles_generated.py).

Actual model-facing entry points retain `tool_<registered_name>.py` filenames.
The registry/factories remain explicit single owners under
[orchestrate/](orchestrate/README.md); files are not automatically admitted as
tools. Parent and child scope, metadata, grounding, permissions and native
services are unchanged. Child-only finish tools remain child-only beside their
research or opposition capability.

Case facts, corrections, recorded checklist answers and deadlines remain jointly
owned with [Work the file](../../work_the_file/README.md); recommendations with
[Advise](../../advise/README.md); provider/storage/security boundaries with
[Shared](../../shared/README.md). HTTP composition stays in [App](../../app/README.md).

See [the full project map](../../../docs/PROJECT_STRUCTURE.md) for journey ownership,
tooling, the explicit role map and historical migration records.
