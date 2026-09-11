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
import re
from dataclasses import dataclass
from pathlib import Path

from nm.domain.text import refuses_blank_text


class ArtefactRefused(RuntimeError):
    """The artefact does not match what it must have been built from."""


_SHA256 = re.compile(r"[0-9a-f]{64}")


@refuses_blank_text()
@dataclass(frozen=True)
class ArtefactLineage:
    """Byte-exact build identity for one derived corpus member.

    Model and dimensions are not meaningful for every artefact.  Their basis
    is nevertheless explicit: a lexical SQLite index can say
    ``model="not_applicable: deterministic FTS5"`` and
    ``dimension_basis="not_applicable: lexical index"``.  Missing metadata is
    never made indistinguishable from an intentional non-applicability.
    """

    artefact: str
    builder: str
    source_versions: tuple[str, ...]
    content_sha256: str
    model: str
    tokenizer: str
    dimension_basis: str
    population_basis: str
    expected_population: int
    observed_population: int
    dimensions: int | None = None

    def __post_init__(self) -> None:
        if not self.source_versions:
            raise ValueError("derived artefact lineage requires source versions")
        if len(self.source_versions) != len(set(self.source_versions)):
            raise ValueError("derived artefact source versions must be unique")
        if not _SHA256.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a full lowercase sha256")
        if self.dimensions is not None and self.dimensions < 1:
            raise ValueError("artefact dimensions must be positive")
        if self.expected_population < 1 or self.observed_population < 0:
            raise ValueError(
                "artefact populations require a positive expectation and "
                "non-negative observation"
            )

    def as_dict(self) -> dict:
        return {
            "artefact": self.artefact,
            "builder": self.builder,
            "source_versions": list(self.source_versions),
            "content_sha256": self.content_sha256,
            "model": self.model,
            "tokenizer": self.tokenizer,
            "dimension_basis": self.dimension_basis,
            "population_basis": self.population_basis,
            "expected_population": self.expected_population,
            "observed_population": self.observed_population,
            "dimensions": self.dimensions,
        }

    def require_payload(self, payload: bytes) -> None:
        """Refuse a derived member changed after its build was recorded."""
        import hashlib

        observed = hashlib.sha256(payload).hexdigest()
        if observed != self.content_sha256:
            raise ArtefactRefused(
                f"{self.artefact!r} content is {observed}, but its lineage "
                f"records {self.content_sha256}; the changed artefact is refused"
            )

    def require_sources(self, published_versions: tuple[str, ...]) -> None:
        """Refuse lineage outside the exact source population being published."""
        missing = sorted(set(self.source_versions) - set(published_versions))
        if missing:
            raise ArtefactRefused(
                f"{self.artefact!r} was built from source versions outside this "
                f"snapshot: {', '.join(missing)}"
            )

    def require_reconciled(self) -> None:
        if self.observed_population != self.expected_population:
            raise ArtefactRefused(
                f"{self.artefact!r} expected {self.expected_population} records "
                f"on {self.population_basis}, but contains "
                f"{self.observed_population}"
            )


@refuses_blank_text()
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
