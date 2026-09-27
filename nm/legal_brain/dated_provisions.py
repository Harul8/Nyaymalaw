"""Bind the actual dated adapter to core capture without leaking adapter types."""
from __future__ import annotations

import json

from nm.legal_brain.evidence_port import SourceDocument, SourceKind
from nm.legal_brain.tool_sources import DatedProvisionCapture, capture_document, combine_captures


def dated_provision_reader(evidence, *, source_generation):
    method = getattr(evidence, "read_provision_at_date", None)
    if not callable(method):
        return None

    def read(act, section, as_of):
        result = method(act, section, as_of)
        # Only the trusted typed adapter output produces source windows. The
        # author cannot add a revision approval, source text or capture flag.
        captures = []
        for passage in result.passages if not result.evidence.findings else ():
            document = SourceDocument("read", label=passage.ref, store=passage.store,
                # An unbound read has a host-observed generation, not an
                # invented immutable-publication snapshot. Reuse still checks
                # the actual generation and exact located bytes separately.
                snapshot_id=passage.snapshot_id or source_generation, target=0,
                segments=((passage.locator, passage.text),),
                locator=passage.locator, kind=SourceKind.PROVISION.value)
            captures.append(capture_document(document, kind=SourceKind.PROVISION))
        return DatedProvisionCapture(result.evidence, combine_captures(*captures),
            json.dumps(result.selection.as_record(), sort_keys=True,
                       ensure_ascii=False, allow_nan=False))

    return read
