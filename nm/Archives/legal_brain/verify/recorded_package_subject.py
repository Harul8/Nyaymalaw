"""Rehydrate one historical verifier subject from its actual captured owners.

This does not assert current legal applicability. Current source/document and
binding owners remain mandatory at the actual continuation/display admission.
No model-authored replacement source, premise or saved verdict is evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopRecord, StepKind
from nm.Archives.legal_brain.reason.matter_support import MatterDocumentSpan, captured_documents
from nm.Archives.legal_brain.retrieve.tool_sources import findings_from_record, source_envelopes_from_event
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.Archives.legal_brain.verify.verifier import EvidencePackage, EvidenceSpan, _json_value
from nm.shared.json_values import same_json_value


def recorded_source_prefixes(parent, saved, matter, log):
    """Exact owned source population before a real recorded review checkpoint."""
    # Supplemental inputs may legitimately cite an earlier exact source read.
    # Admit only actual same-file sealed source prefixes that existed when this
    # judge started; later reads cannot be projected backwards into its proof.
    for record in matter.loop_records:
        if (
            record.identity.matter_id != parent.identity.matter_id
            or record.identity.advocate_id != parent.identity.advocate_id
            or record.identity.matter_version >= saved.identity.matter_version
        ):
            continue
        if log.read(record.identity) != record:
            raise ReviewRefused("A historical source has no exact sealed journal owner")
        events = tuple(
            row
            for row in record.events
            if record.identity.matter_version + row.sequence - 1 < saved.identity.matter_version
        )
        prefix = LoopRecord(record.identity, events)
        yield prefix


def recorded_package_subject(parent, saved, matter, log):
    """An actual prompt must reproduce the complete original package contract."""
    starts = [row.payload for row in saved.events if row.kind is StepKind.MODEL_STARTED]
    if len(starts) != 1:
        raise ReviewRefused("A referenced conditional input has no sole actual judge dispatch")
    payload = json.loads(starts[0]["prompt"]["user"])
    findings, documents = [], []
    for prefix in recorded_source_prefixes(parent, saved, matter, log):
        for finding in findings_from_record(prefix):
            if finding not in findings:
                findings.append(finding)
        for quote in captured_documents(prefix):
            if quote not in documents:
                documents.append(quote)

    def source(raw):
        matches = [
            finding
            for finding in findings
            if hashlib.sha256(
                json.dumps(
                    asdict(finding),
                    sort_keys=True,
                    default=_json_value,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf8")
            ).hexdigest()
            == raw["captured_identity"]
        ]
        if len(matches) != 1 or type(raw["text"]) is not str or not raw["text"]:
            raise ReviewRefused("A historical subject has no exact captured primary source")
        finding = matches[0]
        start = finding.span.index(raw["text"])
        return EvidenceSpan(raw["id"], finding, start, start + len(raw["text"]))

    def document(raw):
        matches = [
            row
            for row in documents
            if MatterDocumentSpan("captured", row, 0, len(row.text)).captured_identity
            == raw["captured_identity"]
        ]
        if len(matches) != 1 or type(raw["text"]) is not str or not raw["text"]:
            raise ReviewRefused("A historical subject has no exact captured document window")
        start = matches[0].text.index(raw["text"])
        return MatterDocumentSpan(raw["id"], matches[0], start, start + len(raw["text"]))

    premises = []
    for raw in payload["premises"]:
        fact = matter.fact(raw["id"])
        if fact is None or not same_json_value(
            json.loads(json.dumps(asdict(fact), default=_json_value)), raw
        ):
            raise ReviewRefused("A historical subject lost its exact attributed premise owner")
        premises.append(fact)
    package = EvidencePackage(
        payload["id"],
        payload["claim"],
        tuple(source(row) for row in payload["sources"]),
        tuple(premises),
        tuple(source(row) for row in payload["contrary_material"]),
        tuple(payload["dependencies"]),
        decisive=payload["decisive"],
        documents=tuple(document(row) for row in payload["case_documents"]),
        document_contrary=tuple(document(row) for row in payload["contrary_documents"]),
    )
    if type(payload["decisive"]) is not bool or not same_json_value(
        json.loads(json.dumps(package.payload(), default=_json_value)), payload
    ):
        raise ReviewRefused("A historical verifier prompt changed its complete package contract")
    return package


def recorded_input_bindings(outcome, saved, matter, log, kind):
    """Reuse the canonical producer, with historical membership not legal currentness.

    These callbacks mean only that these exact bytes/generations were already
    actually captured at this review checkpoint. They are private historical
    association checks and cannot supply current calculator/display authority.
    """
    from nm.Archives.legal_brain.reason.working_record import WorkingRecordOwner
    from nm.Archives.legal_brain.retrieve.tool_sources import findings_from_envelope

    sources, windows = [], []
    for prefix in recorded_source_prefixes(outcome.record, saved, matter, log):
        for event in prefix.events:
            for envelope in source_envelopes_from_event(event):
                generation = envelope.receipt.get("source_version")
                sources.extend(
                    (finding, generation) for finding in findings_from_envelope(envelope)
                )
                windows.extend(
                    (row, generation) for row in envelope.data.get("captured_windows", [])
                )

    def captured_source(finding, generation):
        return any(
            same_json_value(finding.as_record(), row.as_record())
            and same_json_value(generation, version)
            for row, version in sources
        )

    def captured_window(window, generation):
        return any(
            same_json_value(window, row) and same_json_value(generation, version)
            for row, version in windows
        )

    source_owner = WorkingRecordOwner(
        source_current=captured_source, window_current=captured_window
    )
    if kind == "limitation":
        from nm.Archives.legal_brain.procedure.reviewed_limitation_selection import (
            prepare_limitation_selections,
        )

        generations = {
            row.payload["receipt"]["receipt"]["source_generation"]
            for row in outcome.record.events
            if row.kind is StepKind.TOOL_RETURNED
            and row.payload["receipt"].get("tool") == "propose_limitation_selection"
        }
        if len(generations) != 1:
            raise ReviewRefused("Historical limitation inputs have no sole captured generation")
        return prepare_limitation_selections(
            outcome,
            matter,
            source_generation=next(iter(generations)),
            source_current=captured_source,
        )
    if kind == "interest":
        from nm.Archives.legal_brain.procedure.reviewed_interest_selection import InterestSelectionOwner

        return InterestSelectionOwner(source_owner=source_owner).candidates(outcome, matter)
    if kind == "fee":
        from nm.Archives.legal_brain.procedure.reviewed_fee_selection import FeeSelectionOwner

        return FeeSelectionOwner(source_owner=source_owner).candidates(outcome, matter)
    raise ReviewRefused("A continuation kind has no actual registered conditional-input producer")
