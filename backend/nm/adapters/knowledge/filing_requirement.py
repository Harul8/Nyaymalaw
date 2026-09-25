"""The filing-requirement readiness, served through the port. LB-125.

`nm.core` may not import `nm.knowledge`, so the adapter layer joins them --
the same arrangement the elements, pre-institution, governing-law,
authority-weight, interim and procedural-period planes already use.

IT HOLDS THE MANIFEST, not a copy of the answer. The manifest is the CURATED
assertion of intended coverage, and it is read at the moment it is asked, so
the day the Telangana schedule is ingested this answers differently with no
edit here. An installation with no manifest measures nothing and says so.
"""
from __future__ import annotations

from pathlib import Path

from nm.domain.traceability import implements
from nm.knowledge import filing_requirement as curated
from nm.ports.filing_requirement import Readiness, Requirement


class CuratedFilingRequirements:
    """`nm.knowledge.filing_requirement`, behind `FilingRequirementPort`."""

    def __init__(self, manifest_path: Path | str | None = None) -> None:
        """A MANIFEST THAT CANNOT BE READ IS NOT AN EMPTY MANIFEST.

        An empty one would report every instrument as not intended, which is a
        finding; an unreadable one is `None`, which reaches `readiness` as
        NOT_MEASURED. The two send an advocate in opposite directions, and the
        difference is decided here rather than by an exception nobody catches.
        """
        self._manifest = None
        if manifest_path is not None:
            from nm.knowledge.manifest import Manifest
            try:
                self._manifest = Manifest.load(manifest_path)
            except (OSError, ValueError, KeyError, TypeError):
                self._manifest = None

    @implements("D1")
    def readiness(self, requirement: Requirement) -> Readiness:
        return curated.readiness(requirement, self._manifest)
