"""Request-local reuse is exact, finite and does not reopen unrelated history."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from nm.legal_brain.reason import requirements
from nm.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopRecord
from nm.legal_brain.reason.requirements_contracts import State
from nm.work_the_file import deadlines, dispute_agenda, summary
from nm.work_the_file.matter_contracts import Certainty, Fact, Matter, Provenance, Thread
from tests.test_checklist_classification_is_independently_reviewed import (
    NEED,
    TODAY,
    current_fixture_source,
    run_conversation,
)

pytestmark = pytest.mark.class_a


class CurrentSource:
    def __init__(self, *, changed=False):
        self.calls = []
        self.changed = changed

    def __call__(self, source, generation):
        self.calls.append((source, generation))
        return not self.changed and current_fixture_source(source, generation)


def _saved(tmp_path, **kwargs):
    store, _, _, _ = run_conversation(tmp_path, read=False,
                                      source_current=current_fixture_source, **kwargs)
    return store.load("mat_loop")


def test_context_derives_once_from_the_actual_cached_review(tmp_path):
    file = _saved(tmp_path)
    observed = CurrentSource()
    detail = requirements.context_projection(file.threads[0], file.facts, TODAY,
        records=file.loop_records, source_current=observed)
    assert len(observed.calls) == 1
    assert detail["summary"]["held"] == 1 and detail["asking_complete"] and detail["settled"]
    assert detail["items"][0]["review_state"] == "independently_reviewed"
    observed.calls.clear()
    prompt = requirements.conversation_context(file.threads[0], file.facts, TODAY,
        records=file.loop_records, source_current=observed)
    assert len(observed.calls) == 1
    assert "proportionate group of materially decision-changing questions" in prompt
    assert "up to two" not in prompt and "at most one" not in prompt
    assert NEED.need in prompt and NEED.span in prompt
    assert "No checklist state proves merits, authenticity, or document access" in prompt
    assert "Do not ask for held or unavailable items" in prompt


def test_board_register_and_handover_reuse_one_private_exact_population(tmp_path):
    file = _saved(tmp_path, answer="promised", words="I will provide the notice tomorrow.",
                  due="tomorrow")
    observed = CurrentSource()
    projections = requirements.file_projections(file, source_current=observed)
    assert len(observed.calls) == 1
    board = dispute_agenda.project(file, source_current=observed,
                                   checklist_projections=projections)
    register = deadlines.read_matter(file, source_current=observed,
                                     checklist_projections=projections)
    handover = summary.build(file, source_current=observed,
                             checklist_projections=projections).as_dict()
    dispute_agenda.context(file, source_current=observed, checklist_projections=projections)
    assert len(observed.calls) == 1, "Reuse does not reopen sources or rescan old review parents"
    row = board["disputes"][0]
    assert row["requirements"][0]["state"] == State.PROMISED.value
    assert row["nothing_to_ask"] and not row["requirements_settled"]
    assert handover["threads"][0]["requirements"] == projections[file.threads[0].id].summary()
    followups = [item for item in register.rows
                 if item.kind is deadlines.DeadlineKind.INFORMATION_FOLLOWUP]
    assert len(followups) == 1 and followups[0].on.isoformat() == "2026-09-28"
    observed.changed = True
    fresh = requirements.file_projections(file, source_current=observed)
    assert len(observed.calls) == 2, "Another request must observe current sources anew"
    assert fresh[file.threads[0].id].rows[0].state is State.OUTSTANDING
    assert not fresh[file.threads[0].id].settled


@pytest.mark.parametrize("change", ["version", "file", "actor", "certainty", "words",
                                  "source_read", "thread_added", "thread_removed", "journal"])
def test_request_local_reuse_refuses_every_changed_material_subject(tmp_path, change):
    file = _saved(tmp_path)
    projections = requirements.file_projections(file, source_current=current_fixture_source)
    if change in ("version", "file", "actor"):
        field = {"version": "version", "file": "id", "actor": "advocate_id"}[change]
        changed = replace(file, **{field: file.version + 1 if change == "version" else "foreign"})
    elif change in ("certainty", "words"):
        # The projection is bound to every current fact, not only a chosen quote.
        updates = {"certainty": Certainty.DOCUMENTED} if change == "certainty" else {
            "statement": "The notice was not served.", "exact_words": None}
        changed = replace(file, facts=(replace(file.facts[0], **updates), *file.facts[1:]))
    elif change == "source_read":
        changed = replace(file, threads=(replace(file.threads[0],
            requirement_reads={NEED.locator: "changed-generation"}),))
    elif change == "thread_added":
        changed = replace(file, threads=(*file.threads, Thread("extra", "Another dispute")))
    elif change == "thread_removed":
        changed = replace(file, threads=())
    else:
        changed = replace(file, loop_records=tuple(row for row in file.loop_records
            if ":verify:checklist_" not in row.identity.turn_id))
    for consumer in (dispute_agenda.project, deadlines.read_matter, summary.build):
        with pytest.raises(ValueError, match="subject|population"):
            consumer(changed, checklist_projections=projections)


def test_missing_extra_or_untyped_projection_population_cannot_be_an_all_clear(tmp_path):
    file = _saved(tmp_path)
    projections = requirements.file_projections(file, source_current=current_fixture_source)
    missing = replace(projections, entries=())
    extra = replace(projections, entries=(*projections.entries,
                                           ("extra", projections[file.threads[0].id])))
    for bad in (missing, extra, dict(projections.entries), SimpleNamespace(**vars(projections))):
        for consumer in (dispute_agenda.project, deadlines.read_matter, summary.build):
            with pytest.raises(ValueError, match="population|typed"):
                consumer(file, checklist_projections=bad)


@pytest.mark.parametrize("change", ["addition", "removal", "statement", "date", "certainty"])
def test_no_disputes_does_not_hide_a_same_version_change_to_the_factual_population(change):
    words = "I have supplied information before identifying its dispute."
    fact = Fact("opening", words, Provenance("advocate_statement", "opening-turn", span=words),
                date=TODAY, exact_words=words)
    file = Matter("not-yet-scoped", "advocate", "Opening file", facts=(fact,))
    if change == "addition":
        file = replace(file, facts=())
        changed = replace(file, facts=(fact,))
    elif change == "removal":
        changed = replace(file, facts=())
    else:
        updates = {"statement": "The account has changed.", "exact_words": None} if (
            change == "statement") else {"date": TODAY.replace(day=26)} if (
            change == "date") else {"certainty": Certainty.DOCUMENTED}
        changed = replace(file, facts=(replace(fact, **updates),))
    assert file.version == changed.version and not file.threads and not changed.threads
    projections = requirements.file_projections(file)
    assert projections.entries == ()
    for consumer in (dispute_agenda.project, deadlines.read_matter, summary.build):
        with pytest.raises(ValueError, match="population"):
            consumer(changed, checklist_projections=projections)


def _rewrite_terminal(record, transform):
    # Real typed chain, but deliberately malformed semantic receipt. The
    # production decoder, not a forged external PASS, must still reject it.
    events = []
    previous = record.identity.fingerprint
    for old in record.events:
        payload, at = old.payload, old.at
        if old is record.events[-1]:
            payload, at = transform(payload, at)
        event = LoopEvent.create(old.sequence, old.kind, at, payload, previous)
        events.append(event)
        previous = event.fingerprint
    return LoopRecord(record.identity, tuple(events))


@pytest.mark.parametrize("change", ["missing", "corrupt", "unknown", "denied", "future",
                                  "stale_source", "untyped"])
def test_without_real_matching_positive_child_no_source_is_reopened(tmp_path, change):
    file = _saved(tmp_path)
    child = next(row for row in file.loop_records if ":verify:checklist_" in row.identity.turn_id)
    records = file.loop_records
    if change == "missing":
        records = tuple(row for row in records if row is not child)
    elif change in ("corrupt", "unknown", "denied", "future"):
        def alter(payload, at):
            if change == "corrupt":
                payload["verification"] = {"authored": "PASS"}
            elif change in ("unknown", "denied"):
                payload["verification"]["inference"]["assessed"] = (
                    None if change == "unknown" else False)
            else:
                at = datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat()
            return payload, at
        bad = _rewrite_terminal(child, alter)
        records = tuple(bad if row is child else row for row in records)
    elif change == "stale_source":
        file = replace(file, threads=(replace(file.threads[0],
            requirement_reads={NEED.locator: "changed-generation"}),))
    else:
        records = (*records, SimpleNamespace(terminal=True))
    observed = CurrentSource()
    projection = requirements.project(file.threads[0], file.facts,
                                       records=records, source_current=observed)
    assert projection.rows[0].state is State.OUTSTANDING
    assert not projection.nothing_to_ask and not projection.settled
    assert not observed.calls, "Unmatched or negative children need no expensive source read"


def test_empty_or_corrupt_population_never_means_complete(tmp_path):
    file = _saved(tmp_path)
    for requirements_ in ((), (NEED, {"need": "unreadable extra"}), (NEED, NEED)):
        thread = replace(file.threads[0], requirements=requirements_)
        projection = requirements.project(thread, file.facts, records=file.loop_records,
                                           source_current=current_fixture_source)
        assert not projection.complete_population
        assert not projection.nothing_to_ask and not projection.settled
