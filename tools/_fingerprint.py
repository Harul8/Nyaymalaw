"""Source identity for recorded runs. THE OWNER IS `nm/domain/identity.py`.

This module is a re-export and holds no definition of its own.

It used to hold the definition, and that was wrong in a way that only showed up
on 31 August 2026: a scenario run made live model calls against an API server
started the previous evening, found none of the slice it existed to prove, and
exited 0. The fix is for the SERVED PROCESS to report which code it loaded —
and `tools/` is not shipped, so the product could not have answered from here.

Moving it into `nm/` put the definition where both callers can reach it. Two
copies of a digest would be worse than none: they would agree until the day
they did not, and the disagreement would look like a code change.
"""
from __future__ import annotations

from pathlib import Path

from nm.domain.identity import FINGERPRINTED, ROOT, source_fingerprint

__all__ = ["FINGERPRINTED", "ROOT", "Path", "source_fingerprint"]
