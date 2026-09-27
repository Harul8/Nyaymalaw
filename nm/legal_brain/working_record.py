"""Receipt-owned work inventory and exact-source private explanation candidates.

The lead may annotate actual work; it cannot mark that work relevant, complete
or independently checked. Reconstructing the saved tools is the only candidate
reader. Nothing here releases a conversational reply or a normal advice turn.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from nm.legal_brain.brain_context import ContextRefused, linked_fact_ids, require_recorded_source
from nm.legal_brain.brain_release import IndependentReview, ReviewRefused, ReviewService
from nm.legal_brain.evidence_port import SourceKind
from nm.legal_brain.loop_contracts import StepKind, digest
from nm.legal_brain.matter_support import MatterDocumentSpan, captured_documents
from nm.legal_brain.requirements_contracts import Requirement
from nm.legal_brain.requirements_contracts import key as requirement_key
from nm.legal_brain.tool_sources import (
    findings_from_envelope,
    source_envelopes_from_event,
    tool_envelope_from_record,
)
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    Effect,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.legal_brain.verifier import EvidencePackage, EvidenceSpan
from nm.legal_brain.work_receipts import work_receipts
from nm.legal_brain.working_record_contracts import (
    BRIEF_AREAS,
    AnalysisAnnotation,
    AnalysisArea,
    CompletenessItem,
    Disposition,
    ReferenceKind,
    WorkingCompleteness,
    WorkingInventory,
    WorkReference,
)
from nm.shared.model_port import SchemaViolation, require_schema
from nm.work_the_file.file_mutation import assertion_identity, dispute_identity
from nm.work_the_file.file_mutation_contracts import neutral
from nm.work_the_file.original_instruction import (
    InstructionRefused,
    prior_instructions,
    read_original_instruction,
)

VERSION = "source-owned-working-record-v1"
READ_TOOL = "read_working_inventory"
PROPOSE_TOOL = "propose_working_record"
MAX_INVENTORY_CHARACTERS = 256000
_STRING = {"type": "string", "minLength": 1}
REFERENCE_SCHEMA = object_schema(
    {
        "kind": {"type": "string", "enum": [kind.value for kind in ReferenceKind]},
        "id": _STRING,
        "identity": {"type": "string", "minLength": 64},
    }
)
_STRINGS = {"type": "array", "maxItems": 100, "items": _STRING}
ANNOTATION_SCHEMA = object_schema(
    {
        "id": {"type": "string", "minLength": 1},
        "thread_id": {"type": ["string", "null"]},
        "area": {"type": "string", "enum": [area.value for area in AnalysisArea]},
        "disposition": {"type": "string", "enum": [value.value for value in Disposition]},
        "analysis": _STRING,
        "reason": _STRING,
        "references": {"type": "array", "minItems": 1, "maxItems": 100, "items": REFERENCE_SCHEMA},
        "sources": {
            "type": "array",
            "maxItems": 100,
            "items": object_schema(
                {"reference_id": _STRING, "quote": _STRING, "contrary": {"type": "boolean"}}
            ),
        },
        "fact_ids": _STRINGS,
        "need_ids": _STRINGS,
        "depends_on": _STRINGS,
    }
)
PROPOSAL_SCHEMA = object_schema(
    {
        "inventory_identity": _STRING,
        "entries": {"type": "array", "minItems": 1, "maxItems": 100, "items": ANNOTATION_SCHEMA},
    }
)
_CONTROLS = (
    "test_working_candidates_are_actual_tools_not_author_pass_flags",
    "test_missing_needed_work_stays_unassessed_and_narrow_scope_is_proportionate",
)


def _wire(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )


def area_id(thread_id, area):
    return f"area:{thread_id or 'whole_request'}:{area.value}"


def receipt_progress(record):
    """Plain execution-only lines, never copied queries, results or model prose.

    A source read with no recorded dispute target remains shared progress. An
    author cannot make it dispute-specific by writing a narrative. The protected
    original journal retains every attempted operation, including reader and
    candidate operations; completed reads are not claims that the law applies.
    """
    known = (
        set(
            record.events[0]
            .payload.get("context", {})
            .get("brief", {})
            .get("selected_issue_ids", [])
        )
        if record.events
        else set()
    )
    labels = {
        "read_provision": "Read a provision; its application still needs assessment.",
        "read_authority": "Read an authority passage; its application still needs assessment.",
        "search_authorities": "Searched for authority material.",
        "quote_matter": "Read exact words from a supplied document.",
        "search_matter_text": "Searched supplied documents.",
        "create_dispute": "Recorded a separate dispute from the supplied account.",
        "record_requirements": "Recorded source-linked needs for independent assessment.",
        "record_requirement_answer": "Recorded a response for independent checklist review.",
        "record_grounded_file_reading": "Recorded a source-linked reading of the account.",
        READ_TOOL: "Read the current private work inventory.",
        PROPOSE_TOOL: "Recorded a private explanation candidate; checks remain.",
    }
    rows = []
    for attempt in work_receipts(record)["attempts"]:
        call, result = attempt["call"], attempt.get("result", {})
        args, data = call["arguments"], result.get("data", {})
        if call["name"] == "create_dispute" and isinstance(data.get("thread_id"), str):
            known.add(data["thread_id"])
        target = data.get("thread_id", args.get("thread_id"))
        targets = [target] if isinstance(target, str) else args.get("thread_ids", [])
        thread_ids = tuple(value for value in targets if value in known)
        if attempt["state"] != "returned":
            label = (
                "The material check was refused."
                if attempt["state"] == "refused"
                else "The attempted material check has no confirmed completion."
            )
        elif result.get("outcome") == ToolOutcome.FAILED.value:
            label = "The attempted material check failed."
        elif result.get("availability") == Availability.UNAVAILABLE.value:
            label = "The requested material was unavailable."
        elif result.get("outcome") == ToolOutcome.NO_RESULTS.value:
            label = "The completed material check returned no result; coverage is not inferred."
        elif result.get("availability") == Availability.PARTIAL.value:
            label = "Only part of the requested material was available."
        else:
            label = labels.get(
                call["name"],
                {
                    ToolKind.SOURCE.value: (
                        "Recorded a source read; its meaning still needs assessment."
                    ),
                    ToolKind.MATTER.value: "Recorded a scoped file operation.",
                    ToolKind.COMPUTATION.value: "Recorded a calculation and its stated limits.",
                }.get(result.get("kind"), "Recorded a private control operation."),
            )
        rows.append(
            {
                "event_identity": attempt["event_identity"],
                "event_sequence": attempt["event_sequence"],
                "thread_ids": thread_ids,
                "label": label,
                "state": attempt["state"],
                "execution_only": True,
                "explanation_checked": False,
                "working_not_advice": True,
            }
        )
    return tuple(rows)


def exact_reference(inventory, raw):
    """No pointer aliases: a reference names one complete typed owner value."""
    try:
        require_schema(raw, REFERENCE_SCHEMA)
        reference = WorkReference(ReferenceKind(raw["kind"]), raw["id"], raw["identity"])
        actual = inventory.references.get(reference.id)
        if actual is None or actual["reference"] != reference.as_dict():
            raise ValueError("The reference differs from its complete current owner value")
        return reference
    except (SchemaViolation, KeyError, TypeError, ValueError) as exc:
        raise ReviewRefused(
            "A working judgment cites no exact current typed work reference"
        ) from exc


def _current_thread_scope(record, matter, original):
    """Extend only a sealed whole-file admission through actual committed writes.

    The initial brief is a source snapshot, not a forever-frozen list of newly
    recorded disputes. A current arbitrary thread or an author's unassessed
    flag cannot widen the captured task. Failed/prepared-but-uncommitted writes
    contribute no new scope. Identity construction belongs to the writer.
    """
    parents = [
        row for row in matter.loop_records if row.identity.turn_id == record.identity.turn_id
    ]
    if (
        len(parents) != 1
        or parents[0].identity != record.identity
        or parents[0].events[: len(record.events)] != record.events
    ):
        raise ReviewRefused("Working scope lacks its exact owned saved parent prefix")
    saved = record.events[0].payload
    admitted = set(saved["context"]["brief"]["selected_issue_ids"])
    if saved.get("scope_identity") != digest({"requested_issue_ids": []}):
        return admitted
    current = {thread.id for thread in matter.threads}
    wanted, proven = current - admitted, set()
    if not wanted:
        return admitted
    events = {event.fingerprint: event for event in record.events}
    from nm.work_the_file.write_tools import PRIOR_VERSION
    from nm.work_the_file.write_tools import VERSION as WRITE_VERSION

    for attempt in work_receipts(record)["attempts"]:
        call = attempt["call"]
        name, args = call["name"], call["arguments"]
        if name not in {"create_dispute", "record_prior_instruction"}:
            continue
        if name == "record_prior_instruction" and args.get("new_dispute_label") is None:
            continue
        if attempt["state"] != "returned":
            continue
        returned = events[attempt["outcome_identity"]]
        result = tool_envelope_from_record(returned.payload["receipt"])
        data, receipt = result.data, result.receipt
        ident = data.get("thread_id")
        if ident not in wanted:
            continue
        words, source_turn, label = original.text, record.identity.turn_id, args.get("label")
        if name == "record_prior_instruction":
            candidates = [
                row
                for row in prior_instructions(
                    matter,
                    actor=record.identity.advocate_id,
                    mode=record.identity.mode,
                    before_version=record.identity.matter_version,
                )
                if row.record.identity.turn_id == args.get("instruction_turn_id")
            ]
            if len(candidates) != 1:
                raise ReviewRefused("A new working dispute lost its actual prior input owner")
            source = candidates[0]
            if (
                source.original.state != "recorded"
                or source.record.events[0].payload.get("scope_identity")
                != digest({"requested_issue_ids": []})
                or data.get("instruction_identity") != source.original.text_identity
                or data.get("instruction_provenance") != source.original.provenance
                or data.get("source_parent_identity") != source.record.identity.fingerprint
                or data.get("source_journal_identity") != source.record.events[-1].fingerprint
                or data.get("instruction_turn_id") != source.record.identity.turn_id
            ):
                raise ReviewRefused("A new working dispute changed its earlier source admission")
            words, source_turn, label = (
                source.original.text,
                source.record.identity.turn_id,
                args["new_dispute_label"],
            )
        quoted = args.get("quoted")
        thread = matter.thread(ident)
        fact_id = assertion_identity(matter.id, source_turn, words)
        fact = matter.fact(fact_id)
        mutation = returned.payload.get("mutation_identity")
        if (
            not isinstance(label, str)
            or not label.strip()
            or not isinstance(quoted, str)
            or not quoted.strip()
            or quoted not in words
            or result.tool != name
            or result.kind is not ToolKind.MATTER
            or result.version
            != (PRIOR_VERSION if name == "record_prior_instruction" else WRITE_VERSION)
            or result.outcome is not ToolOutcome.RESULTS
            or result.availability is not Availability.AVAILABLE
            or result.assessment is not Assessment.NOT_ASSESSED
            or result.effect is not Effect.CONTINUE
            or not isinstance(mutation, str)
            or len(mutation) != 64
            or any(char not in "0123456789abcdef" for char in mutation)
            or receipt.get("snapshot") != mutation
            or receipt.get("matter_id") != matter.id
            or receipt.get("matter_version")
            != (record.identity.matter_version + returned.sequence - 1)
            or not isinstance(returned.payload.get("checked_snapshot"), str)
            or data.get("operation") != name
            or "threads" not in data.get("changed_fields", [])
            or data.get("selected_span") != quoted
            or data.get("fact_id") != fact_id
            or ident != dispute_identity(matter.id, source_turn, quoted, label)
            or thread is None
            or thread.label != label
            or fact_id not in thread.chronology
            or fact is None
            or fact.statement != words
            or fact.exact_words != words
            or fact.provenance.kind != "advocate_statement"
            or fact.provenance.turn != source_turn
            or fact.provenance.span != words
        ):
            raise ReviewRefused("A new working dispute has no exact committed source-bound receipt")
        if ident in proven:
            raise ReviewRefused("A new working dispute repeats its source-bound creation")
        proven.add(ident)
    if proven != wanted:
        raise ReviewRefused("Whole-file working scope has unowned newly recorded disputes")
    return admitted | proven


class WorkingRecordOwner:
    """Build from the actual captured file and execution/source journals only."""

    def __init__(self, *, source_current=None, window_current=None):
        if source_current is not None and not callable(source_current):
            raise ValueError("Law currentness needs its actual source owner")
        if window_current is not None and not callable(window_current):
            raise ValueError("Raw source currentness needs its actual reader owner")
        self.source_current, self.window_current = source_current, window_current

    def _sources(self, record):
        findings, windows = {}, {}
        for event in record.events:
            for envelope in source_envelopes_from_event(event):
                generation = envelope.receipt.get("source_version")
                for finding in findings_from_envelope(envelope):
                    if (
                        not isinstance(generation, str)
                        or not generation.strip()
                        or self.source_current is None
                        or self.source_current(finding, generation) is not True
                    ):
                        raise ReviewRefused("Working law lacks its current exact source owner")
                    ident = "law:" + digest(neutral(asdict(finding)))
                    value = {"finding": neutral(asdict(finding)), "generation": generation}
                    if ident in findings and findings[ident][1] != value:
                        raise ReviewRefused("The same law window has ambiguous source generations")
                    findings[ident] = (finding, value)
                raw = envelope.data.get("captured_windows", [])
                if not isinstance(raw, list):
                    raise ReviewRefused("The complete captured reader population is unreadable")
                for window in raw:
                    required = {
                        "locator",
                        "text",
                        "source_kind",
                        "source_version",
                        "legal_metadata",
                        "missing",
                    }
                    if (
                        not isinstance(window, dict)
                        or not required <= set(window)
                        or set(window) - required - {"paragraph_kind"}
                        or any(
                            not isinstance(window[name], str) or not window[name].strip()
                            for name in ("locator", "text", "source_kind", "source_version")
                        )
                        or window["source_kind"] not in {kind.value for kind in SourceKind}
                        or window["legal_metadata"] != "not_assessed"
                        or not isinstance(window["missing"], list)
                        or not window["missing"]
                        or any(
                            not isinstance(value, str) or not value.strip()
                            for value in window["missing"]
                        )
                    ):
                        raise ReviewRefused("A captured source window lacks its exact words")
                    # Fully typed windows are already current above. Unassessed
                    # raw windows stay raw; no Finding is manufactured from them.
                    if (
                        any(
                            finding.span == window["text"]
                            and finding.locator == window.get("locator")
                            and finding.source_kind.value == window["source_kind"]
                            and value["generation"] == generation
                            for finding, value in findings.values()
                        )
                        and window["source_version"] == generation
                    ):
                        continue
                    if (
                        self.window_current is None
                        or self.window_current(dict(window), generation) is not True
                    ):
                        raise ReviewRefused("An unassessed working window has no current reader")
                    ident = "window:" + digest({"window": window, "generation": generation})
                    windows[ident] = {"window": window, "generation": generation}
        return findings, windows

    def build(self, record, matter) -> WorkingInventory:
        try:
            brief = require_recorded_source(record, matter)
            original = read_original_instruction(record)
            if original.state != "recorded":
                raise ReviewRefused("Working scope has no whole original authenticated request")
            selected = _current_thread_scope(record, matter, original)
            findings, windows = self._sources(record)
            references, needs = [], []

            def add(kind, ident, value, text, threads=(), *, need=True):
                reference = WorkReference(kind, ident, digest(value))
                references.append(
                    {
                        "reference": reference.as_dict(),
                        "value": value,
                        "text": text,
                        "thread_ids": sorted(threads),
                    }
                )
                if need:
                    needs.append(
                        {
                            "id": "need:" + ident,
                            "kind": kind.value,
                            "reference": reference.as_dict(),
                            "text": text,
                            "thread_ids": sorted(threads),
                        }
                    )

            add(ReferenceKind.INPUT, "original_instruction", original.as_dict(), original.text)
            threads = []
            for thread in matter.threads:
                if thread.id not in selected:
                    continue
                value = neutral(asdict(thread))
                add(ReferenceKind.THREAD, "thread:" + thread.id, value, thread.label, (thread.id,))
                threads.append({"id": thread.id, "label": thread.label})
                for raw in thread.requirements:
                    requirement = Requirement.restore(raw)
                    if requirement is None:
                        raise ReviewRefused("An unreadable needs list is not an empty clean list")
                    key = requirement_key(requirement)
                    value = {
                        "requirement": neutral(asdict(requirement)),
                        "outcome": neutral(thread.requirement_outcomes.get(key)),
                        "read_identity": thread.requirement_reads.get(requirement.locator),
                        "thread_id": thread.id,
                    }
                    add(
                        ReferenceKind.REQUIREMENT,
                        f"requirement:{thread.id}:{key}",
                        value,
                        requirement.need + "\n" + requirement.why + "\n" + requirement.span,
                        (thread.id,),
                    )
            # Use the same current chronology/correction owner as the brief.
            # Newly admitted assertions remain attributed/unconfirmed facts;
            # adding their exact register entries does not establish truth.
            visible = {
                fact_id
                for thread in matter.threads
                if thread.id in selected
                for fact_id in thread.chronology
            }
            if not matter.threads:
                visible = {fact.id for fact in matter.facts}
            visible = linked_fact_ids(neutral([asdict(fact) for fact in matter.facts]), visible)
            for fact in matter.facts:
                if fact.id in visible:
                    add(
                        ReferenceKind.FACT,
                        "fact:" + fact.id,
                        neutral(asdict(fact)),
                        fact.statement,
                        (
                            thread.id
                            for thread in matter.threads
                            if thread.id in selected and fact.id in thread.chronology
                        ),
                    )
            for ident, (finding, value) in findings.items():
                add(ReferenceKind.SOURCE, ident, value, finding.span)
            for ident, value in windows.items():
                add(ReferenceKind.SOURCE, ident, value, value["window"]["text"])
            for document in captured_documents(record):
                add(
                    ReferenceKind.DOCUMENT,
                    "document:" + digest(neutral(asdict(document))),
                    neutral(asdict(document)),
                    document.text,
                )
            # Our own reader/candidate tools and terminal proposals are not new
            # legal work. Exclusion prevents a recursive inventory identity; the
            # full protected parent journal still retains all those operations.
            from nm.legal_brain.early_independent_review import TOOL as EARLY_CHECK_TOOL

            work = work_receipts(record)
            attempts = [
                row
                for row in work["attempts"]
                if row.get("call", {}).get("name")
                not in {
                    READ_TOOL,
                    PROPOSE_TOOL,
                    EARLY_CHECK_TOOL,
                    "submit_answer",
                    "ask_advocate",
                    "propose_conversation",
                }
                and row.get("result", {}).get("effect", Effect.CONTINUE.value)
                == Effect.CONTINUE.value
            ]
            for row in attempts:
                args = row["call"]["arguments"]
                target = (
                    row.get("result", {}).get("data", {}).get("thread_id", args.get("thread_id"))
                )
                scoped = [target] if isinstance(target, str) else args.get("thread_ids", [])
                scoped = [value for value in scoped if value in selected]
                add(
                    ReferenceKind.WORK,
                    "work:" + row["event_identity"],
                    row,
                    _wire(row),
                    scoped,
                    need=False,
                )
            areas = [
                {"id": area_id(thread["id"], area), "thread_id": thread["id"], "area": area.value}
                for thread in threads
                for area in BRIEF_AREAS
            ]
            areas.extend(
                {"id": area_id(None, area), "thread_id": None, "area": area.value}
                for area in AnalysisArea
                if area not in BRIEF_AREAS
            )
            population = {
                "schema": 1,
                "parent_identity": record.identity.as_dict(),
                "file_snapshot": brief.snapshot_id,
                "original_instruction": original.text,
                "threads": threads,
                "references": references,
                "needs": needs,
                "areas": areas,
                "work": {"trust": work["trust"], "count": len(attempts), "attempts": attempts},
            }
            if len({row["reference"]["id"] for row in references}) != len(references):
                raise ReviewRefused("Working owner identities must be unique")
            text = _wire(population)
            if len(text) > MAX_INVENTORY_CHARACTERS:
                raise ReviewRefused("The complete working population exceeds its owned ceiling")
            return WorkingInventory(text)
        except (ContextRefused, InstructionRefused, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ReviewRefused):
                raise
            raise ReviewRefused("The whole working inventory cannot be reconstructed") from exc

    def bind(self, record, matter, proposal):
        """Exact candidate annotation fields become independently reviewable packages."""
        inventory = self.build(record, matter)
        try:
            require_schema(proposal, PROPOSAL_SCHEMA)
            if proposal["inventory_identity"] != inventory.identity:
                raise ReviewRefused("Working annotations refer to a changed exact inventory")
            rows = proposal["entries"]
            if len({row["id"] for row in rows}) != len(rows):
                raise ReviewRefused("A working proposal repeats annotation identities")
            findings, _ = self._sources(record)
            documents = {
                "document:" + digest(neutral(asdict(row))): row
                for row in captured_documents(record)
            }
            references = inventory.references
            needs = {row["id"]: row for row in inventory.payload["needs"]}
            thread_ids = {row["id"] for row in inventory.payload["threads"]}
            package_ids = {
                row["id"]: "work_"
                + digest({"turn": record.identity.turn_id, "annotation": row["id"]})
                for row in rows
            }
            bound, packages = [], []
            for row in rows:
                if (
                    not 0 < len(row["id"]) <= 100
                    or not row["id"].strip()
                    or any(
                        not row[name].strip() or len(row[name]) > 16000
                        for name in ("analysis", "reason")
                    )
                ):
                    raise ReviewRefused(
                        "Working explanation words and identity must be bounded and nonblank"
                    )
                if any(
                    len(set(row[name])) != len(row[name])
                    for name in ("fact_ids", "need_ids", "depends_on")
                ):
                    raise ReviewRefused("Repeated typed working identities add no coverage")
                thread_id = row["thread_id"]
                area = AnalysisArea(row["area"])
                if (
                    thread_id is not None
                    and thread_id not in thread_ids
                    or area in BRIEF_AREAS
                    and thread_id is None
                    or area not in BRIEF_AREAS
                    and thread_id is not None
                ):
                    raise ReviewRefused(
                        "An analysis annotation cannot merge or invent dispute scope"
                    )
                refs = tuple(exact_reference(inventory, raw) for raw in row["references"])
                if len({ref.id for ref in refs}) != len(refs):
                    raise ReviewRefused("Duplicate work references add no source coverage")
                ref_ids = {ref.id for ref in refs}
                for ref in refs:
                    scoped = references[ref.id]["thread_ids"]
                    if thread_id is not None and scoped and thread_id not in scoped:
                        raise ReviewRefused("A working annotation transfers another dispute's work")
                for need in row["need_ids"]:
                    if (
                        need not in needs
                        or needs[need]["reference"]["id"] not in ref_ids
                        or thread_id is not None
                        and needs[need]["thread_ids"]
                        and thread_id not in needs[need]["thread_ids"]
                    ):
                        raise ReviewRefused(
                            "An annotation covers no exact owned need in this dispute"
                        )
                spans, contrary, doc_spans, doc_contrary = [], [], [], []
                for index, source in enumerate(row["sources"]):
                    ident, quote = source["reference_id"], source["quote"]
                    if (
                        ident not in ref_ids
                        or not quote.strip()
                        or ident not in references
                        or quote not in references[ident]["text"]
                    ):
                        raise ReviewRefused(
                            "An explanation quotes no exact referenced source words"
                        )
                    if ident in findings:
                        finding = findings[ident][0]
                        start = finding.span.index(quote)
                        span = EvidenceSpan(f"source_{index}", finding, start, start + len(quote))
                        (contrary if source["contrary"] else spans).append(span)
                    elif ident in documents:
                        document = documents[ident]
                        start = document.text.index(quote)
                        span = MatterDocumentSpan(
                            f"source_{index}", document, start, start + len(quote)
                        )
                        (doc_contrary if source["contrary"] else doc_spans).append(span)
                    else:
                        raise ReviewRefused(
                            "Execution/input/raw windows cannot masquerade as legal sources"
                        )
                facts = []
                for ident in row["fact_ids"]:
                    fact = matter.fact(ident)
                    if (
                        fact is None
                        or "fact:" + ident not in ref_ids
                        or fact.superseded_by is not None
                    ):
                        raise ReviewRefused("A working premise needs its current exact scoped Fact")
                    facts.append(fact)
                if not spans and not doc_spans and not facts:
                    raise ReviewRefused(
                        "A finding explanation needs actual sources or file premises"
                    )
                if any(
                    value not in package_ids or value == row["id"] for value in row["depends_on"]
                ):
                    raise ReviewRefused(
                        "Working dependencies name no different candidate annotation"
                    )
                # Dispositions and reasons are inside the checked words, not
                # an unchecked UI suffix added after independent verification.
                claim = (
                    row["analysis"]
                    + "\nNM's judgment: "
                    + row["disposition"]
                    + ". Reason: "
                    + row["reason"]
                )
                package = EvidencePackage(
                    package_ids[row["id"]],
                    claim,
                    tuple(spans),
                    premises=tuple(facts),
                    contrary=tuple(contrary),
                    dependencies=tuple(package_ids[value] for value in row["depends_on"]),
                    documents=tuple(doc_spans),
                    document_contrary=tuple(doc_contrary),
                )
                bound.append(
                    AnalysisAnnotation(
                        row["id"],
                        thread_id,
                        area,
                        Disposition(row["disposition"]),
                        row["analysis"],
                        row["reason"],
                        refs,
                        tuple(row["need_ids"]),
                        package.id,
                        package.identity,
                    )
                )
                packages.append(package)
            return inventory, tuple(bound), tuple(packages)
        except (SchemaViolation, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ReviewRefused):
                raise
            raise ReviewRefused(
                "The working candidate is malformed or lacks owned support"
            ) from exc

    def candidates(self, outcome, matter):
        return self.candidates_for_record(outcome.record, matter)

    def candidates_for_record(self, record, matter):
        """Only actual admitted tool results; model messages/STOP flags are not writers."""
        calls, rows, inventory = {}, {}, self.build(record, matter)
        for event in record.events:
            if event.kind is StepKind.TOOL_STARTED:
                call = event.payload["call"]
                if call["name"] == PROPOSE_TOOL:
                    calls[call["call_id"]] = call
            elif event.kind is StepKind.TOOL_RETURNED:
                call = calls.get(event.payload.get("call_id"))
                if call is None:
                    continue
                envelope = tool_envelope_from_record(event.payload["receipt"])
                if (
                    envelope.tool != PROPOSE_TOOL
                    or envelope.version != VERSION
                    or envelope.kind is not ToolKind.CONTROL
                    or envelope.assessment is not Assessment.NOT_ASSESSED
                    or envelope.availability is not Availability.AVAILABLE
                    or envelope.outcome is not ToolOutcome.RESULTS
                    or envelope.effect is not Effect.CONTINUE
                    or envelope.receipt.get("operation") != PROPOSE_TOOL
                    or envelope.receipt.get("matter_id") != record.identity.matter_id
                    or envelope.receipt.get("turn_id") != record.identity.turn_id
                    or envelope.data
                    != {
                        "candidate": call["arguments"],
                        "independently_checked": False,
                        "released": False,
                    }
                    or envelope.receipt.get("inventory_identity")
                    != call["arguments"].get("inventory_identity")
                ):
                    raise ReviewRefused(
                        "The working candidate differs from its actual tool receipt"
                    )
                if call["arguments"]["inventory_identity"] != inventory.identity:
                    raise ReviewRefused(
                        "A candidate was written against an earlier work population"
                    )
                for row in call["arguments"]["entries"]:
                    if row["id"] in rows and rows[row["id"]] != row:
                        raise ReviewRefused("An annotation has ambiguous saved candidate versions")
                    rows[row["id"]] = row
        if not rows:
            return inventory, (), ()
        # Rebinding today's exact values invalidates corrections, changed
        # requirements, missing work or source generations; no stored PASS wins.
        return self.bind(
            record,
            matter,
            {"inventory_identity": inventory.identity, "entries": list(rows.values())},
        )

    def packages(self, outcome, matter):
        """Trusted current-subject callback for SavedCheckReader, including empty narrow work."""
        return self.candidates(outcome, matter)[2]


def working_record_tools(store, *, owner: WorkingRecordOwner) -> tuple[RegisteredTool, ...]:
    if not isinstance(owner, WorkingRecordOwner):
        raise ValueError("Working tools need their single actual inventory owner")

    def current(context):
        matter = store.load(context.identity.matter_id)
        records = (
            [row for row in matter.loop_records if row.identity == context.identity]
            if matter is not None
            else []
        )
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
            or len(records) != 1
            or records[0].terminal
        ):
            raise ToolRefused("Working tools need their exact current owned open parent")
        return matter, records[0]

    def envelope(name, inventory, context, data):
        return ToolEnvelope(
            name,
            VERSION,
            ToolKind.CONTROL,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "operation": name,
                "matter_id": context.identity.matter_id,
                "turn_id": context.identity.turn_id,
                "inventory_identity": inventory.identity,
            },
            data,
            "Private work data only; no relevance, legal truth, completeness or release certified.",
        )

    from nm.legal_brain.tool_propose_working_record import build_tool as propose_working_record_tool
    from nm.legal_brain.tool_read_working_inventory import build_tool as read_working_inventory_tool

    return (
        read_working_inventory_tool(current=current, envelope=envelope, owner=owner),
        propose_working_record_tool(current=current, envelope=envelope, owner=owner),
    )


@dataclass(frozen=True)
class WorkingReview:
    inventory: WorkingInventory
    annotations: tuple[AnalysisAnnotation, ...]
    review: IndependentReview | None

    @property
    def checked_annotations(self):
        released = (
            {package.identity for package in self.review.result.released}
            if self.review is not None
            else set()
        )
        return tuple(row for row in self.annotations if row.package_identity in released)


class WorkingRecordReviewService:
    def __init__(self, *, reviewer: ReviewService, owner: WorkingRecordOwner):
        if not isinstance(reviewer, ReviewService) or not isinstance(owner, WorkingRecordOwner):
            raise ValueError(
                "Working review needs the existing durable independent source reviewer"
            )
        self.reviewer, self.owner = reviewer, owner

    def review(self, outcome, *, budget=None, cancelled=lambda: False, max_model_calls=None):
        matter = self.reviewer.store.load(outcome.record.identity.matter_id)
        inventory, annotations, packages = self.owner.candidates(outcome, matter)
        if not packages:
            return WorkingReview(inventory, annotations, None)

        def current(parent, file, proposed):
            if self.owner.packages(parent, file) != proposed:
                raise ReviewRefused("Working explanations changed before independent verification")

        def sources(parent, file, proposed):
            current(parent, file, proposed)
            return tuple(
                dict.fromkeys(
                    span.finding
                    for package in proposed
                    for span in (*package.spans, *package.contrary)
                )
            )

        reviewed = self.reviewer.review_packages(
            outcome,
            packages,
            current_owner=current,
            current_sources=sources,
            cancelled=cancelled,
            max_model_calls=max_model_calls,
            **({"budget": budget} if budget is not None else {}),
        )
        return WorkingReview(inventory, annotations, reviewed)

    def recorded(self, outcome):
        from nm.legal_brain.brain_assessment import saved_package_reviews

        matter = self.reviewer.store.load(outcome.record.identity.matter_id)
        inventory, annotations, packages = self.owner.candidates(outcome, matter)
        self.reviewer._current(
            outcome,
            packages=packages,
            current_owner=lambda parent, file, proposed: self._same(parent, file, proposed),
        )
        if packages:
            reviewed = saved_package_reviews(outcome, packages, matter, self.reviewer.log)
        else:
            reviewed = None
        return WorkingReview(inventory, annotations, reviewed)

    def _same(self, outcome, matter, packages):
        if self.owner.packages(outcome, matter) != packages:
            raise ReviewRefused("Saved working packages differ from their current exact owners")

    def completeness(self, outcome, *, scope_service):
        """No author/caller-supplied proof: reconstruct both independent saved owners."""
        from nm.legal_brain.working_scope import WorkingScopeService

        if (
            not isinstance(scope_service, WorkingScopeService)
            or scope_service.owner is not self.owner
        ):
            raise ValueError("Completeness needs the actual saved scope service for this owner")
        working = self.recorded(outcome)
        proof = scope_service.recorded(outcome)
        inventory = working.inventory
        judgments = {row.id: row for row in proof.judgments} if proof is not None else {}
        checked = working.checked_annotations
        items = []
        for row in (*inventory.payload["areas"], *inventory.payload["needs"]):
            ident = row["id"]
            judgment = judgments.get(ident)
            needed = judgment.needed if judgment is not None else None
            coverage = tuple(
                annotation.id
                for annotation in checked
                if (
                    ("area" in row and area_id(annotation.thread_id, annotation.area) == ident)
                    or ident in annotation.need_ids
                )
            )
            state = (
                "inapplicable"
                if needed is False
                else "checked"
                if needed is True
                and judgment.covered is True
                and coverage
                and set(judgment.annotation_ids) <= set(coverage)
                else "not_assessed"
            )
            items.append(
                CompletenessItem(
                    ident,
                    needed,
                    state,
                    coverage,
                    judgment.reason
                    if judgment is not None
                    else "No current independent scope judgment",
                )
            )
        return WorkingCompleteness(
            inventory.identity,
            tuple(items),
            proof is not None and proof.assessed,
            proof.check_turn_id if proof is not None else "",
        )
