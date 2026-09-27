# Act

Drafting, hearing/witness preparation and consequential-action state. Preparing content or a product proposal is separate from advocate approval, authority and an actual external effect.

Key files:

- [drafting.py](drafting.py) — Owns native drafting package state and content projections.
- [action.py](action.py) — Owns consequential-action transitions and projections.
- [action_proposal_tool.py](action_proposal_tool.py) — Checks the exact owned drafting package and supplied instruction for preparation only.
- [tool_propose_action.py](tool_propose_action.py) — The registered model-facing preparation door; it does not approve, send or file.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Services and native owners

- [action.py](action.py)
- [action_proposal_tool.py](action_proposal_tool.py)
- [drafting.py](drafting.py)
- [hearing.py](hearing.py)

### Registered model tool doors (core)

- [tool_propose_action.py](tool_propose_action.py)

### Contracts and package

- [__init__.py](__init__.py)
- [action_contracts.py](action_contracts.py)
- [drafting_contracts.py](drafting_contracts.py)
- [witness_contracts.py](witness_contracts.py)
