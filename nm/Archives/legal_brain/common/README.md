# 03.00 — Share one guidance and contract owner

Keep genuinely cross-capability professional guidance, source-quoting and citation contracts, structured-read policies, output ceilings and tier decisions in single owners used by the other capabilities.

This is a responsibility within the legal-brain loop, not a mandatory execution
stage or a claim of complete feature acceptance. Files inside this folder stay flat.

## Read first

- [principles_generated.py](principles_generated.py)
- [principles_port.py](principles_port.py)
- [conversation.py](conversation.py)
- [citation_contracts.py](citation_contracts.py)
- [quotable_contracts.py](quotable_contracts.py)
- [reads_contracts.py](reads_contracts.py)

## Boundaries

Common is not a dumping ground. Capability-specific contracts, ports, adapters and tools stay beside their capability. Principles are authored once in docs/blueprint/LEGAL_BRAIN_PRINCIPLES.md and generated here; do not independently edit a second ruleset or use model knowledge as factual/legal evidence.

Architectural roles and dependency directions remain explicit in
[`nm/source_layout.json`](../../../source_layout.json). No new tool permission,
provider-processing approval or release claim comes from moving a file.

## Complete file index

Navigation over 11 implementation files, 0 browser assets and
the package initializer; this is not test evidence.

### Implementation

- [ceiling.py](ceiling.py) — Derives bounded response ceilings from actual work and sources.
- [citation_contracts.py](citation_contracts.py) — How an advocate writes a provision reference.
- [conversation.py](conversation.py) — Shared professional judgment principles, not example conversations or routing rules.
- [curation_contracts.py](curation_contracts.py) — Types whether a curated table actually covers a key.
- [principles_file_adapter.py](principles_file_adapter.py) — Read-only local owner guidance; snapshots do not change during a turn.
- [principles_generated.py](principles_generated.py) — Generated legacy consumer of docs/blueprint/LEGAL_BRAIN_PRINCIPLES.md.
- [principles_port.py](principles_port.py) — Versioned owner guidance, supplied to the pure reasoning loop by a port.
- [quotable_contracts.py](quotable_contracts.py) — Separates source text that may be quoted from text only read internally.
- [reads_contracts.py](reads_contracts.py) — Defines structured model-read contracts and their costs.
- [tiers_contracts.py](tiers_contracts.py) — Which steps may use the expensive tier, and the measurement that earned it.
- [tool_read_owner_guide.py](tool_read_owner_guide.py) — Reads versioned owner guidance through the registered tool.

### Package

- [__init__.py](__init__.py) — Legal-brain common capability; no runtime exports.

Return to [Legal brain](../README.md) or [the full project map](../../../../docs/PROJECT_STRUCTURE.md).
