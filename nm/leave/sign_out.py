"""End the server-owned session; cookie clearing is the HTTP edge's job.

An absent token is not reported as an ended live session. The native directory
owner returns the same three-state outcome that the sign-out response carries.
This human-only capability is never installed in the model tool registry.
"""
from __future__ import annotations

from nm.arrive.directory_port import DirectoryPort


def end_session(directory: DirectoryPort, token: str | None) -> str:
    return directory.close_session(token or "", "signed out")
