# 07 — Carry

Handover, re-entry, scheduled service decisions and conflict-watch state. Scheduling a job is not running or delivering it; durable work execution remains with the existing shared worker and configured connectors.

Key files:

- [handover.py](handover.py) — Persists handover/closure projections, re-entry and source-change propagation.
- [handover_contracts.py](handover_contracts.py) — Types the native handover state.
- [service.py](service.py) — Prepares scheduling/cancellation and conflict-watch decisions.
- [service_contracts.py](service_contracts.py) — Types scheduled service work independently of dispatch.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Services and native owners

- [handover.py](handover.py) — Persists handover records and manages closure and re-entry transitions.
- [service.py](service.py) — Schedules authorised follow-up work and monitors recorded conflict-watch state.

### Contracts and package

- [__init__.py](__init__.py) — Continuity, service and advocate handover of the matter record.
- [handover_contracts.py](handover_contracts.py) — Handover does not move responsibility by itself.
- [service_contracts.py](service_contracts.py) — Nothing runs in the background without somebody having asked.
