"""Source identity. WHAT CODE IS THIS, said by the thing itself.

WHY THIS IS IN THE PRODUCT AND NOT IN `tools/`
-----------------------------------------------
It began in `tools/_fingerprint.py`, so that a recorded mutation run could not
certify code it never saw. That was right and it was half the population.

A RUNNING PROCESS IS AN ARTEFACT TOO. On 31 August 2026 a scenario run made
live model calls against an API server started the previous evening, found none
of the slice it existed to prove, and exited 0. The verdict was indisputable
and it was about code nobody had run.

Had the fingerprint lived only in `tools/`, the served process could not have
answered the question — `tools/` is not shipped, so a deployed product would
report `unknown` and the check would degrade to nothing exactly where it
matters most. So the owner is here, and `tools/_fingerprint.py` re-exports it.
One definition; CLAUDE.md §4 is about what refuses the second copy.

This is the same argument `nm/knowledge/artefact.py` makes about the dense
index: the only reason that 437MB index was KNOWABLY unusable is that it
shipped an `identity.json`. Every artefact this project produces carries its
identity, and a process serving turns is one.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: What a run's verdict depends on. `tests/` is included because a mutation
#: proves a TEST bites, so a changed test invalidates the record exactly as a
#: changed source file does.
FINGERPRINTED = ("nm", "tests")


def source_fingerprint(root: Path | None = None) -> str:
    """A stable digest of the code a recorded run was made against.

    Path-and-content, sorted, so it is reproducible across machines and does
    not move with mtimes. Cheap enough to compute on every run.
    """
    root = root or ROOT
    h = hashlib.sha256()
    for top in FINGERPRINTED:
        base = root / top
        if not base.exists():
            # NOT ASSESSED, and it must not read as "nothing has changed".
            # A deployment that ships `nm/` without `tests/` is ordinary; a
            # digest that quietly skipped a whole tree would match across a
            # change it never looked at.
            h.update(f"<absent:{top}>".encode())
            continue
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            h.update(str(p.relative_to(root)).replace("\\", "/").encode("utf8"))
            h.update(p.read_bytes())
    return h.hexdigest()[:16]
