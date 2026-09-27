"""Recheck cached checklist law through the actual source owner, without a model call.

This establishes only that the same captured text remains readable in the bound
generation. It is not an assessment of legal currency, relevance, binding or
authenticity. Unknown or caller-authored generation labels do not certify reuse.
"""
from __future__ import annotations

from collections.abc import Callable

from nm.bootstrap.controlled_generations import GenerationGuard, GenerationUnavailable
from nm.ports.evidence import EvidencePort, Finding, SourceDocument


def bind_source_current(evidence: EvidencePort, guard: GenerationGuard, *,
                        owned_current: Callable[[], bool],
                        session_current: Callable[[], bool]):
    if not isinstance(guard, GenerationGuard) or not all(
            callable(owner) for owner in (owned_current, session_current)):
        raise ValueError("Cached law needs actual generation, file and session owners")

    def boundary():
        guard.require_current()
        return bool(session_current() and owned_current())

    def current(finding: Finding, original_generation: str) -> bool:
        if (not isinstance(finding, Finding) or not finding.locator.strip()
                or not finding.span.strip() or original_generation != guard.version):
            return False
        try:
            if not boundary():
                return False
            document = evidence.document(finding.locator, finding.source_kind.value)
            if not boundary():
                return False
            if (not isinstance(document, SourceDocument) or document.state != "read"
                    or type(document.target) is not int or document.locator != finding.locator
                    or document.kind != finding.source_kind.value):
                return False
            index = document.target - document.first
            if not 0 <= index < len(document.segments):
                return False
            corpus = guard.binding["corpus"]
            expected_snapshot = (corpus["bound_snapshot"]
                if corpus["state"] == "bound_immutable_publication" else "")
            if document.snapshot_id != expected_snapshot:
                return False
            # Only the exact located passage can retain a relevance proof. An
            # occurrence elsewhere in the same Act or judgment is not its source.
            return finding.span in document.segments[index][1]
        except (GenerationUnavailable, OSError, ValueError, PermissionError):
            return False

    return current
