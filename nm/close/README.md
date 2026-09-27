# Close

Matter closure and retention/hold/restore state. A request does not establish approval or completed erasure, and historical tombstones remain relevant when assessing a restore.

Key files:

- [closure_contracts.py](closure_contracts.py) — Types closure state and transitions.
- [retention_contracts.py](retention_contracts.py) — Types retention requests, holds and their transition rules.
- [retention.py](retention.py) — Owns retention persistence decisions and the restore guard.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Services and native owners

- [retention.py](retention.py)

### Contracts and package

- [__init__.py](__init__.py)
- [closure_contracts.py](closure_contracts.py)
- [retention_contracts.py](retention_contracts.py)
