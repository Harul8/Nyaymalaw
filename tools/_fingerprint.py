"""Source identity, so a recorded run cannot vouch for code it never saw.

WHY THIS EXISTS
---------------
`tools/mutate.py` records which counterexamples were rejected, and
`tools/releasegate.py` reads that record to score RG-11 ("the suite bites").
A record with no identity would let a mutation run from three commits ago
certify today's code.

That is defect shape S11 -- an artefact that cannot be told apart from a
current one -- and it is the same argument `nm/knowledge/artefact.py` makes
about the dense index. The only reason that index was KNOWABLY unusable is
that it shipped an `identity.json`; every artefact this project produces
carries its identity for the same reason.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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
        for p in sorted((root / top).rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            h.update(str(p.relative_to(root)).replace("\\", "/").encode("utf8"))
            h.update(p.read_bytes())
    return h.hexdigest()[:16]
