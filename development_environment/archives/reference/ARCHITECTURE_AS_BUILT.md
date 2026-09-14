# Agentified NM — Architecture

> **AS-BUILT RECORD.** This describes the system as it stands today. It is a
> migration reference, not a specification — the target design is
> `docs/ARCHITECTURE.md`, derived from `docs/PRD.md`. Per PRD rule 3, the design
> is never derived from this document; where the two differ, this one is the gap.


Current runtime architecture. When this doc and the code diverge, code wins.

## 1. Product shape

Advocate-facing matter cockpit. The advocate opens a matter, inputs client statement + documents, watches facts extracted and law retrieved side-by-side, answers auto-generated gap questions, approves a strategy memo, then generates filing-ready drafts with per-averment traceability.

v1 deliverables (in build order):

1. Legal notice
2. Plaint
3. Written statement
4. Petition
5. Writ
6. Complaint
7. Reply
8. Rejoinder
9. Interim application
10. Affidavit

## 2. Folder layout

```
agents/
  orchestrator.py       LangGraph orchestrator, matter-centric state
  state.py              AgentifiedState (matter-scoped)
  tool_registry.py      Tool definitions in OpenAI function-calling format
  memory.py             Cross-matter memory (SQLite)
  intake/               Advocate-facing intake — structured input, not chat
  document/             Document fact extractor + cross-referencer
  forum/                Forum identifier + limitation checker
  verification/         Post-draft traceability + citation + limitation checks
  drafter/              Multi-step drafter: outline, section, verify, render

retrieval/
  chunker/              Hierarchical bare-act + paragraph-exact case chunkers
  indexer/              FAISS + BM25 index builder
  retriever.py          Parent-child retrieval, structured-first short-circuit
  legal_graph.py        SQLite legal graph (sections, cross-refs, case-section)
  intent.py             Query intent classifier (including sub-target)
  decomposer.py         Multi-dispute decomposer
  citations.py          Citation graph utilities
  act_equivalence.py    IPC↔BNS, CrPC↔BNSS, IEA↔BSA mapping
  enricher.py           Web fallback (Indiankanoon)
  guard.py              Input safety, prompt-injection, grounding guard

drafts/
  templates/            Jinja templates per deliverable × forum × jurisdiction
  exemplars/            Anonymized gold drafts, tagged for few-shot

platform/
  llm.py                OpenAI client, token budgeting
  memory.py             Memory pressure monitoring
  warmup.py             Tiered warm-up (cold-serve → retrieval → rerank → drafter)
  progress.py           SSE progress events
  dedup.py              Utility
  feedback/             Feedback logger, reviewer, store, pipeline
  training/             Runtime few-shot layer

prompts/
  intake.py             Advocate-facing intake prompts
  research.py           Retrieval / analysis prompts
  drafter.py            Multi-step drafting prompts

api/
  matters_routes.py     Matter CRUD + cockpit state
  drafts_routes.py      Draft lifecycle, versions, export
  retrieval_routes.py   Ad-hoc search endpoints
  admin_routes.py       Admin
  auth_routes.py        Auth
  library_routes.py     Bare acts / case laws library browsing
  deps.py               Shared FastAPI dependencies

frontend/               React advocate cockpit
legal_database/         Corpus + indices
scripts/                Index build, graph rebuild, one-off maintenance
tests/                  Unit + integration
evals/                  Retrieval precision + draft quality evals
```

## 3. Orchestrator graph

```
START
  |
  v
[safety_check]  -- unsafe --------------------------------------> END
  | safe
  v
[rate_limit]    -- budget exceeded ----------------------------> END
  | ok
  |
  +-- multi-dispute query ---> [research_worker xN (Send)] --+
  |                                                          |
  v                                                          |
[agent]  <-------------------------------------------------- +
  |
  +-- tool calls --> [tools] --> [tool_retry] --> [agent]  (loop)
  |
  +-- drafting request --> [drafter_outline] --> [drafter_section xN]
  |                              |
  |                              v
  |                        [drafter_verify]  (per-averment trace)
  |                              |
  |                              v
  |                        [drafter_render]  (jinja -> docx / pdf)
  |
  +-- final answer --> [grounding_guard] --> END
```

Key carryovers from Agentic NM: safety, rate limit, Send() fan-out, tool_retry, grounding guard.

Key additions: drafter sub-graph, advocate-facing intake entry, matter-scoped state.

## 4. Retrieval: parent-child hierarchical

### The problem in v1

Sections were stored as whole-section chunks. Long sections (S.138 NI Act with provisos (a)(b)(c) + explanations; CPC Order 7 Rule 1) became one 3000-char embedding. Intra-section signal diluted. BM25 matched boilerplate.

Case law chunks had paragraph_num like `1_2` — paragraphs merged into pairs, so para-exact retrieval was impossible.

### The fix

**Hierarchical chunking.** Every bare-act chunk is addressable as `act_id > section > sub_section > clause > proviso|explanation|illustration`, with the parent-chain preserved in metadata. Case-law chunks are single-paragraph with paragraph_num preserved.

**Parent-child retrieval.** Two passes:

1. Coarse: retrieve top-K *parents* (section-level for acts, case-level for cases) using section summary + BM25 + vector over section text.
2. Fine: within each parent, retrieve top-k *children* (sub-section / clause / proviso for acts; paragraph for cases) using a second vector + BM25 pass scoped to that parent's children.

**Structured-first short-circuit.** If the query has explicit refs ("S.138 proviso (c)", "Article 21", "[2019] 9 SCC 1 para 42"), bypass vector search and go directly to `legal_graph` for exact node retrieval. Vector search is only used to fill gaps.

**Sub-target intent.** Query intent classifier labels the sub-target — `ingredient | defence | exception | proviso | explanation | illustration | ratio | obiter | relief | procedure` — and biases fine retrieval toward that atom type.

**Reranker.** Keep the cross-encoder. Add an optional LLM-based rerank on top-20 for high-stakes calls (drafting, verification).

## 5. Drafter

Multi-step:

1. **Outline** — cause title, parties, jurisdictional averments, limitation, ingredient checklist, relief map.
2. **Section drafts** — for each section of the chosen template (facts, grounds, prayer, etc.), produce a draft grounded in `matter_state` fact IDs and `legal_graph` section ids.
3. **Verify** — for every averment check fact-ID trace, for every citation check resolvability and non-overruled status, for every ground check ingredient coverage.
4. **Render** — Jinja template fills, export `.docx` + `.pdf`.

Templates and exemplars are keyed by `(deliverable × forum × jurisdiction)`.

## 6. Warm-up (tiered)

Tier 0 — cold serve (< 15s): FastAPI boot, OpenAI client, matter state DB open. Chat endpoints return immediately with "retrieval warming" status.

Tier 1 — retrieval ready (< 60s): FAISS indices `mmap`'d read-only, BM25 loaded from JSON, embedder model cached on disk, `legal_graph` SQLite opened.

Tier 2 — rerank ready (on demand): cross-encoder loaded on first rerank call (GPU with CPU fallback).

Tier 3 — drafter ready (on demand): template library parsed on first draft call.

Unchanged indices are skipped via metadata-hash check.

## 7. State

`AgentifiedState` is matter-centric:

- `matter_id` — one per client-matter
- `session_id` — one per intake conversation under the matter
- `client_statement` — raw input
- `extracted_facts` — list of fact records with stable `fact_id`
- `documents` — list of uploaded doc records with extracted facts
- `gap_matrix` — per section × ingredient × fact mapping
- `retrieved_law` — sections and cases with parent-child context
- `strategy_memo` — advocate-approved before drafting
- `drafts` — list of `DraftVersion` (deliverable, forum, jurisdiction, markdown body, docx path)
- `messages` — conversation log (LangGraph reducer append)
- `research_results` — fan-out accumulator

## 8. Safety and guardrails

Input safety (harmful-content classifier), prompt-injection detection, PII flagging, grounding guard (every citation must resolve to `legal_graph` or be dropped), draft-traceability verifier (every averment ↔ fact_id), overruled-case filter.

## 9. Feedback loop

Every interaction logs to the feedback workbook. Runtime few-shot learner picks high-signal examples and injects them into future prompts. Daily distillation pipeline reviews sessions and updates the exemplar corpus.

## 10. Source of truth

When this doc and code diverge, code wins. Primary runtime files:

- `agents/orchestrator.py`
- `agents/state.py`
- `agents/tool_registry.py`
- `agents/drafter/*`
- `retrieval/retriever.py`
- `retrieval/chunker/*`
- `retrieval/legal_graph.py`
- `retrieval/guard.py`
- `platform/llm.py`
- `api_server.py`
- `mcp_server.py`
