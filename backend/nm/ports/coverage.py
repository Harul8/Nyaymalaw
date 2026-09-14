"""The coverage port. What the corpus holds, asked at turn time.

The engine must be able to say *"the binding court for this jurisdiction has no
output held"* before the advocate relies on an answer. It may not read a file
to find that out, so the question crosses a port and the answer is a domain
value.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from nm.domain.coverage import CoveragePosition


@runtime_checkable
class CoveragePort(Protocol):
    def position(self, jurisdiction: str) -> CoveragePosition: ...
