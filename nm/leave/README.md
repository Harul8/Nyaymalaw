# 09 — Leave

Ending the server-owned account session. The HTTP edge separately clears cookies; sign-out is a human account operation, not a model tool or a claim that a missing token represented a live session.

Key files:

- [sign_out.py](sign_out.py) — Delegates session closure to the native directory owner and retains its three-state outcome.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Services and native owners

- [sign_out.py](sign_out.py) — Ends the server-owned session through the native directory owner.

### Contracts and package

- [__init__.py](__init__.py) — Marks the session-termination package; it exports no alternate logout path.
