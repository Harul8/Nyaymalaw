"""Derived-artefact identity. Defect shape S11.

    Every derived artefact -- index, embedding store, summary, citator,
    manifest -- records the identity of what it was built from and is REFUSED
    on mismatch, not used with a warning.

WHY A REFUSAL AND NOT A WARNING
-------------------------------
An embedding index built with model A and queried with model B's vectors does
not error. It returns plausible, confidently wrong neighbours, and every answer
downstream inherits that silently. There is no symptom to notice.

This is not hypothetical here. The previous build left a dense index of 284,447
provisions at 384 dimensions, built with `sentence-transformers/all-MiniLM-L6-v2`.
This product's declared embedding model is `text-embedding-3-large`. The index
is real, sizeable, and completely unusable -- and the ONLY reason that is
knowable is that it shipped an identity file beside it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ArtefactRefused(RuntimeError):
    """The artefact does not match what it must have been built from."""


@dataclass(frozen=True)
class ArtefactIdentity:
    artefact: str
    builder: str
    built_at: str | None = None
    dimensions: int | None = None
    rows: int | None = None
    fingerprint: str | None = None

    @staticmethod
    def load(path: str | Path) -> "ArtefactIdentity":
        p = Path(path)
        if not p.exists():
            # An artefact with NO identity is refused outright. "We do not know
            # what built this" is not a lesser problem than a mismatch -- it is
            # the same problem with less information.
            raise ArtefactRefused(
                f"{p} has no identity file. A derived artefact that cannot say "
                f"what it was built from is refused, not used.")
        doc = json.loads(p.read_text(encoding="utf8"))
        note = doc.get("note") or ""
        dims = None
        for token in note.replace(",", " ").split():
            if token.isdigit() and int(token) in (256, 384, 512, 768, 1024, 1536, 3072):
                dims = int(token)
        return ArtefactIdentity(
            artefact=doc.get("artefact", "unknown"),
            builder=doc.get("builder", "unknown"),
            built_at=doc.get("built_at"),
            dimensions=dims,
            rows=(doc.get("inputs") or [{}])[0].get("rows"),
            fingerprint=doc.get("fingerprint"),
        )

    def require_built_with(self, expected_model: str) -> None:
        """Raise unless this artefact was built with the model we will query it with."""
        if expected_model.lower() not in self.builder.lower():
            raise ArtefactRefused(
                f"{self.artefact!r} was built with {self.builder!r}, but this "
                f"product queries with {expected_model!r}. Querying an index "
                f"across embedding models does not error -- it returns "
                f"plausible, confidently wrong neighbours. Rebuild the index, "
                f"or change NM_EMBED_MODEL and re-index (PRD §7.4.2 carve-out)."
            )
