# Working on Nyaymalaw

## Authority and work queue

Read AGENTS.md for standing build and release safeguards. The owner's current
instruction determines authorised scope. Core-engine implementation is paused;
planning and cleanup do not themselves authorise resuming M1 or paid runs.

Owner decisions P7 and P12 of 10 October 2026 establish these roles:

| Source | Current role |
|---|---|
| Advocate build plan in docs/Nyaymalaw_Implementation_Plan.xlsx | One work queue: decisions, slice contracts, current status, evidence, model-call impact and remaining work. Record decisions before dependent implementation. |
| legal brain in the same workbook | Linked capability intent and detail. Earlier status notes are historical. |
| AGENTS.md | Standing safeguards, prompt responsibilities, atomic changes and release rules. |
| docs/BUILD_GUIDE.md and docs/playbooks/ | Proportionate Start, Build, Test and Sign-off method. |
| docs/PROJECT_STRUCTURE.md | Code navigation. Verify actual source before changing behaviour. |
| docs/BASELINE.md, docs/DEFECT_SHAPES.md, docs/GOLDEN_SET.md | Dated corpus measurements, defect mechanisms and evaluation materials; check present applicability. |

Before Build, Implementation Plan LB rows, the earlier PRD/generated contracts,
backlog registries, PLAN.md and older plan workbooks are historical planning
inputs. They do not choose current work or certify its completion. Retain old
inputs where live corpus, storage, authentication or assurance tools depend on
them; record consumers in the archive map. Historical planning status does not
retire a still-relevant safety check or justify regenerating obsolete status.

For each slice, use its plan row: trigger, original inputs, admitted output,
decision owner, state effect, failure scope, bounded recovery and observable
outcome. Reuse fitting contracts explicitly. Create no parallel tracker.

## Current code and archive dependencies

The app starts with conversations paused. nm/app/api.py owns the authenticated
HTTP boundary, nm/app/composition.py composes services and nm/app/main.py
launches it. nm/core_engine/ currently holds citation and retrieval helpers;
no brain processes the served turn. Earlier conversations remain preserved.
M1's unfinished candidate is kept in the private checkpoint named in the plan.

nm/Archives/brain/ and nm/Archives/legal_brain/ contain reference engines.
Some archived modules remain dependencies of live corpus jobs and tooling.
Archived does not mean unused, safe to delete, or active on the served chat path.
Check the archive dependency map and actual imports before moving anything.

Before borrowing archived or Agentified NM code, tell the owner exactly what
will be reused, inspect its complete contract and validate current integration.
Do not reinstate a whole engine or infer that its tests protect new code.
Preserve unrelated edits, source documents and saved matters.

Citation, provision-reference and frozen search-token patterns have one owner:
nm/shared/citation_contracts.py. Reuse it instead of copying parsers.
nm/shared/gates_contracts.py owns each registered gate's response, scope and
recovery. Read actual rows and callers. A declared gate is not evidence it is
wired; a local fallback cannot override its scope.

## Building and verifying

- Apply AGENTS' atomic rule: one prompt and one production file per repair piece,
  with focused tests/documentation. Surface inseparable dependencies before
  expanding scope. Integrate verified pieces before declaring a feature complete.
- Name the general invariant. Separate measured cause from hypothesis, review
  known defect shapes and enumerate affected callers from source.
- Reuse one mechanism across the affected population. Remove redundant paths and
  record dependent work rather than declaring a partial fix complete.
- Observed matters are regression examples, never production keyword lists,
  scenario branches, prompt exceptions or memorised legal answers.
- Distinguish mechanical contracts from semantic/legal judgments. Preserve
  independently valid work, meaningful unknowns and explicit coverage.
- Catch expected service failures at their owner. Do not disguise programming
  errors with broad model-error handlers. Preserve diagnostics without private data.
- Sweep changed identities through callers. Use focused undefined-name and
  conditional-variable checks where relevant; a renamed definition is insufficient.
- Verify HTTP output and saved/reopened state. Browser acceptance examines the
  actual response and sources against the full conversation. Valid JSON, a
  reviewer verdict and isolated tests do not prove semantic accuracy.
- Use actual preceding outputs for integration, not invented intermediate state.
  Synthetic checks establish exercised invariants; bounded live runs measure
  model behaviour. Say which evidence was obtained.
- Keep failing tests guarding live behaviour. Archive by retired responsibility,
  never merely because a test fails, cannot load or reduces the pass count.
- Record evidence and limitations on Advocate build plan. Planning cleanup and a
  paused engine cannot earn runtime or production acceptance.

## Responses and model calls

P10 permits natural professional answers/summaries, grounded analysis, relevant
limitations and proposed questions/next steps. S3 owns their admission contract.
Code owns saved-effect, execution/completion claims, effect-only acknowledgements
and service status, including inside a natural answer.

Independent review sees the whole requested work, complete original conversation,
current authorised records, admitted relevant evidence and complete draft.
It checks additions, omissions, framing and contradictions, not just selected
sentence/passage matches. Substantive rewrites are mechanically checked and
independently reviewed again. Owned IDs, exact quotations, permission, source
identity and confirmed persistence remain code checks.

The standing model default is GPT-4.1 mini unless a scoped comparison or change is
approved. Record normal/conditional calls, inputs, outputs, tokens, latency and
actual cost. Do not add calls merely to repeat a control. P16 imposes no product
spending cap; recovery remains bounded and development experiments retain their
explicitly authorised spend/run limits. A comparison does not promote its model.

## Corpus discipline

- legal_database/ is a gitignored directory junction. Preserve its target, never
  force-add corpus bytes, and use dated manifests to establish coverage.
- Originals, chunks, parents and indexes have different metadata. Identify the
  store, version and filters inspected. One failed lookup cannot prove absence
  from the corpus. Search tools may need explicit junction traversal.
- Held corpus law is the product boundary. Availability, provenance, speaker,
  court treatment, applicability, currency and binding force remain distinct.
  Summarising an uploaded judgment does not admit it as governing authority.
- Resolve named Acts/authorities by exact identity or checked canonical aliases.
  Approximate matching proposes/ranks candidates; it never silently resolves
  legal identity. Preserve ambiguity.
- Unnamed candidate Acts still need identity/applicability checks. Topic keywords
  and model memory cannot decide governing law.
- Check index lineage, embedding model, dimensions and query processing.
  Equal vector dimensions do not establish semantic compatibility.
- Missing/unreadable indexes mean unavailable/not assessed, not no authority.
  Never silently substitute an incompatible store or unbounded scan.
- Ingestion, training, index builds and other long jobs require specific
  authority. Explain effects and the intended command first.

## Tooling and repository discipline

Use available graph tools to narrow scope, then read exact source/tests.
Stale graphs, untracked files, dynamic references and unsupported languages can
hide code. Fall back to rg; never stage files or rebuild/embed a graph solely
for read-only review. Structural and embedding freshness differ. Rank-fusion
scores order results, not semantic confidence. A search_mode of none means no
graph answer; hybrid includes semantic results and is not lexical degradation.

Graph launcher: development_environment/developer_tooling/crg_serve.ps1.
Keep credentials in approved local settings, never tracked configuration, logs or
stdout. Stdio MCP stdout must remain protocol-clean. The launcher documents the
process-local SSLKEYLOGFILE workaround; diagnose before blaming a library.
Preserve required tooling extras when changing installations.

Run from checkout root. Avoid editable installs that import another worktree.
Preserve nm/source_layout.json roles, dependency boundaries and the closed
browser-asset allowlist. assurance/common/homes.py owns tooling population;
do not add a competing directory registry. Configure hooks by path.

Use safe file-writing tools for escaped scripts. On Windows, inspect absolute
paths and junction targets before moving/removing files; keep operations in one
shell and never recurse into corpus targets.

## Delivery

Golden and served end-to-end evaluations need approval for the named bounded run.
Existing explicit authority remains valid within scope. Paid calls, external
processing, long jobs and destructive actions retain their own limits. Tests and
technical review confer neither deployment authority nor legal sign-off.

Commit and push each authorised verified milestone to s0-foundations on the
configured origin for https://github.com/Harul8/Nyaymalaw. Include only this task's
changes, preserve concurrent work, never force-push, and state checks run and
not run. Read-only, pause or no-commit instructions take precedence.

Dated incident narratives remain in Git history, baseline/defect documents and
archive evidence. Remeasure relevant claims before relying on them today.
