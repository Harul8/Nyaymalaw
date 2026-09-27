"""Exact current interaction subjects, not fabricated legal evidence packages.

The terminal kind describes what the author proposed, not what the words mean.
Only supplied/admitted material and actual captured source windows are available
to the independent wording owner. A source-free acknowledgement needs no fake
Finding. Documents remain extracted words, never established case facts.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass

from nm.legal_brain.common.principles_port import PrinciplesPort
from nm.legal_brain.communicate.preview_display import displayed_questions
from nm.legal_brain.communicate.register_contracts import PEER
from nm.legal_brain.orchestrate.loop_contracts import LoopOutcome, StepKind, StopReason, digest
from nm.legal_brain.reason.matter_support import MatterDocumentSpan, captured_documents
from nm.legal_brain.retrieve.evidence_port import Finding, SourceKind
from nm.legal_brain.retrieve.tool_sources import findings_from_envelope, source_envelopes_from_event
from nm.legal_brain.understand.brain_context import require_recorded_source
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.legal_brain.verify.verifier import EvidencePackage
from nm.work_the_file.file_mutation_contracts import neutral

SourceCurrent = Callable[[Finding, str], bool]
WindowCurrent = Callable[[dict, str], bool]
MAX_INTERACTION_CHARACTERS = 16000


@dataclass(frozen=True)
class InteractionSubject:
    """Immutable JSON binds the exact words, instruction, scope and sources."""

    payload_json: str

    def __post_init__(self):
        if not isinstance(self.payload_json, str) or not self.payload_json.strip():
            raise ValueError("An interaction subject needs its exact supplied material")
        raw = json.loads(self.payload_json)
        if (not isinstance(raw, dict) or not isinstance(raw.get("proposed_text"), str)
                or not raw["proposed_text"].strip()
                or not 0 < len(raw["proposed_text"]) <= MAX_INTERACTION_CHARACTERS
                or not isinstance(raw.get("original_instruction"), str)
                or not raw["original_instruction"].strip()
                or raw.get("kind") not in {StopReason.QUESTION.value,
                                           StopReason.CONVERSATION.value}):
            raise ValueError("An interaction subject needs bounded exact text and instruction")

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def identity(self):
        return digest(self.payload)

    @property
    def text(self):
        return self.payload["proposed_text"]

    @property
    def sources(self):
        return {row["id"]: row["text"] for row in self.payload["quote_sources"]}


def _terminal(outcome: LoopOutcome) -> str:
    if not outcome.record.terminal:
        raise ReviewRefused("Interaction wording lacks its actual terminal record")
    stop = outcome.record.events[-1].payload
    if (stop.get("reason") != outcome.reason.value
            or stop.get("proposal") != outcome.proposal
            or stop.get("budget") != outcome.budget.as_dict()
            or stop.get("released") is not False):
        raise ReviewRefused("The interaction differs from its exact saved terminal and budget")
    proposal = outcome.proposal
    if outcome.reason is StopReason.QUESTION:
        if set(proposal) != {"question"}:
            raise ReviewRefused("A question cannot add unchecked answer or authority fields")
        text = proposal["question"]
    elif outcome.reason is StopReason.CONVERSATION:
        if (set(proposal) != {"text", "assessment_state", "client_ready", "released"}
                or proposal["assessment_state"] != "not_assessed"
                or proposal["client_ready"] is not False or proposal["released"] is not False):
            raise ReviewRefused("A conversational label cannot carry its own assessment")
        text = proposal["text"]
    else:
        raise ReviewRefused("Only a saved question or conversational proposal is an interaction")
    if (not isinstance(text, str) or not text.strip()
            or len(text) > MAX_INTERACTION_CHARACTERS):
        raise ReviewRefused("Interaction words must be exact, nonblank and bounded")
    return text


class InteractionSubjectOwner:
    """Installation-owned rebuilding callback for the shared saved transport."""

    def __init__(self, *, principles: PrinciplesPort,
                 source_current: SourceCurrent | None = None,
                 window_current: WindowCurrent | None = None):
        if not isinstance(principles, PrinciplesPort):
            raise ValueError("An interaction review needs the versioned principles owner")
        if source_current is not None and not callable(source_current):
            raise ValueError("Current source windows need their actual source owner")
        if window_current is not None and not callable(window_current):
            raise ValueError("An unassessed legal window needs its current exact read owner")
        self.principles, self.source_current = principles, source_current
        self.window_current = window_current

    def packages(self, outcome, matter) -> tuple[EvidencePackage, ...]:
        """Actual document supports only; this does not invoke legal preflight."""
        self.build(outcome, matter)
        windows = captured_documents(outcome.record)
        if not windows:
            return ()
        return (EvidencePackage("interaction_documents", _terminal(outcome), (),
            documents=tuple(MatterDocumentSpan(f"document_{index}", quote, 0, len(quote.text))
                            for index, quote in enumerate(windows))),)

    def build(self, outcome, matter, *, include_work_receipts=False) -> InteractionSubject:
        text = _terminal(outcome)
        brief = require_recorded_source(outcome.record, matter)
        principles = self.principles.load()
        if principles.version != outcome.record.identity.principles_version:
            raise ReviewRefused("The interaction principles changed since the supplied proposal")
        starts = [event.payload for event in outcome.record.events
                  if event.kind is StepKind.MODEL_STARTED]
        if not starts or not isinstance(starts[0].get("prompt", {}).get("user"), str):
            raise ReviewRefused("The interaction lacks its original authenticated instruction")
        original = starts[0]["prompt"]["user"]
        if not original.strip():
            raise ReviewRefused("An empty original instruction cannot be independently reviewed")
        source_rows, captured, read_windows = [], [], []
        for event in outcome.record.events:
            for envelope in source_envelopes_from_event(event):
                generation = envelope.receipt.get("source_version")
                for finding in findings_from_envelope(envelope):
                    pair = (finding, generation)
                    if pair in captured:
                        continue
                    if (not isinstance(generation, str) or not generation.strip()
                            or self.source_current is None
                            or self.source_current(finding, generation) is not True):
                        raise ReviewRefused("The interaction law window is not currently readable")
                    captured.append(pair)
                    source_rows.append({"id": f"law_{len(source_rows)}",
                        "generation": generation, "finding": neutral(asdict(finding))})
                windows = envelope.data.get("captured_windows", [])
                if not isinstance(windows, list):
                    raise ReviewRefused("Actual legal reader windows need their saved population")
                for window in windows:
                    if (not isinstance(window, dict) or set(window) != {
                            "locator", "text", "source_kind", "source_version", "legal_metadata",
                            "missing"} or window.get("legal_metadata") != "not_assessed"
                            or any(not isinstance(window[name], str) or not window[name].strip()
                                   for name in ("locator", "text", "source_kind", "source_version"))
                            or window["source_kind"] not in {kind.value for kind in SourceKind}
                            or not isinstance(window["missing"], list) or not window["missing"]
                            or any(not isinstance(value, str) or not value.strip()
                                   for value in window["missing"])):
                        raise ReviewRefused("A raw source window cannot acquire invented metadata")
                    pair = (window, generation)
                    if pair in read_windows:
                        continue
                    already_current = any(
                        finding.locator == window["locator"]
                        and finding.span == window["text"]
                        and finding.source_kind.value == window["source_kind"]
                        and original_generation == generation
                        for finding, original_generation in captured)
                    if (not already_current and (not isinstance(generation, str)
                            or not generation.strip() or self.window_current is None
                            or self.window_current(dict(window), generation) is not True)):
                        raise ReviewRefused("The raw legal window has no current exact read owner")
                    read_windows.append(pair)
        documents = tuple(MatterDocumentSpan(f"document_{index}", quote, 0, len(quote.text))
            for index, quote in enumerate(captured_documents(outcome.record)))
        file = json.loads(brief.text)["data"]
        # Journal appends change transaction versions, not the semantic subject.
        # Private proposal/check logs are not prior advocate-visible questions.
        file.pop("version", None)
        file.pop("loop_records", None)
        file.pop("checklist_context_as_of", None)
        questions = [neutral(asdict(row)) for row in matter.asked
                     if row.thread is None or row.thread in brief.selected_issue_ids]
        shown = displayed_questions(matter, before_version=outcome.record.identity.matter_version,
                                    selected_issue_ids=brief.selected_issue_ids)
        quote_sources = [
            {"id": "original_instruction", "text": original},
            {"id": "proposed_text", "text": text},
            {"id": "principles", "text": principles.text},
            {"id": "peer_register", "text": PEER},
            *[{"id": f"fact:{span.source_id}", "text": span.verbatim}
              for span in brief.sources],
            *[{"id": f"asked:{index}", "text": row["text"]}
              for index, row in enumerate(questions)],
            *[{"id": f"preview_question:{row['turn_id']}", "text": row["text"]}
              for row in shown],
            *[{"id": row["id"], "text": row["finding"]["span"]} for row in source_rows],
            *[{"id": f"window_{index}", "text": window["text"]}
              for index, (window, _) in enumerate(read_windows)],
            *[{"id": span.id, "text": span.text} for span in documents],
        ]
        if len({row["id"] for row in quote_sources}) != len(quote_sources):
            raise ReviewRefused("The interaction contains ambiguous source identities")
        payload = {
            "parent": outcome.record.events[-1].fingerprint,
            "parent_identity": outcome.record.identity.as_dict(),
            "kind": outcome.reason.value, "proposed_text": text,
            "original_instruction": original, "checked_file": file,
            "checked_snapshot": brief.snapshot_id,
            "selected_issue_ids": list(brief.selected_issue_ids),
            "principles_version": principles.version,
            "delivered_questions": questions,
            "displayed_private_questions": list(shown),
            "law_windows": source_rows,
            "unassessed_legal_windows": [{"id": f"window_{index}", "generation": generation,
                "window": window} for index, (window, generation) in enumerate(read_windows)],
            "documents": [span.payload() for span in documents],
            "quote_sources": quote_sources,
        }
        if include_work_receipts:
            from nm.legal_brain.orchestrate.work_receipts import work_receipts

            work = work_receipts(outcome.record)
            payload["work_receipts"] = work
            quote_sources.append({"id": "work_receipts", "text": json.dumps(
                work, sort_keys=True, ensure_ascii=False, allow_nan=False)})
        return InteractionSubject(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                              allow_nan=False, separators=(",", ":")))
