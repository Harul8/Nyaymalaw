"""Typed private work, not a transcript of deliberation or permission to advise."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from nm.legal_brain.orchestrate.loop_contracts import digest
from nm.shared.budget_contracts import Budget


class AnalysisArea(str, Enum):
    UNDERSTANDING = "understanding"
    DISPUTES = "disputes"
    ACT_PASSAGES = "act_passages"
    CASE_LAW_PASSAGES = "case_law_passages"
    EVIDENCE_TO_COLLECT = "evidence_to_collect"
    CASE_TO_PREPARE = "case_to_prepare"
    ARGUMENTS = "arguments"
    OPPOSITION = "opposition"
    STRENGTHEN = "strengthen"
    CROSS_MATTER = "cross_matter"
    QUESTIONS = "questions"


BRIEF_AREAS = tuple(
    area
    for area in AnalysisArea
    if area
    not in {
        AnalysisArea.UNDERSTANDING,
        AnalysisArea.DISPUTES,
        AnalysisArea.CROSS_MATTER,
        AnalysisArea.QUESTIONS,
    }
)


class Disposition(str, Enum):
    CONSIDERED = "considered"
    KEPT = "kept"
    SET_ASIDE = "set_aside"
    UNASSESSED = "unassessed"
    INAPPLICABLE = "inapplicable"


class ReferenceKind(str, Enum):
    INPUT = "input"
    THREAD = "thread"
    FACT = "fact"
    SOURCE = "source"
    DOCUMENT = "document"
    REQUIREMENT = "requirement"
    WORK = "work"


@dataclass(frozen=True)
class WorkReference:
    kind: ReferenceKind
    id: str
    identity: str

    def __post_init__(self):
        if (
            not isinstance(self.kind, ReferenceKind)
            or not isinstance(self.id, str)
            or not self.id.strip()
            or not isinstance(self.identity, str)
            or len(self.identity) != 64
            or any(char not in "0123456789abcdef" for char in self.identity)
        ):
            raise ValueError("Working references need exact typed owner identities")

    def as_dict(self):
        return {"kind": self.kind.value, "id": self.id, "identity": self.identity}


@dataclass(frozen=True)
class WorkingInventory:
    """Immutable complete JSON; callers receive decoded copies, not mutable truth."""

    payload_json: str

    def __post_init__(self):
        value = json.loads(self.payload_json)
        if (
            not isinstance(value, dict)
            or value.get("schema") != 1
            or not isinstance(value.get("original_instruction"), str)
            or not value["original_instruction"].strip()
            or any(
                not isinstance(value.get(name), list)
                for name in ("references", "needs", "areas", "threads")
            )
        ):
            raise ValueError("A working inventory needs the whole actual request and populations")

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def identity(self):
        return digest(self.payload)

    @property
    def references(self):
        return {row["reference"]["id"]: row for row in self.payload["references"]}


@dataclass(frozen=True)
class AnalysisAnnotation:
    id: str
    thread_id: str | None
    area: AnalysisArea
    disposition: Disposition
    analysis: str
    reason: str
    references: tuple[WorkReference, ...]
    need_ids: tuple[str, ...]
    package_id: str
    package_identity: str
    """Candidate only: no author-written relevance, completeness or PASS field."""


@dataclass(frozen=True)
class ScopeJudgment:
    id: str
    needed: bool | None
    covered: bool | None
    reason: str
    supporting_words: tuple[tuple[str, str], ...]
    references: tuple[WorkReference, ...]
    annotation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelevanceProof:
    inventory_identity: str
    parent_terminal: str
    check_turn_id: str
    comprehensive: bool | None
    population_assessed: bool | None
    judgments: tuple[ScopeJudgment, ...]
    reason: str
    budget: Budget
    model_steps: int
    """Useful only after its saved independent transport is reconstructed."""

    @property
    def assessed(self):
        return (
            self.population_assessed is True
            and self.comprehensive is not None
            and all(
                row.needed is not None and (row.needed is False or row.covered is not None)
                for row in self.judgments
            )
        )


@dataclass(frozen=True)
class CompletenessItem:
    id: str
    needed: bool | None
    state: str
    annotation_ids: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class WorkingCompleteness:
    inventory_identity: str
    items: tuple[CompletenessItem, ...]
    scope_assessed: bool
    check_turn_id: str = ""

    @property
    def complete(self):
        return self.scope_assessed and all(
            row.needed is not None and (row.needed is False or row.state == "checked")
            for row in self.items
        )

    @property
    def client_ready(self):
        return False

    @property
    def released(self):
        return False
