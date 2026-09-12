"""One filesystem-removal owner; housekeeping cannot undo an accepted result.

Only concrete I/O layers may depend on this module. Domain, ports and core
remain independent of filesystem operations. A failed removal is returned to
the caller, which retains its existing recovery policy; it never masks the
failure or success of the operation whose temporary name is being removed.
"""
from __future__ import annotations

import shutil
from pathlib import Path


def discard(path: Path) -> bool:
    """Remove one file name; absent is success and an OS refusal is False."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def discard_tree(path: Path) -> bool:
    """Remove a caller-validated temporary tree without masking its outcome."""
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        # A concurrently removed child can raise while the root still exists.
        # Confirm the root name is absent; an unreadable status is not success.
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
