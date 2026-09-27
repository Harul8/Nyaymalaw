"""Private opposition work derived from sealed child receipts, never merits clearance.

Pass timing is a lead-agent judgment. This owner refuses broadening, source-free
attacks and fabricated completion. The owner has not adopted a 'key details'
threshold: even a fully populated private pass remains independently unassessed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from nm.legal_brain.orchestrate.loop_contracts import StepKind, digest
from nm.legal_brain.orchestrate.tools import (
    ToolRefused,
)
from nm.legal_brain.reason.adversarial import Attack
from nm.legal_brain.retrieve.evidence_port import Finding
from nm.legal_brain.retrieve.tool_sources import findings_from_record
from nm.legal_brain.understand.brain_context import assemble_brief, linked_fact_ids

PASSES = {"oppose_early": "early", "oppose_full": "full", "oppose_matter": "matter"}
VERSION = "opposition-work-v1"
KINDS = (
    "strongest_case",
    "reply",
    "judicial_question",
    "cross_exposure",
    "no_exposure_identified",
    "coverage_limit",
)


@dataclass(frozen=True)
class OppositionRequest:
    tool: str
    question: str
    issue_ids: tuple[str, ...]

    def __post_init__(self):
        if (
            self.tool not in PASSES
            or not isinstance(self.question, str)
            or not self.question.strip()
            or not isinstance(self.issue_ids, tuple)
            or not self.issue_ids
            or len(self.issue_ids) != len(set(self.issue_ids))
            or any(not isinstance(row, str) or not row.strip() for row in self.issue_ids)
        ):
            raise ValueError("An opposition task has its pass, question and exact dispute scope")

    def admit(self, matter, granted):
        known = {row.id for row in matter.threads}
        selected = set(self.issue_ids)
        if not selected <= known or not selected <= set(granted):
            raise ToolRefused("Opposition cannot inherit another dispute's grant.")
        if self.tool == "oppose_matter" and (
            len(known) < 2 or selected != known or not known <= set(granted)
        ):
            raise ToolRefused("The cross-dispute pass needs the actual whole-matter read scope.")
        if self.tool != "oppose_matter" and len(selected) != 1:
            raise ToolRefused("An early or full pass belongs to exactly one recorded dispute.")


def case_basis(matter, request: OppositionRequest):
    """All scoped substantive fields, including adverse/corrected/conflicted facts.

    Journal appends and unrelated linked disputes do not change this subject.
    Unassigned facts remain in every subject until a checked attribution exists.
    """
    brief = assemble_brief(matter, request.issue_ids, advocate_id=matter.advocate_id)
    raw = json.loads(brief.source_record_json)
    selected = set(request.issue_ids)
    linked = {fact for row in raw["threads"] if row["id"] in selected for fact in row["chronology"]}
    assigned = {fact for row in raw["threads"] for fact in row["chronology"]}
    wanted = linked_fact_ids(
        raw["facts"], linked | {row["id"] for row in raw["facts"] if row["id"] not in assigned}
    )
    threads = [
        {key: value for key, value in row.items() if key != "thresholds_told"}
        for row in raw["threads"]
        if row["id"] in selected
    ]
    facts = [row for row in raw["facts"] if row["id"] in wanted]
    documents = {row["provenance"]["document"] for row in facts if row["provenance"]["document"]}
    bindings = {
        key: value
        for key, value in raw["source_bindings"].items()
        if key != "__superseded__" and value.get("thread_id") in selected
    }
    bindings["__superseded__"] = [
        value
        for value in raw["source_bindings"].get("__superseded__", [])
        if value.get("thread_id") in selected
    ]
    return {
        "matter_id": matter.id,
        "advocate_id": matter.advocate_id,
        "pass": PASSES[request.tool],
        "question": request.question,
        "issue_ids": sorted(request.issue_ids),
        "threads": threads,
        "facts": facts,
        "commission": raw["commission"],
        "engagement": raw["engagement"],
        "intake_parties": raw["intake_parties"],
        "screens": raw["screens"],
        "emergencies": raw["emergencies"],
        "urgency_records": raw["urgency_records"],
        "source_bindings": bindings,
        "documents": {key: value for key, value in raw["uploads"].items() if key in documents},
    }


def check_observations(request, rows, *, finding_ids, premise_ids, premise_by_issue):
    """Exact linked private candidates, not a determination that their law applies."""
    if not isinstance(rows, list) or not rows:
        raise ToolRefused("An empty opposition return cannot establish that adverse work ran.")
    ids, covered, categories = set(), set(), {}
    for row in rows:
        scope = row["issue_ids"]
        if (
            not row["id"].strip()
            or row["id"] in ids
            or not row["text"].strip()
            or row["kind"] not in KINDS
            or not scope
            or len(set(scope)) != len(scope)
            or not set(scope) <= set(request.issue_ids)
            or not row["finding_ids"]
            or not set(row["finding_ids"]) <= finding_ids
            or not row["premise_ids"]
            or not set(row["premise_ids"]) <= premise_ids
            or any(
                not set(row["premise_ids"]) & set(premise_by_issue.get(issue, ()))
                for issue in scope
            )
        ):
            raise ToolRefused("Opposition needs exact scoped case premises and retrieved passages.")
        if row["kind"] in ("cross_exposure", "no_exposure_identified") and len(scope) < 2:
            raise ToolRefused("A cross-dispute observation cannot name just one dispute.")
        ids.add(row["id"])
        covered.update(scope)
        for issue in scope:
            categories.setdefault(issue, set()).add(row["kind"])
        if row["kind"] == "reply":
            contrary = next(
                (
                    item
                    for item in rows
                    if item["id"] == row["response_to"]
                    and item["kind"] == "strongest_case"
                    and set(item["issue_ids"]) == set(scope)
                ),
                None,
            )
            if contrary is None:
                raise ToolRefused(
                    "A proposed reply identifies the exact contrary case it addresses."
                )
            Attack(
                scope[0],
                contrary["text"],
                contrary["text"],
                "" if row["no_supported_reply"] else row["text"],
                row["no_supported_reply"],
                row["course"],
            )
        elif row["response_to"] or row["no_supported_reply"] or row["course"]:
            raise ToolRefused("Only a reply may record its no-supported-answer disposition.")
    if covered != set(request.issue_ids):
        raise ToolRefused("An opposition pass cannot silently skip a selected dispute.")
    if request.tool == "oppose_full" and any(
        not {"strongest_case", "reply", "judicial_question"} <= categories[issue]
        for issue in request.issue_ids
    ):
        raise ToolRefused(
            "A private full pass names the contrary case, reply and judicial vulnerability."
        )
    if request.tool == "oppose_early" and not any(row["kind"] == "strongest_case" for row in rows):
        raise ToolRefused(
            "An early pass must actually identify a source-grounded possible defence."
        )
    if request.tool == "oppose_matter" and not any(
        row["kind"] in {"cross_exposure", "no_exposure_identified"} for row in rows
    ):
        raise ToolRefused("The whole-matter pass must actually examine a cross-dispute exposure.")


def controls(context, provider, model):
    return {
        "principles_version": context.identity.principles_version,
        "tools_version": context.identity.tools_version,
        "provider": provider,
        "model": model,
    }


def work_record(matter, request, research, captured, control):
    findings = research.get("findings", [])
    if not findings or not research.get("observations"):
        raise ToolRefused("An opposition record cannot be built from an empty or failed read.")
    windows = research["source_windows"]
    locators = {row["finding_metadata"]["locator"] for row in windows}
    sources = tuple(row for row in captured if row.locator in locators)
    if not sources or any(not isinstance(row, Finding) for row in sources):
        raise ToolRefused("Opposition cannot author its source capture population.")
    body = {
        "schema": 1,
        "tool": request.tool,
        "question": request.question,
        "issue_ids": list(request.issue_ids),
        "case": case_basis(matter, request),
        "sources": [row.as_record() for row in sources],
        "controls": control,
        "research": research,
        "assessment": "not_assessed",
        "advice_released": False,
        "full_readiness": "not_assessed",
    }
    return {**body, "work_identity": digest(body)}


def _check_saved_extracts(raw):
    research, windows = raw["research"], raw["research"]["source_windows"]
    sources = tuple(Finding.from_record(row) for row in raw["sources"])
    actual = {"law_" + digest(row.as_record()): row for row in sources}
    if (
        not windows
        or len({row["id"] for row in windows}) != len(windows)
        or research["source_set_identity"] != digest(windows)
        or research["state"] != "exact_extracts_not_semantically_assessed"
    ):
        raise ToolRefused("Saved opposition needs its exact nonempty source-window population.")
    for row in windows:
        source = actual.get(row["id"])
        if (
            source is None
            or row["start"] != 0
            or row["end"] != len(source.span)
            or row["text"] != source.span
            or row["finding_identity"] != digest(source.as_record())
            or row["finding_metadata"]
            != {key: value for key, value in source.as_record().items() if key != "span"}
        ):
            raise ToolRefused("A saved opposition window differs from its actual source capture.")
    extracts = research["findings"]
    if not extracts or len({row["id"] for row in extracts}) != len(extracts):
        raise ToolRefused("Saved opposition needs uniquely identified actual extracts.")
    for row in extracts:
        source = actual.get(row["source_window_id"])
        if source is None or not row["quote"].strip() or row["quote"] not in source.span:
            raise ToolRefused("A saved extract is not verbatim in its actual source.")


def _saved_work(matter):
    """Read one exact parent invocation/return pair, not arbitrary nested prose."""
    originals = {}
    for record in matter.loop_records:
        if (
            record.identity.advocate_id != matter.advocate_id
            or record.identity.matter_id != matter.id
        ):
            raise ToolRefused("An opposition journal belongs to another file or actor.")
        pending = {}
        for event in record.events:
            if event.kind is StepKind.TOOL_STARTED:
                call = event.payload["call"]
                pending[call["call_id"]] = call
            elif event.kind is StepKind.TOOL_RETURNED:
                call = pending.pop(event.payload["call_id"], None)
                receipt = event.payload["receipt"]
                raw = receipt.get("receipt", {}).get("task_result", {}).get("opposition_work")
                if raw is None:
                    continue
                if (
                    call is None
                    or call["name"] not in PASSES
                    or receipt["tool"] != call["name"]
                    or receipt["assessment"] != "not_assessed"
                ):
                    raise ToolRefused(
                        "Saved opposition is not correlated with its actual dispatch."
                    )
                body = {key: value for key, value in raw.items() if key != "work_identity"}
                if (
                    set(body)
                    != {
                        "schema",
                        "tool",
                        "question",
                        "issue_ids",
                        "case",
                        "sources",
                        "controls",
                        "research",
                        "assessment",
                        "advice_released",
                        "full_readiness",
                    }
                    or raw.get("work_identity") != digest(body)
                    or raw.get("schema") != 1
                    or raw.get("assessment") != "not_assessed"
                    or raw.get("advice_released") is not False
                    or raw.get("full_readiness") != "not_assessed"
                    or raw["tool"] != call["name"]
                    or raw["question"] != call["arguments"]["question"]
                    or raw["issue_ids"] != call["arguments"]["issue_ids"]
                ):
                    raise ToolRefused("The saved opposition work differs from its sealed subject.")
                # These are genuine child source owners. Reuse does not invent
                # a new trace; its original work was already sealed separately.
                original = receipt["receipt"]["task_result"].get("reused_from")
                if original is None:
                    captured = findings_from_record(
                        replace(record, events=record.events[: event.sequence])
                    )
                    if any(Finding.from_record(row) not in captured for row in raw["sources"]):
                        raise ToolRefused(
                            "Opposition cites material its child did not actually read."
                        )
                else:
                    earlier = originals.get(original["event_fingerprint"])
                    if earlier is None or earlier != (raw, original):
                        raise ToolRefused("Reused opposition needs its actual earlier sealed work.")
                request = OppositionRequest(raw["tool"], raw["question"], tuple(raw["issue_ids"]))
                _check_saved_extracts(raw)
                if any(
                    row.get("semantic_assessment") != "not_assessed"
                    for row in raw["research"]["observations"]
                ):
                    raise ToolRefused("Private opposition cannot author independent assessment.")
                check_observations(
                    request,
                    raw["research"]["observations"],
                    finding_ids={row["id"] for row in raw["research"]["findings"]},
                    premise_ids={row["id"] for row in raw["case"]["facts"]},
                    premise_by_issue=scoped_premises(raw["case"]),
                )
                reference = {
                    "turn_id": record.identity.turn_id,
                    "event_fingerprint": event.fingerprint,
                    "sequence": event.sequence,
                }
                originals[event.fingerprint] = (raw, reference)
                yield raw, reference


def status_for_work(matter, raw, captured, control):
    request = OppositionRequest(raw["tool"], raw["question"], tuple(raw["issue_ids"]))
    known = {row.id for row in matter.threads}
    if (
        not set(request.issue_ids) <= known
        or request.tool == "oppose_matter"
        and set(request.issue_ids) != known
        or raw["case"] != case_basis(matter, request)
        or raw["controls"] != control
    ):
        return "stale"
    saved = tuple(Finding.from_record(row) for row in raw["sources"])
    if any(old.locator == new.locator and old != new for old in saved for new in captured):
        return "stale"
    if any(row not in captured for row in saved):
        return "source_not_revalidated"
    return "current_unreviewed"


def scoped_premises(record):
    """Exact chronology/correction/conflict closure, not a relevance guess."""
    return {
        row["id"]: linked_fact_ids(record["facts"], row["chronology"]) for row in record["threads"]
    }


def reusable_work(matter, request, captured, control):
    latest = {}
    for raw, reference in _saved_work(matter):
        latest[(raw["tool"], tuple(raw["issue_ids"]), raw["question"])] = (raw, reference)
    row = latest.get((request.tool, request.issue_ids, request.question))
    return (
        row
        if row and status_for_work(matter, row[0], captured, control) == "current_unreviewed"
        else None
    )


def opposition_status_tool(*, store, provider, model):
    """Trusted local projection; root registers this with actual permission closures."""

    from nm.legal_brain.reason.tool_read_opposition_status import (
        build_tool as read_opposition_status_tool,
    )

    return read_opposition_status_tool(store=store, provider=provider, model=model)
