"""Grounded checklist proposals on actual captured law, with one atomic writer.

This owner never chooses law from model memory, establishes a case fact, answers
a requirement or certifies legal review. Existing checklist interpretation and
merge own the record. The lead journal alone applies the prepared projection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from nm.legal_brain.orchestrate.loop_contracts import StepKind, digest
from nm.legal_brain.orchestrate.tools import (
    RegisteredTool,
    ToolRefused,
    object_schema,
)
from nm.legal_brain.reason import requirements
from nm.legal_brain.reason.requirements_contracts import (
    Force,
    Requirement,
    applicability_identity,
    key,
)
from nm.legal_brain.retrieve.tool_sources import findings_from_record
from nm.work_the_file.file_mutation_contracts import FileMutation, neutral

VERSION = "captured-source-requirements-v1"
_STRING = {"type": "string", "minLength": 1}
_ROW = object_schema(
    {
        "need": _STRING,
        "why": _STRING,
        "span": _STRING,
        "locator": _STRING,
        "force": {"type": "string", "enum": [row.value for row in Force]},
    }
)


def _parent(matter, turn_id, advocate_id):
    records = [row for row in matter.loop_records if row.identity.turn_id == turn_id]
    if (
        len(records) != 1
        or records[0].identity.advocate_id != advocate_id
        or records[0].terminal
        or not records[0].events
        or records[0].events[-1].kind is not StepKind.TOOL_STARTED
    ):
        raise ToolRefused("A source write needs its actual current reserved parent tool call.")
    return records[0]


def _reading(rows, captured, *, context_identity=""):
    found = []
    for row in rows:
        matches = tuple(source for source in captured if source.locator == row["locator"])
        if len(matches) != 1:
            raise ToolRefused("A checklist row needs one unambiguous actual source read.")
        source = matches[0]
        if source.supports is False or source.source_blocking_reason:
            raise ToolRefused(source.source_blocking_reason or "Known unsupported source.")
        if row["span"] not in source.span:
            raise ToolRefused("A requirement must quote its actually captured passage exactly.")
        passage = requirements.Passage(
            source.ref, source.span, source.source_kind.value, source.locator
        )
        read = requirements.read(
            {
                "requirements": [
                    {
                        "need": row["need"],
                        "why": row["why"],
                        "span": row["span"],
                        "source": source.ref,
                        "force": row["force"],
                    }
                ]
            },
            (passage,), context_identity=context_identity,
        )
        if len(read.requirements) != 1 or read.dropped:
            raise ToolRefused("The existing source-bound requirement owner refused the row.")
        if key(read.requirements[0]) in {key(held) for held in found}:
            raise ToolRefused("The same requirement cannot be declared twice.")
        found.append(read.requirements[0])
    return requirements.Reading(tuple(found))


@dataclass(frozen=True)
class SourceRequirementMutation(FileMutation):
    """Closed source extension; all original admission/ownership rules remain."""

    thread_id: str
    turn_id: str
    source_version: str
    proposed: tuple[Requirement, ...]

    def _thread_projection(self, before, after, facts):
        if before.id != self.thread_id:
            return super()._thread_projection(before, after, facts)
        # The base still checks chronology, issues, outcomes and assessment.
        super()._thread_projection(
            before,
            replace(
                after, requirements=before.requirements,
                requirement_reads=before.requirement_reads,
                requirement_read_contexts=before.requirement_read_contexts,
            ),
            facts,
        )
        if (
            not self.proposed
            or not isinstance(self.proposed, tuple)
            or any(not isinstance(row, Requirement) for row in self.proposed)
            or not isinstance(self.source_version, str)
            or not self.source_version.strip()
        ):
            raise ValueError("A source mutation needs its typed actual proposed population")
        parent = _parent(self.before, self.turn_id, self.advocate_id)
        captured = findings_from_record(parent, source_version=self.source_version)
        rows = tuple(
            {
                "need": row.need,
                "why": row.why,
                "span": row.span,
                "locator": row.locator,
                "force": row.force.value,
            }
            for row in self.proposed
        )
        context_identity = applicability_identity(before, self.before.facts)
        if _reading(rows, captured,
                    context_identity=context_identity).requirements != self.proposed:
            raise ValueError("A prepared requirement differs from the captured source read")
        if any(Requirement.restore(row) is None for row in before.requirements):
            raise ValueError("An unreadable earlier checklist cannot silently be erased")
        expected = requirements.merge(before.requirements, requirements.Reading(self.proposed))
        if neutral([asdict(row) for row in expected]) != neutral(asdict(after)["requirements"]):
            raise ValueError("A source mutation preserves the checklist through its merge owner")
        expected_reads = {
            **before.requirement_reads,
            **{row.locator: row.source_identity for row in self.proposed},
        }
        if after.requirement_reads != expected_reads:
            raise ValueError("A source mutation records only the exact captured passage identities")
        expected_contexts = {
            **before.requirement_read_contexts,
            **{row.locator: context_identity for row in self.proposed},
        }
        if after.requirement_read_contexts != expected_contexts:
            raise ValueError("A source mutation records only its current dispute applicability")

    def _validate_projection(self):
        if not any(row.id == self.thread_id for row in self.before.threads):
            raise ValueError("A source mutation cannot create or choose an unknown dispute")
        if self.changed_fields != ("threads",):
            raise ValueError("A source mutation changes only captured checklist requirements")
        if len(self.before.threads) != len(self.after.threads):
            raise ValueError("A source mutation cannot add or remove a dispute")
        for old, new in zip(self.before.threads, self.after.threads, strict=True):
            permitted = (
                replace(new, requirements=old.requirements,
                        requirement_reads=old.requirement_reads,
                        requirement_read_contexts=old.requirement_read_contexts)
                if old.id == self.thread_id
                else new
            )
            if neutral(asdict(old)) != neutral(asdict(permitted)):
                raise ValueError("A source mutation changes only its selected requirements")
        super()._validate_projection()

    def _digest(self):
        return digest(
            {
                "base": super()._digest(),
                "thread": self.thread_id,
                "turn": self.turn_id,
                "source_version": self.source_version,
                "proposed": neutral([asdict(row) for row in self.proposed]),
            }
        )


def source_write_tools(store, *, source_version: str) -> tuple[RegisteredTool, ...]:
    """One useful grounded legal-write owner; no arbitrary fields or source IDs."""
    if not isinstance(source_version, str) or not source_version.strip():
        raise ValueError("A source write is bound to its actual admitted source generation")

    from nm.legal_brain.reason.tool_record_requirements import (
        build_tool as record_requirements_tool,
    )

    return (record_requirements_tool(store=store, source_version=source_version),)
