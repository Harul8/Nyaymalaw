"""One capture owner for trusted source readers, never model-authored evidence.

An exact text read is not a legal Finding. Missing attribution, validity,
binding and treatment stay visible; only the existing owners can establish
them. Typed primary reads retain their complete Findings without synthesis.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

from nm.core.tools import Assessment, Availability, Effect, ToolEnvelope, ToolKind, ToolOutcome
from nm.domain.loop import StepKind
from nm.ports.evidence import (
    Binding,
    Coverage,
    EvidenceResult,
    Finding,
    SourceDocument,
    SourceKind,
    Treatment,
    kind_for_corpus_label,
)
from nm.ports.search import Paragraph


@dataclass(frozen=True)
class SourceCapture:
    findings: tuple[Finding, ...] = ()
    windows: tuple[dict, ...] = ()

    @property
    def locators(self):
        return tuple(dict.fromkeys((*[row.locator for row in self.findings],
                                    *[row["locator"] for row in self.windows])))


def _captured_findings(data, receipt) -> tuple[Finding, ...]:
    rows, locators = data.get("findings", []), receipt.get("locators")
    if (not isinstance(rows, list) or not isinstance(locators, list)
            or any(not isinstance(value, str) or not value.strip() for value in locators)):
        raise ValueError("Captured sources need their exact finding and locator populations")
    found = []
    for raw in rows:
        finding = Finding.from_record(raw)
        if finding.locator not in locators:
            raise ValueError("A captured finding has no source-read receipt")
        if finding not in found:
            found.append(finding)
    return tuple(found)


def findings_from_envelope(envelope: ToolEnvelope) -> tuple[Finding, ...]:
    """The same capture decoder for actual typed returned source contracts."""
    if not isinstance(envelope, ToolEnvelope):
        raise ValueError("A capture needs an actual typed tool result")
    if envelope.kind is not ToolKind.SOURCE:
        return ()
    return _captured_findings(envelope.data, envelope.receipt)


def _source_envelope(raw) -> ToolEnvelope:
    if not isinstance(raw, dict) or set(raw) != {field.name for field in fields(ToolEnvelope)}:
        raise ValueError("A saved source needs its complete original tool envelope")
    values = dict(raw)
    for key, kind in (("kind", ToolKind), ("outcome", ToolOutcome),
                      ("availability", Availability), ("assessment", Assessment),
                      ("effect", Effect)):
        values[key] = kind(values[key])
    return ToolEnvelope(**values)


def source_envelopes_from_event(event) -> tuple[ToolEnvelope, ...]:
    """Actual direct or delegated reads with their ORIGINAL source generations.

    The delegated aggregate digest identifies a set, not a corpus generation.
    Only its saved child dispatch/return transcript supplies the original reads.
    An arbitrary nested dictionary cannot promote findings or primary reads.
    """
    if event.kind is not StepKind.TOOL_RETURNED:
        return ()
    parent = _source_envelope(event.payload["receipt"])
    if parent.kind is not ToolKind.SOURCE:
        return ()
    trace = event.payload.get("child_transcript")
    if trace is None:
        return (parent,)
    if (not isinstance(trace, (tuple, list)) or event.payload.get("child_released") is not False
            or type(event.payload.get("child_steps")) is not int
            or event.payload["child_steps"] != sum(
                isinstance(row, dict) and row.get("kind") in {"model_started", "tool_started"}
                for row in trace)):
        raise ValueError("Delegated source capture needs its exact attempted child population")
    captured, pending = [], None
    for row in trace:
        if not isinstance(row, dict):
            raise ValueError("A saved child event needs its explicit typed record")
        if row.get("kind") == "tool_started":
            if pending is not None or not isinstance(row.get("call"), dict):
                raise ValueError("A child source cannot skip its actual invocation")
            from nm.ports.model import ToolCall

            pending = ToolCall(**row["call"])
        elif row.get("kind") == "tool_returned":
            result = _source_envelope(row["receipt"])
            if pending is None or pending.name != result.tool:
                raise ValueError("A returned child source differs from its actual invocation")
            pending = None
            if result.kind is ToolKind.SOURCE:
                captured.append(result)
        elif row.get("kind") == "refused":
            pending = None  # A recorded failed invocation grants no source.
    if pending is not None:
        raise ValueError("A completed child source transcript has an unknown pending read")
    return tuple(captured)


def findings_from_record(record, *, source_version: str | None = None) -> tuple[Finding, ...]:
    """Read only actual SOURCE envelopes from an already sealed tool journal.

    This admits no recursively discovered ``findings`` key and promotes no raw
    document window. A version filter is an exact capture-generation selection,
    not a claim that an external corpus was freshly checked.
    """
    if source_version is not None and (
            not isinstance(source_version, str) or not source_version.strip()):
        raise ValueError("A source-generation selection needs its actual nonblank identity")
    found = []
    for event in record.events:
        if event.kind is not StepKind.TOOL_RETURNED:
            continue
        for envelope in source_envelopes_from_event(event):
            if (source_version is not None
                    and envelope.receipt.get("source_version") != source_version):
                continue
            for finding in findings_from_envelope(envelope):
                if finding not in found:
                    found.append(finding)
    return tuple(found)


def capture_primary(result: EvidenceResult) -> SourceCapture:
    """Only an actual evidence-port read supplies a legal Finding contract."""
    if not isinstance(result, EvidenceResult):
        raise ValueError("primary capture requires the typed evidence owner result")
    if result.coverage is Coverage.NOT_ASSESSED and result.findings:
        raise ValueError("an unassessed source read cannot establish captured findings")
    return SourceCapture(result.findings)


def combine_captures(*captures: SourceCapture) -> SourceCapture:
    findings, windows = [], []
    for capture in captures:
        if not isinstance(capture, SourceCapture):
            raise ValueError("source captures have one explicit typed owner")
        for finding in capture.findings:
            if finding not in findings:
                findings.append(finding)
        for window in capture.windows:
            if window not in windows:
                windows.append(dict(window))
    return SourceCapture(tuple(findings), tuple(windows))


def _window(locator, text, *, kind, source_version, missing):
    if any(not isinstance(value, str) or not value.strip()
           for value in (locator, text, source_version)):
        raise ValueError("a captured source window needs its exact text, locator and version")
    if not isinstance(kind, SourceKind) or not missing:
        raise ValueError("an unassessed window names its source kind and missing metadata")
    return {"locator": locator, "text": text, "source_kind": kind.value,
            "source_version": source_version, "legal_metadata": "not_assessed",
            "missing": list(missing)}


def capture_paragraph(paragraph: Paragraph, *, index: str,
                      source_version: str) -> SourceCapture:
    if not isinstance(paragraph, Paragraph):
        raise ValueError("paragraph capture requires the exact passage owner result")
    missing = ("binding jurisdiction and rule", "subsequent treatment", "governing date")
    window = _window(paragraph.locator, paragraph.text, kind=SourceKind.AUTHORITY,
                     source_version=source_version, missing=missing)
    attribution = kind_for_corpus_label(paragraph.para_type)
    window["paragraph_kind"] = attribution.value
    if not attribution.attributable:
        window["missing"].append("a paragraph attributable to the court's decision")
        return SourceCapture(windows=(window,))
    # Preserve actual attribution, but never infer binding from the court name
    # or call a case clean because no treatment read was performed.
    finding = Finding(
        proposition="The located passage has not been assessed for legal support.",
        source_kind=SourceKind.AUTHORITY, ref=paragraph.case_name,
        span=paragraph.text, locator=paragraph.locator, store=index,
        binding=Binding.NOT_ASSESSED, binding_for="The applicable forum is not established.",
        binding_reason="This paragraph reader did not assess binding status.",
        supports=None, para_kind=attribution,
        treatment=Treatment.not_checked("This paragraph reader did not assess later treatment."),
        origin=paragraph.origin,
    )
    return SourceCapture((finding,), (window,))


def capture_document(document: SourceDocument, *, kind: SourceKind) -> SourceCapture:
    if not isinstance(document, SourceDocument) or not isinstance(kind, SourceKind):
        raise ValueError("document capture requires its typed owner and actual source kind")
    if document.state != "read":
        return SourceCapture()
    missing = (("validity window", "governing date", "semantic support")
               if kind is SourceKind.PROVISION else
               ("paragraph attribution", "binding jurisdiction and rule", "subsequent treatment",
                "governing date", "semantic support"))
    return SourceCapture(windows=tuple(
        _window(locator, text, kind=kind, source_version=document.snapshot_id, missing=missing)
        for locator, text in document.segments))


def source_envelope(name: str, version: str, index: str, source_version: str,
                    locators, data: dict, *, available=True, partial=False,
                    assessed=False, reason="", capture: SourceCapture | None = None,
                    primary_reads: tuple[EvidenceResult, ...] = ()):
    """The only source envelope writer; captures come from named typed readers.

    No recursive dictionary walk is permitted. A guide, search hit or an
    arbitrary payload field named ``findings`` cannot promote itself.
    """
    if not isinstance(data, dict) or {"findings", "captured_windows"} & data.keys():
        raise ValueError("source capture fields belong to the typed source owner")
    if any(not isinstance(row, EvidenceResult) for row in primary_reads):
        raise ValueError("a captured primary read comes from the typed evidence owner")
    capture = combine_captures(capture or SourceCapture(),
                               *(capture_primary(row) for row in primary_reads))
    if not isinstance(capture, SourceCapture):
        raise ValueError("source captures have one explicit typed owner")
    if not available and (data or capture.findings or capture.windows):
        raise ValueError("an unavailable source read cannot carry captured material")
    value = dict(data)
    if capture.findings:
        value["findings"] = [row.as_record() for row in capture.findings]
    if capture.windows:
        value["captured_windows"] = [dict(row) for row in capture.windows]
    if assessed and (capture.windows or
                     any(not finding.usable for finding in capture.findings)):
        raise ValueError("unusable captures cannot acquire a supported envelope assessment")
    held = list(dict.fromkeys((*locators, *capture.locators)))
    receipt = {"index": index, "source_version": source_version, "locators": held}
    if primary_reads:
        # NO_RESULTS cannot carry findings data, but an actually searched miss
        # still preserves the original coverage/missing/index/assumption.
        receipt["primary_reads"] = [asdict(row) for row in primary_reads]
    return ToolEnvelope(
        name, version, ToolKind.SOURCE,
        (ToolOutcome.FAILED if not available else
         ToolOutcome.RESULTS if value else ToolOutcome.NO_RESULTS),
        (Availability.UNAVAILABLE if not available else
         Availability.PARTIAL if partial else Availability.AVAILABLE),
        Assessment.SUPPORTED if assessed else Assessment.NOT_ASSESSED,
        receipt,
        value, reason,
    )
