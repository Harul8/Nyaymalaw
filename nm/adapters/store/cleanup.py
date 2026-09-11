"""Removing a name, when the decision has already been made.

    from nm.adapters.store.cleanup import discard

THE RULE, stated without the site that exposed it
---------------------------------------------------
**A claim that is already established is never surrendered by the failure of a
step that did not establish it.**

An exclusive create is a compare-and-set: when it succeeds, the decision is
made, it is durable, and another caller has very possibly already been refused
against it. Everything after that point is either

  * part of delivering what the claim was for -- and its failure is a genuine
    rollback, because nothing was delivered; or
  * HOUSEKEEPING -- tidying a name that no longer decides anything.

Housekeeping that can raise is a step that can undo a decision somebody has
already acted on. That is not a theoretical ordering: on Windows, removing a
file another thread still holds open raises, and
`accept_invitation` used to answer that by deleting the very record that made
the claim exclusive. Both claimants were then refused, the invitation went back
on the door, and the race test caught it on the first of twenty attempts --
intermittently, which is how it survived earlier runs.

WHY THIS IS A MODULE AND NOT A LINE AT EACH SITE
--------------------------------------------------
Four call sites in this package remove a name after a durable write, and three
of them were each written with their own idea of what to do when the removal
fails. That is CLAUDE.md section 4's question -- *what refuses the second copy?*
-- and the answer has to be structural, so this is the only place in `nm/`
permitted to call `unlink`, and
`tests/test_a_completed_claim_survives_its_own_housekeeping.py` scans the
product and fails the build on a second one.
"""
from __future__ import annotations

from pathlib import Path


def discard(path: Path) -> bool:
    """Remove a name, reporting whether it went. NEVER RAISES.

    Returns False when the name is still there. The caller decides what that
    means -- there is no answer here that is right for every site, and a
    swallowed failure that nobody can see is the absent-reads-as-success shape
    this codebase has paid for nine times.

    An already-absent name is success: the postcondition is that the name is
    gone, and it is.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True
