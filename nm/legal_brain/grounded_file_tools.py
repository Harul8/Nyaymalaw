"""Source-bound file interpretations, never human confirmation or legal truth.

The existing calendar, posture, parties and correction/dependency owners decide
what can be represented. A model selects a current scoped account; it cannot
select the actor, source words, clock, permission, confirmation or mutation type.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import date

from nm.legal_brain import parties, posture
from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.quotable_contracts import Quotable
from nm.shared.clock_contracts import today as forum_today
from nm.work_the_file import chronology, dependency
from nm.work_the_file.event_observation_contracts import EventObservation, event_context
from nm.work_the_file.file_mutation_contracts import FileMutation, neutral
from nm.work_the_file.matter_contracts import Basis, Certainty, FactBasis, Role

VERSION = "source-bound-file-interpretations-v1"
_STRING = {"type": "string", "minLength": 1}
_CONTROLS = (
    "test_new_file_reading_is_reachable_and_keeps_the_original_account",
    "test_grounded_file_reading_cannot_invent_or_upgrade_a_fact",
)


def _scoped_fact(matter, thread_id, fact_id):
    thread, fact = matter.thread(thread_id), matter.fact(fact_id)
    if (
        thread is None
        or fact is None
        or fact.id not in thread.chronology
        or fact.superseded_by is not None
        or fact.conflicts_with
        or fact.provenance.kind != "advocate_statement"
        or fact.certainty is not Certainty.ASSERTED
        or fact.basis is not FactBasis.NOT_ASSESSED
        or fact.confirmed is not None
        or fact.confirmed_at is not None
    ):
        raise ValueError("A file reading needs its exact current unconfirmed scoped account.")
    return thread, fact


def _derive(matter, *, thread_id, fact_id, turn_id, reference, proposal):
    thread, fact = _scoped_fact(matter, thread_id, fact_id)
    words = Quotable(turn=fact.statement)
    after = matter
    detail = {
        "fact_id": fact.id,
        "thread_id": thread.id,
        "original_account": fact.statement,
        "posture_basis": "not_assessed",
        "human_confirmation": "not_recorded",
        "legal_truth_established": False,
        "semantic_classification": "not_assessed",
    }
    observations = tuple(EventObservation.restore(row) for row in thread.event_observations)
    added = []
    for raw in proposal["events"]:
        event_quote, expression = raw["event_quote"], raw["date_expression"]
        if (
            not event_quote
            or event_quote not in fact.statement
            or expression
            and expression not in event_quote
        ):
            raise ValueError("An event and its date expression must occur in the source exactly.")
        # An earlier 'yesterday' must not be counted from the current turn.
        # Absolute calendar expressions are reference-independent; the same
        # owner, evaluated on two anchors, establishes that property.
        from nm.work_the_file.date_resolution import resolve

        on = resolve(expression, reference) if expression else None
        if expression and (
            on is None
            or (fact.provenance.turn != turn_id and resolve(expression, date(2000, 1, 1)) != on)
        ):
            raise ValueError("The source expression has no reproducible original date anchor.")
        readings = chronology.interpret(
            words,
            reference,
            {
                "events": [
                    {
                        "event": event_quote,
                        "date_expression": expression,
                        "resolved": on.isoformat() if on else "",
                        "documented": False,
                        "corrects": "",
                        "correction_instruction": "",
                    }
                ]
            },
        )
        if len(readings) != 1 or readings[0].refused or readings[0].on != on:
            raise ValueError("The existing calendar owner refused the proposed date.")
        observation = EventObservation(
            fact.id, fact.version, fact.statement, event_quote, expression, reference, on
        )
        if observation.observation_key in {row.observation_key for row in added}:
            raise ValueError("One event observation cannot be proposed twice.")
        if observation.observation_key not in {row.observation_key for row in observations}:
            added.append(observation)
    stated = posture.interpret(words, proposal["posture"])
    if stated.refused:
        raise ValueError(stated.refused)
    current = thread.posture
    if stated.role is not Role.UNKNOWN:
        # Reading is not human confirmation. Even a quoted procedural label
        # retains an INFERRED interpretation until independently assessed.
        current = current.enrich(stated.role, Basis.INFERRED, fact.id)
        detail.update(
            posture_basis="inferred",
            role=stated.role.value,
            representation_quote=stated.quoted,
            role_quote=proposal["posture"]["role_quote"],
        )
    named = parties.interpret(words, proposal["parties"])
    if named.refused or len(named.parties) != len(proposal["parties"]["parties"]):
        raise ValueError(named.refused or "The party reading omitted an invalid candidate.")
    held = dict(thread.parties)
    candidates = []
    for row in named.parties:
        if row.name not in fact.statement:
            raise ValueError("A party name must retain its actual original characters.")
        # A model cannot assign the directional conflict-screen input merely
        # by naming a person. A direction already recorded by intake survives;
        # new names are RELATED candidates pending independent clarification.
        side = matter.intake_parties.get(row.name, held.get(row.name, "related"))
        if side not in parties.SIDES:
            raise ValueError("The recorded party direction is unreadable, not clear.")
        held[row.name] = side
        candidates.append(
            {
                "name": row.name,
                "proposed_side": row.side,
                "recorded_side": side,
                "semantic_assessment": "not_assessed",
            }
        )
    detail["party_candidates"] = candidates
    changed = replace(
        thread,
        posture=current,
        parties=held,
        event_observations=(*thread.event_observations, *added),
        assessed=tuple(value for value in thread.assessed if value != "review_current"),
    )
    if changed != thread:
        after = after.with_thread(changed)
    # Exact facts and role conclusions already use this dependency owner.
    # Record before first so a changed existing fact is not a first observation.
    ledger, _, _ = dependency.sync_inputs(
        dependency.Ledger.from_stored(matter.dependencies), matter
    )
    ledger, affected, _ = dependency.sync_inputs(
        ledger,
        after,
        reason="A source-bound file interpretation changed its recorded input.",
        at=reference.isoformat(),
        by=matter.advocate_id,
    )
    if current != thread.posture:
        role_node = ledger.node(dependency.names_for(thread.id).role)
        if role_node is not None:
            # A prior role conclusion already declares the inputs it rests
            # on. Revisit that exact closure through the existing invalidation
            # owner; no new field/status state machine is introduced here.
            ledger, role_affected = dependency.invalidate(
                ledger,
                role_node.rests_on,
                reason="The source-bound procedural interpretation changed.",
                at=reference.isoformat(),
                by=matter.advocate_id,
            )
            affected = tuple(sorted(set((*affected, *role_affected))))
    if after != matter:
        after = replace(after, dependencies=ledger.as_dict())
    after = replace(
        after, version=matter.version, threads=tuple(after.thread(row.id) for row in matter.threads)
    )
    detail["stale_nodes"] = list(affected)
    detail["event_context"] = event_context(changed, after.facts)
    return after, detail


@dataclass(frozen=True)
class GroundedReadingMutation(FileMutation):
    """Closed interpretation extension; no arbitrary fact/thread field writer."""

    thread_id: str
    fact_id: str
    turn_id: str
    reference: date
    proposal: dict

    def __post_init__(self):
        object.__setattr__(self, "proposal", deepcopy(self.proposal))
        super().__post_init__()

    def _validate_projection(self):
        if type(self.reference) is not date:
            raise ValueError("A file reading carries the trusted calendar reference.")
        expected, _ = _derive(
            self.before,
            thread_id=self.thread_id,
            fact_id=self.fact_id,
            turn_id=self.turn_id,
            reference=self.reference,
            proposal=self.proposal,
        )
        if neutral(asdict(expected)) != neutral(asdict(self.after)):
            raise ValueError("The file projection differs from the existing reading owners.")
        super()._validate_projection()

    def _thread_projection(self, before, after, facts):
        if before.id == self.thread_id:
            after = replace(
                after,
                posture=before.posture,
                parties=before.parties,
                event_observations=before.event_observations,
            )
        super()._thread_projection(before, after, facts)

    def _digest(self):
        return digest(
            {
                "base": super()._digest(),
                "thread": self.thread_id,
                "fact": self.fact_id,
                "turn": self.turn_id,
                "reference": self.reference.isoformat(),
                "proposal": neutral(self.proposal),
            }
        )


def grounded_file_tools(store, *, today=forum_today):
    """Attach to the shared registry and one atomic journal writer.

    Calendar resolution is mechanical; event association, party direction and
    procedural-role meaning are still interpretations. No confirmed fact or
    legal cause/application/deadline is manufactured by this tool.
    """

    from nm.legal_brain.tool_record_grounded_file_reading import (
        build_tool as record_grounded_file_reading_tool,
    )

    return (record_grounded_file_reading_tool(store=store, today=today),)
