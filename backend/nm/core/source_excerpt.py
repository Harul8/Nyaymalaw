"""One construction point for the exact words obtained through the evidence port."""
from nm.domain.source_excerpt import SourceExcerpt
from nm.ports.evidence import Finding


def capture(finding: Finding) -> SourceExcerpt:
    return SourceExcerpt.capture(
        label=finding.ref, locator=finding.locator, namespace=finding.store,
        text=finding.span, kind=finding.source_kind.value,
        valid_from=finding.valid_from.isoformat() if finding.valid_from else "",
        valid_to=finding.valid_to.isoformat() if finding.valid_to else "")
