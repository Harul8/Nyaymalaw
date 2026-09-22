"""One construction point for the exact words obtained through the evidence port."""
from nm.domain.source_excerpt import SourceExcerpt
from nm.ports.evidence import Finding


def document_anchor(body: str, saved: str) -> tuple[int, int] | None:
    """Unique exact words, retaining original offsets across whitespace changes."""
    import re
    words = saved.split()
    if not words:
        return None
    matches = re.finditer(r"\s+".join(re.escape(word) for word in words), body)
    match = next(matches, None)
    if match is None or next(matches, None) is not None:
        return None
    return match.start(), match.end() - match.start()


def capture(finding: Finding) -> SourceExcerpt:
    return SourceExcerpt.capture(
        label=finding.ref, locator=finding.locator, namespace=finding.store,
        text=finding.span, kind=finding.source_kind.value,
        valid_from=finding.valid_from.isoformat() if finding.valid_from else "",
        valid_to=finding.valid_to.isoformat() if finding.valid_to else "")
