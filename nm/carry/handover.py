"""Persisting handovers, closure and re-entry. BK-33-AC2, BK-39, BK-59. P32.

`nm.carry.handover_contracts` and `nm.close.closure_contracts` hold the state and the rules; this
holds the persistence shape, the served projections and re-entry.

RE-ENTRY READS THE FILE, NOT A CACHE
--------------------------------------
BK-33-AC2 asks that re-entry restore the selected matter *from the
authoritative file without cross-matter state leakage*. `re_entry` therefore
takes one matter and reads only it: there is no second argument it could mix in
and no store lookup that could return a sibling. The leak this refuses is the
one that produces the worst possible outcome in this product -- another
client's material rendered under this client's name.

EVENTS GO THROUGH P18's LEDGER
--------------------------------
BK-59-AC1 asks that a material event invalidate or recompute affected
obligations *without rewriting past issued records*. Both halves are already
built: `nm.work_the_file.dependency.invalidate` marks exactly the closure a change
reaches and keeps the prior state as a `Revision`. `record_event` hands it the
moved inputs and returns what it reached. Nothing here walks the graph.
"""
from __future__ import annotations




def _enum(kind, value, fallback):
    try:
        return kind(value)
    except (ValueError, KeyError):
        return fallback


# ------------------------------------------------------------- handovers ---

# --------------------------------------------------------------- closure ---

# -------------------------------------------------------------- re-entry ---

