# FROZEN — working subsystems (do not regress)

These subsystems are **working correctly and are frozen**. Any future change must
**not** alter their behavior or outputs. Treat this file as a gate: before editing,
check whether a change touches anything below; if so, stop and reconsider, and after
any change re-run the regression checks at the bottom and confirm identical results.

_Last verified working: 2026-06-09 (multi-dispute consults grounded 100% on the
final memo; cited sections stable across runs)._

---

## 1. Retrieval (issue-spotting + per-dispute + lexical + fast path)
- `agents/legal_analysis.py`
  - `spot_issues`, `issue_search_phrases`, `_ISSUE_CACHE`
  - `retrieve_for_matter` — broad narrative search + per-issue sweep (BM25 lexical
    `lexical_section_lookup` @85, named-section `lookup_section_with_succession` @90,
    fast semantic), **per-issue `issue` tagging**
- `retrieval/retriever.py`
  - `search_bare_acts`, `search_case_laws` (incl. `fast=` path), `lexical_section_lookup`,
    `lookup_section_with_succession`, `topic_case_ids`, `reload_indexes`
**Invariant:** the same fact pattern returns the same governing sections; agent and
eval both call `retrieve_for_matter` (single source of truth).

## 2. Cross-encoder precision rerank (per dispute)
- `retrieval/retriever.py::score_pairs` (BAAI/bge-reranker-v2-m3 wrapper)
- `agents/legal_analysis.py::_precision_rerank_by_issue` (+ `_CE_FIT_FLOOR`, `weak_fit`)
- `agents/orchestrator.py::_select_per_issue_balanced` (per-issue ordering by `ce`,
  round-robin quota), `_format_retrieved_for_prompt` (balanced selection + `fit=` tag)
**Invariant:** each spotted issue contributes its top section to the answer window;
governing provision wins over a merely-adjacent one.

## 3. Reading pane + hyperlinked citations
- `agents/orchestrator.py::_sanitize_citations` (bracket-wrap real chunk_ids, strip
  literal `[chunk_id]`), `_format_retrieved_for_prompt` evidence block
- `api/agent_routes.py` done-event `bare_acts`/`case_laws` (`_filter_to_cited`)
- `frontend/src/App.jsx`: `linkifyCitations`, `openSourcePane`, source-pane windowing
**Invariant:** cited `§N <Act>` renders clickable and opens the correct section.

## 4. Case checklist (build / accumulate / persist / collapse)
- `agents/legal_analysis.py`: `build_checklist`, `_merge_checklists`, `_same_item`,
  `_norm_label` (deterministic carry-forward — prior items never dropped/rephrased)
- `agents/orchestrator.py::query_planning` checklist build; `agents/state.py` channel
- persistence: `api/matters_routes.py` history `checklist`; `api/agent_routes.py`
  done events; `frontend/src/App.jsx` checklist pane (auto-collapsed, persisted)
**Invariant:** checklist accumulates across turns, ticks on confirmation, survives
reload, renders auto-collapsed.

---

## What MAY change (the conversation layer)
The **consult conversational behavior only** — prompt text and consult-phase posture
guards — may evolve. Specifically these are the *intended* surfaces of change:
`_CONSULT_PROMPT`, the consult "core" contract in `agent_node`, `classify_phase`
staging, and the posture guards (`_advises_without_options`, `_asks_legal_decision`
and their reprompts). These must keep calling the frozen retrieval/rerank/evidence/
checklist code **unchanged**.

## Regression checks (run after any change)
1. Multi-dispute consult (e.g. partnership: CBT/forgery/cheque/assault/defamation)
   still cites **NI §138, BNS §356/§316/§336** as hyperlinks — diff `bare_acts`.
2. Matrimonial matter still grounds **§109 / §123 / Dowry Prohibition §4 / PWDV §3**.
3. Checklist still accumulates + ticks + persists + auto-collapses in the UI.
4. `score_pairs` / precision rerank still fires (server log shows per-issue rerank).
5. Server boots; `/agent/stream` returns grounded reply + checklist.
