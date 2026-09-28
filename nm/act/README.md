# 06 — Act

Drafting, hearing/witness preparation and consequential-action state. Preparing content or a product proposal is separate from advocate approval, authority and an actual external effect.

Key files:

- [drafting.py](drafting.py) — Owns native drafting package state and content projections.
- [action.py](action.py) — Owns consequential-action transitions and projections.
- [action_proposal_tool.py](action_proposal_tool.py) — Checks the exact owned drafting package and supplied instruction for preparation only.
- [tool_propose_action.py](tool_propose_action.py) — The registered model-facing preparation door; it does not approve, send or file.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Services and native owners

- [action.py](action.py) — Persists consequential-action proposals and their recorded state.
- [action_proposal_tool.py](action_proposal_tool.py) — Checks preparation-only action content without approving external action.
- [drafting.py](drafting.py) — Assembles source-bound drafting packages for review.
- [hearing.py](hearing.py) — Hearing and negotiation preparation, derived and not asserted.

### Registered model tool doors (core)

- [tool_propose_action.py](tool_propose_action.py) — Offers preparation-only action content through the registered tool.

### Contracts and package

- [__init__.py](__init__.py) — Authorised legal actions, drafting and hearing preparation.
- [action_contracts.py](action_contracts.py) — Consequential-action states and approvals; no file is sent or filed here.
- [drafting_contracts.py](drafting_contracts.py) — Types draft packages and their not-ready-to-file states.
- [witness_contracts.py](witness_contracts.py) — Preparation that does not put words in a witness's mouth.
