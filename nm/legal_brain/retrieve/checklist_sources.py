"""Recheck cached checklist law through the actual source owner, without a model call.

This establishes only that the same captured text remains readable in the bound
generation. It is not an assessment of legal currency, relevance, binding or
authenticity. Unknown or caller-authored generation labels do not certify reuse.
"""

from __future__ import annotations

from collections.abc import Callable

from nm.legal_brain.orchestrate.controlled_generations import GenerationGuard, GenerationUnavailable
from nm.legal_brain.retrieve.evidence_port import EvidencePort, Finding, SourceDocument, SourceKind


def _bind_located_words(
    evidence: EvidencePort,
    guard: GenerationGuard,
    *,
    owned_current: Callable[[], bool],
    session_current: Callable[[], bool],
):
    if not isinstance(guard, GenerationGuard) or not all(
        callable(owner) for owner in (owned_current, session_current)
    ):
        raise ValueError("Cached law needs actual generation, file and session owners")

    def boundary():
        guard.require_current()
        return bool(session_current() and owned_current())

    def current(locator, text, kind, original_generation, *, capture_version=None) -> bool:
        if (
            any(not isinstance(value, str) or not value.strip() for value in (locator, text))
            or not isinstance(kind, str)
            or kind not in {value.value for value in SourceKind}
            or original_generation != guard.version
        ):
            return False
        try:
            if not boundary():
                return False
            document = evidence.document(locator, kind)
            if not boundary():
                return False
            if (
                not isinstance(document, SourceDocument)
                or document.state != "read"
                or type(document.target) is not int
                or document.locator != locator
                or document.kind != kind
            ):
                return False
            index = document.target - document.first
            if not 0 <= index < len(document.segments):
                return False
            corpus = guard.binding["corpus"]
            expected_snapshot = (
                corpus["bound_snapshot"] if corpus["state"] == "bound_immutable_publication" else ""
            )
            if document.snapshot_id != expected_snapshot:
                return False
            if capture_version is not None and capture_version not in {
                guard.version,
                expected_snapshot,
            }:
                return False
            # Only the exact located passage can retain a relevance proof. An
            # occurrence elsewhere in the same Act or judgment is not its source.
            return text in document.segments[index][1]
        except (GenerationUnavailable, OSError, ValueError, PermissionError):
            return False

    return current


def bind_source_current(
    evidence: EvidencePort,
    guard: GenerationGuard,
    *,
    owned_current: Callable[[], bool],
    session_current: Callable[[], bool],
):
    located = _bind_located_words(
        evidence, guard, owned_current=owned_current, session_current=session_current
    )

    def current(finding: Finding, original_generation: str) -> bool:
        return isinstance(finding, Finding) and located(
            finding.locator, finding.span, finding.source_kind.value, original_generation
        )

    return current


def bind_window_current(
    evidence: EvidencePort,
    guard: GenerationGuard,
    *,
    owned_current: Callable[[], bool],
    session_current: Callable[[], bool],
):
    """Raw legal words remain raw, current only through the same actual reader.

    Document capture records the immutable snapshot; paragraph capture records
    the bound composite generation. Neither can be replaced by a caller label,
    neighbouring passage, stored metadata flag or a fabricated Finding.
    """
    located = _bind_located_words(
        evidence, guard, owned_current=owned_current, session_current=session_current
    )

    def current(window, original_generation: str) -> bool:
        required = {"locator", "text", "source_kind", "source_version", "legal_metadata", "missing"}
        if (
            not isinstance(window, dict)
            or not required <= set(window)
            or set(window) - required - {"paragraph_kind"}
            or window["legal_metadata"] != "not_assessed"
            or not isinstance(window["source_version"], str)
            or not window["source_version"].strip()
            or not isinstance(window["missing"], list)
            or not window["missing"]
            or any(not isinstance(value, str) or not value.strip() for value in window["missing"])
            or "paragraph_kind" in window
            and not isinstance(window["paragraph_kind"], str)
        ):
            return False
        return located(
            window["locator"],
            window["text"],
            window["source_kind"],
            original_generation,
            capture_version=window["source_version"],
        )

    return current
