"""A self-consistent resealed check is not proof of a changed real work population."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from nm.Archives.legal_brain.verify.brain_finalization import CheckRead
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.Archives.legal_brain.verify.interaction_review import (
    COMMUNICATION_PROTOCOL_VERSIONS,
    InteractionReviewService,
    communication_contract,
    communication_requires_work,
    whole_text_unit,
)
from nm.Archives.legal_brain.verify.interaction_subject import InteractionSubject
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopRecord, StepKind, digest
from nm.Archives.legal_brain.communicate.preview_display import interaction_text
from nm.Archives.legal_brain.orchestrate.work_receipts import require_work_receipts, work_receipts
from nm.shared.budget_contracts import Spend
from nm.work_the_file.file_mutation_contracts import neutral
from tests.test_communication_evidence_roles_are_owned import EvidenceJudge
from tests.test_communication_premises_require_their_own_assessment import PremiseJudge
from tests.test_communication_quotes_are_words_not_selectors import QuoteJudge
from tests.test_communication_reviews_see_actual_work import WorkJudge
from tests.test_interaction_review_units_are_server_owned import UnitJudge
from tests.test_interaction_words_require_an_independent_exact_review import InteractionJudge, _case
from tests.test_structured_work_references_are_actual_receipts import ReferenceJudge

pytestmark = pytest.mark.class_a
JUDGES = {1: InteractionJudge, 2: UnitJudge, 3: EvidenceJudge,
          4: WorkJudge, 5: QuoteJudge, 6: ReferenceJudge, 7: PremiseJudge}
MUTATIONS = ("empty", "count", "omitted", "invented", "outcome", "call", "quote_source",
             "count_float", "event_sequence_float")
TYPE_EQUIVALENT_MUTATIONS = frozenset({"count_float", "event_sequence_float"})
WORK_VERSIONS = tuple(version for version in COMMUNICATION_PROTOCOL_VERSIONS
                      if communication_requires_work(version))


def _history(tmp_path, version):
    store, brain, outcome, _, original = _case(tmp_path, kind="ask_advocate",
        text="Which record contains that date?", message="Ask what is still needed.",
        read_source=True)
    judge = JUDGES[version]()
    original.reader.model = judge
    service = InteractionReviewService(reader=original.reader, owner=original.owner,
                                       protocol_version=version)
    reviewed = service.review(outcome)
    assert reviewed.checked
    proof = next(row for row in store.load("mat_loop").loop_records
                 if row.identity.turn_id == reviewed.check_turn_id)
    assert len(judge.prompts) == 1
    # Reconstruction is a read of real saved evidence, not another evaluation.
    judge.structured = lambda *_args, **_kwargs: pytest.fail("History cannot re-run its judge")
    brain.model.tool_call.side_effect = lambda *_args, **_kwargs: pytest.fail(
        "History cannot re-run its author")
    return store, outcome, service, proof


def _alter_work(payload, mutation):
    before = deepcopy(payload)
    work = payload["work_receipts"]
    assert work["count"] == len(work["attempts"]) == 2
    if mutation == "empty":
        work.update(count=0, attempts=[])
    elif mutation == "count":
        work["count"] += 1
    elif mutation == "omitted":
        work["attempts"].pop()
        work["count"] = len(work["attempts"])
    elif mutation == "invented":
        extra = deepcopy(work["attempts"][0])
        extra["event_sequence"] += 100
        extra["event_identity"] = digest("undispatched attempt")
        extra["call"]["call_id"] = "undispatched"
        work["attempts"].append(extra)
        work["count"] = len(work["attempts"])
    elif mutation == "outcome":
        work["attempts"][0]["result"]["availability"] = "unavailable"
    elif mutation == "call":
        work["attempts"][0]["call"]["name"] = "undispatched_capability"
    elif mutation == "count_float":
        assert type(work["count"]) is int
        work["count"] = float(work["count"])
    elif mutation == "event_sequence_float":
        assert type(work["attempts"][0]["event_sequence"]) is int
        work["attempts"][0]["event_sequence"] = float(
            work["attempts"][0]["event_sequence"])
    else:
        assert mutation == "quote_source"
    source = next(row for row in payload["quote_sources"] if row["id"] == "work_receipts")
    # A separately authentic source citation cannot hide a changed typed payload.
    if mutation not in TYPE_EQUIVALENT_MUTATIONS:
        source["text"] = json.dumps(work, sort_keys=True, ensure_ascii=False, allow_nan=False)
    else:
        original_source = next(row for row in before["quote_sources"]
                               if row["id"] == "work_receipts")
        assert source == original_source
    if mutation == "quote_source":
        source["text"] = json.dumps({**work, "count": 0}, sort_keys=True,
                                    ensure_ascii=False, allow_nan=False)
    # Python equality collapses int/float and bool/int. Exact subject identity does not.
    assert digest(payload) != digest(before)


def _reseal_forged_subject(parent, proof, version, mutation, budget):
    """Preserve the real parent, protocol and words; reseal all dependent proof identities."""
    name, schema, build_prompt, interpret = communication_contract(version)
    assert proof.identity.turn_id == f"{parent.identity.turn_id}:check:{name}"
    packet = json.loads(proof.events[0].payload["prompt"]["user"])
    payload = deepcopy(packet["subject"])
    payload["kind"] = parent.events[-1].payload["reason"]
    _alter_work(payload, mutation)
    subject = InteractionSubject(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                            allow_nan=False, separators=(",", ":")))
    prompt = neutral(asdict(build_prompt(subject, subject.sources["principles"])))
    raw = deepcopy(proof.events[-1].payload["data"])
    raw["subject_identity"] = subject.identity
    raw["units"][0]["unit_id"] = whole_text_unit(subject)["unit_id"]
    if version == 7:
        raw["premise_inventory"]["unit_id"] = whole_text_unit(subject)["unit_id"]
    if version in (6, 7):
        raw["faithfulness"]["work_references"] = [{"pointer": "", "value_json": json.dumps(
            subject.payload["work_receipts"], ensure_ascii=False, allow_nan=False)}]
    else:
        raw["faithfulness"]["supporting_words"] = [{"source_id": "work_receipts",
                                                     "quote": subject.sources["work_receipts"]}]
    # Even the independent raw judgment is internally valid for the fake supplied subject.
    stop = proof.events[-1].payload
    assessed = interpret(subject, CheckRead(raw, stop["reason"], Spend(**stop["spend"]), 1),
                         budget, proof.identity.turn_id)
    assert assessed.checked and assessed.candidate_text == payload["proposed_text"]
    dispatch = next(event.payload for event in proof.events
                    if event.kind is StepKind.MODEL_STARTED)
    offer_hash = digest({"parent": parent.events[-1].fingerprint, "prompt": prompt,
        "schema": schema, "tier": "judge", "provider": dispatch["provider"],
        "model": dispatch["model"], "max_tokens": dispatch["max_tokens"]})
    identity = replace(proof.identity, offer_hash=offer_hash)
    events, previous = [], identity.fingerprint
    for event in proof.events:
        changed = event.payload
        if event.kind in (StepKind.START, StepKind.MODEL_STARTED):
            changed["prompt"] = prompt
        elif event.kind is StepKind.MODEL_RETURNED:
            changed["result"]["data"] = raw
        elif event.kind is StepKind.STOP:
            changed["data"] = raw
        rebuilt = LoopEvent.create(event.sequence, event.kind, event.at, changed, previous)
        events.append(rebuilt)
        previous = rebuilt.fingerprint
    forged = LoopRecord(identity, tuple(events))
    assert forged != proof and forged.identity.offer_hash != proof.identity.offer_hash
    assert forged.events[0].payload["schema"] == proof.events[0].payload["schema"]
    assert forged.events[-1].payload["data"] == forged.events[2].payload["result"]["data"]
    assert subject.identity != packet["subject_identity"]
    return forged


@pytest.mark.parametrize("version", COMMUNICATION_PROTOCOL_VERSIONS)
def test_every_real_protocol_history_replays_identical_words_without_model_work_or_upgrade(
        tmp_path, version):
    store, outcome, service, proof = _history(tmp_path, version)
    before = store.load("mat_loop")
    original = neutral(asdict(proof))
    text, snapshot = interaction_text(outcome.record, proof)
    assert text == outcome.proposal["question"]
    packet = json.loads(proof.events[0].payload["prompt"]["user"])
    assert snapshot == packet["subject"]["checked_snapshot"]
    assert neutral(asdict(proof)) == original and store.load("mat_loop") == before
    assert service.recorded(outcome).candidate_text == text
    assert not before.asked and not before.turn_receipts


@pytest.mark.parametrize("version", WORK_VERSIONS)
@pytest.mark.parametrize("mutation", MUTATIONS)
def test_resealed_consistent_fake_review_cannot_change_the_actual_attempted_population(
        tmp_path, version, mutation):
    store, outcome, _, proof = _history(tmp_path, version)
    before = store.load("mat_loop")
    parent_identity = digest(neutral(asdict(outcome.record)))
    assert work_receipts(outcome.record)["count"] == 2
    assert interaction_text(outcome.record, proof)[0] == outcome.proposal["question"]
    forged = _reseal_forged_subject(outcome.record, proof, version, mutation, outcome.budget)
    with pytest.raises(ReviewRefused, match="work|citation"):
        interaction_text(outcome.record, forged)
    forged_payload = json.loads(forged.events[0].payload["prompt"]["user"])["subject"]
    with pytest.raises(ReviewRefused, match="work|citation"):
        require_work_receipts(forged_payload, outcome.record)
    assert digest(neutral(asdict(outcome.record))) == parent_identity
    assert store.load("mat_loop") == before
