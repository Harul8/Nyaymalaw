# 03.01 — Understand the contribution

Interpret the advocate's latest contribution against the recorded brief, supplied material and current context. Recognise intent, distinguish disputes, bind words to the right thread and ask proportionate questions without treating an allegation as established.

This is a responsibility within the legal-brain loop, not a mandatory execution
stage or a claim of complete feature acceptance. Files inside this folder stay flat.

## Read first

- [route.py](route.py)
- [brain_context.py](brain_context.py)
- [dispute.py](dispute.py)
- [threading.py](threading.py)
- [briefing.py](briefing.py)

## Boundaries

Party/posture reads and dispute binding remain quoted, attributed interpretations. Reading the file does not create facts or confer authority. Advocate preferences are not case evidence; the stored transcript is not replaced by working-context summaries.

Architectural roles and dependency directions remain explicit in
[`nm/source_layout.json`](../../source_layout.json). No new tool permission,
provider-processing approval or release claim comes from moving a file.

## Complete file index

Navigation over 19 implementation files, 1 browser assets and
the package initializer; this is not test evidence.

### Implementation

- [advocate_memory_contracts.py](advocate_memory_contracts.py) — Explicit account preferences; no open text and no matter material.
- [advocate_memory_routes_api.py](advocate_memory_routes_api.py) — Injectable authenticated account-memory routes, without an API-owner import.
- [advocate_memory.py](advocate_memory.py) — Owned preference changes and a typed presentation-only prefix input.
- [brain_context.py](brain_context.py) — Checked-file context generations, never a model summary replacing the file.
- [briefing.py](briefing.py) — Tracks interactive brief readiness separately from completion of a conversation turn.
- [conversational_proposal.py](conversational_proposal.py) — An exact private conversational candidate, never a merits/release shortcut.
- [dispute.py](dispute.py) — Distinguishes a contribution to an existing dispute from a newly raised dispute.
- [parties.py](parties.py) — Interprets party identities and relationships from supplied words.
- [posture.py](posture.py) — Interprets stated procedural posture without a keyword list.
- [route.py](route.py) — Classifies the current contribution's immediate objective.
- [threading.py](threading.py) — Binds a contribution to existing or new dispute threads.
- [tool_ask_advocate.py](tool_ask_advocate.py) — Proposes one advocate-facing question for review.
- [tool_propose_conversation.py](tool_propose_conversation.py) — Proposes a private natural reply without merits clearance.
- [tool_quote_matter.py](tool_quote_matter.py) — Quotes exact recorded matter words for grounded context.
- [tool_read_facts.py](tool_read_facts.py) — Reads attributed facts without treating allegations as proved.
- [tool_read_matter.py](tool_read_matter.py) — Reads the current admitted matter state.
- [tool_read_thread.py](tool_read_thread.py) — Reads one dispute thread from the current matter.
- [tool_read_turn.py](tool_read_turn.py) — Reads a recorded turn without replacing original history.
- [tool_search_matter.py](tool_search_matter.py) — Searches admitted matter material within the account boundary.

### Browser assets

- [advocate-preferences.js](advocate-preferences.js) — Lets advocates view and update explicit account-level preferences.

### Package

- [__init__.py](__init__.py) — Legal-brain understand capability; no runtime exports.

Return to [Legal brain](../README.md) or [the full project map](../../../docs/PROJECT_STRUCTURE.md).
