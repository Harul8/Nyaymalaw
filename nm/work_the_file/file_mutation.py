"""Prepare source-bound file writes through existing owners; perform no I/O.

Model arguments select an existing exact item, never an actor, transaction
version or original message. Those inputs come from authenticated admission.
"""
from __future__ import annotations

from dataclasses import replace

from nm.Archives.legal_brain.common.quotable_contracts import Quotable
from nm.Archives.legal_brain.orchestrate.loop_contracts import digest
from nm.Archives.legal_brain.reason import issues, requirements
from nm.Archives.legal_brain.reason.issue_contracts import from_stored, merge
from nm.shared.text_contracts import fold
from nm.work_the_file import dependency
from nm.work_the_file.file_mutation_contracts import FileMutation
from nm.work_the_file.matter_contracts import Fact, Matter, Provenance, Thread


class MutationRefused(ValueError):
    """A proposed content change could not be grounded in the trusted input."""


def _trusted(matter, *, advocate_id, current_version, turn_id, message):
    if (not isinstance(matter, Matter) or matter.advocate_id != advocate_id
            or type(current_version) is not int or matter.version != current_version):
        raise MutationRefused("the actor or observed file version does not match")
    if (not isinstance(turn_id, str) or not turn_id.strip()
            or not isinstance(message, str) or not message.strip()):
        raise MutationRefused("a mutation needs its original authenticated advocate message")


def _quote(message, quoted):
    if not isinstance(quoted, str) or not quoted.strip() or quoted not in message:
        raise MutationRefused("the proposed words are not in the original advocate message")


def _thread(matter, ident):
    found = matter.thread(ident)
    if found is None:
        raise MutationRefused("the exact dispute is not on this matter")
    return found


def assertion_identity(matter_id, turn_id, message):
    """One identity for the entire attributed input, never a selected fragment."""
    return "fact_" + digest({"matter": matter_id, "turn": turn_id, "words": message})[:24]


def dispute_identity(matter_id, turn_id, quoted, label):
    """The exact source-bound writer and its receipt readers share this owner."""
    return "thr_" + digest({"matter": matter_id, "turn": turn_id,
                            "quote": quoted, "label": label})[:24]


def _assertion(matter, *, turn_id, message, quoted, thread_ids):
    _quote(message, quoted)
    if (not isinstance(thread_ids, (list, tuple)) or not thread_ids
            or any(not isinstance(ident, str) for ident in thread_ids)
            or len(set(thread_ids)) != len(thread_ids)):
        raise MutationRefused("an assertion has an explicit unique existing dispute scope")
    for ident in thread_ids:
        _thread(matter, ident)
    # A fragment can omit who alleged it, a denial, or a hypothetical. Keep
    # the entire authenticated account; the quote selects scope, not truth.
    ident = assertion_identity(matter.id, turn_id, message)
    fact = Fact(ident, message, Provenance("advocate_statement", turn_id, span=message),
                exact_words=message)
    held = matter.fact(ident)
    if held is None:
        matter, fact = matter.recording(fact)
    elif held != fact:
        raise MutationRefused("an existing statement identity carries different content")
    for tid in thread_ids:
        thread = _thread(matter, tid)
        chronology = thread.chronology if fact.id in thread.chronology else (
            *thread.chronology, fact.id)
        changed = replace(thread, chronology=chronology,
                          assessed=tuple(v for v in thread.assessed if v != "review_current"))
        if changed != thread:
            matter = matter.with_thread(changed)
    return matter, fact


def _finish(before, after, advocate_id):
    # Existing pure owners advance versions while building their projections.
    # The actual transaction still belongs to the one journal append/CAS.
    ordered = (*tuple(after.thread(t.id) for t in before.threads),
               *tuple(t for t in after.threads if before.thread(t.id) is None))
    after = replace(after, version=before.version, threads=ordered)
    if after == before:
        raise MutationRefused("the requested content is already recorded; no change was prepared")
    return FileMutation(before, after, advocate_id)


def prepare_admission(matter, *, advocate_id, current_version, turn_id, message,
                      quoted, thread_ids):
    _trusted(matter, advocate_id=advocate_id, current_version=current_version,
             turn_id=turn_id, message=message)
    after, fact = _assertion(matter, turn_id=turn_id, message=message,
                             quoted=quoted, thread_ids=thread_ids)
    return _finish(matter, after, advocate_id), {
        "fact_id": fact.id, "selected_span": quoted, "asserted_only": True}


def prepare_dispute(matter, *, advocate_id, current_version, turn_id, message, label, quoted):
    _trusted(matter, advocate_id=advocate_id, current_version=current_version,
             turn_id=turn_id, message=message)
    _quote(message, quoted)
    if not isinstance(label, str) or not label.strip():
        raise MutationRefused("a dispute has a nonblank descriptive label")
    ident = dispute_identity(matter.id, turn_id, quoted, label)
    if matter.thread(ident) is not None:
        raise MutationRefused(
            "this exact dispute creation is already recorded; nothing was duplicated")
    thread = replace(Thread.create(label), id=ident)
    after = matter.with_thread(thread)
    after, fact = _assertion(after, turn_id=turn_id, message=message,
                             quoted=quoted, thread_ids=(thread.id,))
    return _finish(matter, after, advocate_id), {"thread_id": thread.id,
        "fact_id": fact.id, "unassessed": True, "merged_existing": False,
        "selected_span": quoted, "asserted_only": True}


def prepare_correction(matter, *, advocate_id, current_version, turn_id, message,
                       old_fact_id, quoted, today):
    _trusted(matter, advocate_id=advocate_id, current_version=current_version,
             turn_id=turn_id, message=message)
    old = matter.fact(old_fact_id)
    if old is None or old.superseded_by is not None:
        raise MutationRefused("correct the exact current entry, not a missing or withdrawn one")
    tids = tuple(t.id for t in matter.threads if old.id in t.chronology)
    after, fact = _assertion(matter, turn_id=turn_id, message=message,
                             quoted=quoted, thread_ids=tids)
    try:
        after = after.superseding(old.id, fact.id)
    except ValueError as exc:
        raise MutationRefused("the existing correction owner refused the replacement") from exc
    ledger, affected, _ = dependency.sync_inputs(
        dependency.Ledger.from_stored(after.dependencies), after,
        reason=quoted, at=today.isoformat(), by=advocate_id)
    after = replace(after, dependencies=ledger.as_dict())
    return _finish(matter, after, advocate_id), {
        "fact_id": fact.id, "replaced_fact_id": old.id,
        "stale_nodes": list(affected), "selected_span": quoted, "asserted_only": True}


def prepare_requirement_answer(matter, *, advocate_id, current_version, turn_id,
                               message, thread_id, requirement_key, answer, quoted,
                               due_expression, today, fact_id=""):
    _trusted(matter, advocate_id=advocate_id, current_version=current_version,
             turn_id=turn_id, message=message)
    thread = _thread(matter, thread_id)
    if requirement_key not in {requirements.key(row) for row in requirements.restored(thread)}:
        raise MutationRefused("the exact requirement is not on this dispute")
    if fact_id:
        fact = matter.fact(fact_id)
        if (fact is None or fact.id not in thread.chronology or fact.superseded_by is not None
                or fact.provenance.kind != "advocate_statement"):
            raise MutationRefused("the earlier answer needs its exact current scoped assertion")
        _quote(fact.statement, quoted)
        after, source_message = matter, fact.statement
    else:
        after, fact = _assertion(matter, turn_id=turn_id, message=message,
                                 quoted=quoted, thread_ids=(thread_id,))
        source_message = message
    proposal = {"thread_id": thread_id, "key": requirement_key, "answer": answer,
                "quoted": quoted, "due_expression": due_expression}
    if fact_id:
        proposal["fact_id"] = fact.id
    answered = requirements.apply_answers(after, [proposal], message=source_message,
        turn_id=turn_id, today=today, current_only=not bool(fact_id), requires_review=True)
    before_outcome = after.thread(thread_id).requirement_outcomes.get(requirement_key)
    outcome = answered.thread(thread_id).requirement_outcomes.get(requirement_key)
    if outcome == before_outcome:
        raise MutationRefused("the existing checklist owner could not ground that answer")
    return _finish(matter, answered, advocate_id), {
        "fact_id": fact.id, "thread_id": thread_id, "requirement_key": requirement_key,
        "outcome": outcome, "selected_span": quoted, "legal_truth_established": False,
        "earlier_assertion_reused": bool(fact_id),
        "checklist_context": requirements.context_projection(
            answered.thread(thread_id), answered.facts, today)}


def prepare_issue(matter, *, advocate_id, current_version, turn_id, message,
                  thread_id, statement, kind, runs_against, quoted):
    _trusted(matter, advocate_id=advocate_id, current_version=current_version,
             turn_id=turn_id, message=message)
    _quote(message, quoted)
    thread = _thread(matter, thread_id)
    row = {"statement": statement, "kind": kind, "runs_against": runs_against,
           "sentences": list(Quotable(turn=message).sentences), "restates": ""}
    read = issues.read({"issues": [row]}, thread_id, Quotable(turn=message))
    if not read.examined or read.refused or len(read.issues) != 1:
        raise MutationRefused("the existing issue owner could not ground that question")
    standing = tuple(thread.issues)
    restored = from_stored(standing)
    if len(restored) != len(standing):
        raise MutationRefused("the standing issue register is unreadable; no issue was overwritten")
    if fold(statement) in {fold(value.statement) for value in restored}:
        raise MutationRefused("the exact issue is already recorded; its disposition is preserved")
    additions = merge(restored, read.issues)[len(restored):]
    if len(additions) != 1:
        raise MutationRefused("the existing issue owner admitted no new question")
    added = additions[0]
    after = matter.with_thread(replace(thread, issues=(*standing, added),
        assessed=tuple(v for v in thread.assessed if v != "review_current")))
    return _finish(matter, after, advocate_id), {"thread_id": thread_id,
        "issue_id": added.id, "selected_span": quoted,
        "question_only": True, "fact_established": False}
