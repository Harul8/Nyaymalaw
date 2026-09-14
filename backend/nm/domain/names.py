"""Removing a name, when the decision has already been made.

    from nm.domain.names import discard, discard_tree

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
file another thread still holds open raises, and `accept_invitation` used to
answer that by deleting the very record that made the claim exclusive. Both
claimants were then refused, the invitation went back on the door, and the race
test caught it on the first of twenty attempts -- intermittently, which is how
it survived earlier runs.

WHY THIS IS A MODULE AND NOT A LINE AT EACH SITE
--------------------------------------------------
Four call sites in the store package removed a name after a durable write and
three of them were each written with their own idea of what to do when the
removal fails. That is CLAUDE.md section 4's question -- *what refuses the
second copy?* -- and the answer has to be structural, so this is the only place
in `backend/nm/` permitted to call `unlink` or `rmtree`, and
`tests/test_a_completed_claim_survives_its_own_housekeeping.py` scans the
product and fails the build on a second one.

WHY IT LIVES IN `backend/nm/domain/` AND NOT IN `backend/nm/adapters/store/`
--------------------------------------------------------------
IT LIVED THERE, AND THE LAYER WAS THE DEFECT. `assurance/gate/layercheck.py` permits
`knowledge` to import only `{knowledge, ports, domain}`, so `backend/nm/knowledge/`
could not reach the owner at all. When P20's immutable-corpus publication
landed -- three temporary-file removals and a lock release in
`backend/nm/knowledge/manifest.py` -- it could not have used the one mechanism even had
its author looked for it, and the product-wide sweep went red on the
integration commit that brought the two branches together.

The lesson is not "P20 should have looked". It is that **an owner reachable
from only part of the product is not an owner**, and the rule -- removing a
name is one decision -- is a rule about the product, not about a store adapter.
`domain` is the one layer every other layer may import, `pathlib` and `shutil`
are the standard library rather than the provider clients `layercheck` keeps
out of the core, so this is where a rule of that scope belongs.

TWO FUNCTIONS, BECAUSE THE SWEEP HAD ONLY FOUND ONE HALF
----------------------------------------------------------
The scanner looked for `.unlink(` and `os.remove(` and did not look for
`shutil.rmtree(`. A partial publication transaction is removed with `rmtree`
and can fail on exactly the same held-open file, in exactly the same
`finally`, with exactly the same consequence -- so it was the same defect
sitting outside the population the sweep drew. Widening the scanner without
giving the widened population an owner would only have turned a silent gap
into a red build with nowhere to go.
"""
from __future__ import annotations

import shutil
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


def discard_tree(path: Path) -> bool:
    """The same postcondition for a directory. NEVER RAISES.

    A separate function rather than a flag, because the two are different
    postconditions and a caller that passes the wrong one should not silently
    get the other: `discard` on a directory raises `IsADirectoryError` on
    POSIX and `PermissionError` on Windows, and both are caught here as False
    rather than becoming a distinction the caller has to know.
    """
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        # A child can disappear concurrently while the root remains. Success
        # means the requested root name is gone, not merely that rmtree saw a
        # missing descendant.
        try:
            path.lstat()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return False
    except OSError:
        return False
    return True
