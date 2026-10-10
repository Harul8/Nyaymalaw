"""Four-stage integration and persistence; scripted verdicts are wiring evidence only."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from nm.core_engine.conversation import ConversationRefused, chat_matter_id, digest
from nm.core_engine.retrieval import HybridSearcher
from nm.core_engine.turn import process, saved_rows
from nm.shared.budget_contracts import Completion
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.egress_contracts import EgressRefused
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage
from nm.shared.store_file_store import FileMatterStore
from nm.shared.turn_attempt_store import FileTurnAttempts
from tests.test_core_answer_sources import AdjacentJudgment
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a


class ScriptedModel:
    """Payload-dependent wire fixture; never presented as an accurate model reviewer."""
    def __init__(self, *, legal=False, reject=0, malformed_writer=0, failure=None):
        self.legal, self.reject = legal, reject
        self.malformed_writer, self.failure, self.calls = malformed_writer, failure, []

    def context_budget(self, tier): return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        data = json.loads(prompt.user)
        self.calls.append((prompt.operation, data))
        if prompt.operation == self.failure:
            raise ProviderUnavailable("Synthetic provider outage")
        ctx = data if prompt.operation == "core_understanding" else data["original_context"]
        latest = ctx["latest"]
        ref = {"source_id": latest["source_id"], "quote": latest["text"]}
        if prompt.operation == "core_understanding":
            out = {"courtesies": [{"quote": latest["text"], "meaning": "A social message",
                "context": [], "unresolved": []}], "information": [], "requests": [], "restrictions": []}
        elif prompt.operation == "core_research_plan":
            out = {"work": [{"purpose": "Inspect held law", "outcome": "Supported account",
                "sources": [ref], "constraints": [], "unresolved": [], "enquiries": [{
                    "text": "conditions and contrary authority", "purpose": "Identify scope",
                    "basis": "conditional"}]}] if self.legal else []}
        elif prompt.operation == "core_response_writer":
            uses = []
            text = "Hello. How can I help?"
            if self.legal:
                source = next(s for s in data["held_passages"]["passages"] if s["kind"] == "judgment"
                              and "Counsel submitted" in s["text"])
                treatment = next(s for s in data["held_passages"]["passages"] if "Court rejected" in s["text"])
                uses = [{"source_id": source["id"], "quote": source["text"],
                    "role": "party_submission", "speaker": "Counsel", "treatment": "rejected",
                    "treatment_source": {"source_id": treatment["id"], "quote": treatment["text"]}}]
                text = "The court rejected counsel's submission because its condition was unmet."
            out = {"units": [{"kind": "law" if uses else "greeting", "text": text,
                              "addresses": [ref], "uses": uses}]}
            if self.malformed_writer:
                self.malformed_writer -= 1
                out["units"][0]["addresses"][0]["quote"] = "Absent quotation"
        elif prompt.operation == "core_response_review":
            units = data["complete_draft_proposal"]["units"]
            rejected = self.reject > 0
            self.reject -= int(rejected)
            out = {"verdict": "reject" if rejected else "accept",
                "units": [{"unit_id": u["id"], "verdict": "rejected" if rejected else "supported",
                           "reason": "Synthetic unit decision"} for u in units],
                "request_coverage": [{"request": ref, "disposition": "addressed",
                    "unit_ids": [u["id"] for u in units], "reason": "Synthetic coverage"}],
                "findings": [{"category": "attribution", "unit_ids": [units[0]["id"]],
                    "sources": [ref], "mismatch": "Synthetic attribution rejection"}] if rejected else []}
        else:
            raise AssertionError(prompt.operation)
        return ModelResult(None, out, tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def searcher():
    return HybridSearcher({"provision": Collection(), "judgment": AdjacentJudgment()})


def run(store, model, **changes):
    return process(model, store, searcher(), **{"advocate_id": "owner", "message": "Hello.",
        "turn_id": "t1", "session_current": lambda: True,
        "attempts": FileTurnAttempts(store._root / "attempts.sqlite"), **changes})


@pytest.fixture
def store(tmp_path): return FileMatterStore(tmp_path, key="synthetic-turn-fixture")


def test_four_actual_stage_calls_save_reopen_and_replay_without_reexecution(store):
    model = ScriptedModel(legal=True)
    response = run(store, model)
    assert response["committed"] == "committed" and response["metrics"]["llm_calls"] == 4
    assert [name for name, _ in model.calls] == ["core_understanding", "core_research_plan",
                                                "core_response_writer", "core_response_review"]
    stored = store.load(chat_matter_id("owner", response["chat_id"]))
    rows = saved_rows(stored, "owner")
    assert rows[0]["activities"]["contract"] == "core_turn_v2"
    assert rows[0]["activities"]["review"]["contract"] == "core_response_review_v2"
    assert rows[0]["activities"]["authority_evidence"]["contract"] == "core_response_authorities_v1"
    assert rows[0]["response"] == response
    source = response["elements"][0]["source"]
    assert source["verification"]["source_treatment"] == "rejected"
    assert "Court rejected" in source["verification"]["treatment_excerpt"]
    assert len(response["elements"][0]["sources"]) == 2
    assert run(store, model) == {**response, "replayed": True}
    assert len(model.calls) == 4


def test_mixed_legacy_and_current_history_reopens_without_fresh_authority_checks(store, monkeypatch):
    from nm.core_engine import response_authorities, response_rendering, response_review, turn
    from nm.core_engine.conversation import commit_turn, open_turn

    context = open_turn(store, advocate_id="owner", message="Earlier account.", turn_id="old")
    _, activity, metrics = turn.prepare(ScriptedModel(), context.payload(), searcher())
    original = context.payload()
    activity.pop("authority_evidence")
    activity["contract"] = turn.LEGACY_CONTRACT
    activity["rendering_contract"] = response_rendering.LEGACY_CONTRACT
    dependencies = response_review._dependencies(original, activity["research"],
        activity["sources"], activity["draft"], activity["execution"],
        contract=response_review.LEGACY_CONTRACT)
    activity["review"] = response_review._accept(activity["review"]["proposal"], dependencies,
        contract=response_review.LEGACY_CONTRACT)
    elements = response_rendering.render(original, activity["research"], activity["sources"],
        activity["draft"], activity["review"], execution=activity["execution"],
        contract=response_rendering.LEGACY_CONTRACT)
    first = commit_turn(store, context, elements=elements, activities=activity, metrics=metrics,
                        session_current=lambda: True)
    model = ScriptedModel()
    second = run(store, model, chat_id=first["chat_id"], turn_id="new", message="Continue.")
    assert second["committed"] == "committed" and len(model.calls) == 4

    def no_new_check(*args, **kwargs):
        raise AssertionError("Saved readback cannot consult current authority indexes")
    monkeypatch.setattr(response_authorities, "check", no_new_check)
    rows = saved_rows(store.load(chat_matter_id("owner", first["chat_id"])), "owner")
    assert [row["activities"]["contract"] for row in rows] == ["core_turn_v1", "core_turn_v2"]
    assert rows[0]["response"]["elements"] == elements
    assert run(store, model, chat_id=first["chat_id"], turn_id="new", message="Continue.")["replayed"]
    assert len(model.calls) == 4


def test_rewritten_draft_recomputes_its_authority_evidence_before_review(store, monkeypatch):
    from nm.core_engine import response_authorities
    original = response_authorities.check
    checked = []

    def record(*args, **kwargs):
        evidence = original(*args, **kwargs)
        checked.append(evidence)
        return evidence
    monkeypatch.setattr(response_authorities, "check", record)
    model = ScriptedModel(reject=1)
    result = run(store, model)
    reviews = [payload["owned_authority_checks"] for name, payload in model.calls
               if name == "core_response_review"]
    assert result["metrics"]["llm_calls"] == 6 and len(checked) == len(reviews) == 2
    assert [row["units"] for row in checked] == [row["units"] for row in reviews]


def test_complete_conversation_survives_followup_and_restriction_words(store):
    model = ScriptedModel()
    first = run(store, model, message="Do not contact anyone. The account is disputed.")
    second = run(store, model, chat_id=first["chat_id"], turn_id="t2", message="Hello again.")
    assert second["metrics"]["llm_calls"] == 4
    for operation, payload in model.calls[4:]:
        context = payload if operation == "core_understanding" else payload["original_context"]
        assert context["conversation"][0]["text"] == "Do not contact anyone. The account is disputed."
        assert context["conversation"][1]["text"] == first["elements"][0]["text"]


def test_reviewer_rejection_uses_one_rewrite_and_new_independent_review(store):
    model = ScriptedModel(reject=1)
    response = run(store, model)
    assert response["metrics"]["llm_calls"] == 6
    assert response["metrics"]["draft_corrections"] == 1
    assert "correction" in model.calls[4][1]
    assert "correction" not in model.calls[5][1]


def test_repeated_rejection_withholds_entire_turn_without_save(store):
    model = ScriptedModel(reject=2)
    with pytest.raises(ConversationRefused) as error: run(store, model)
    assert error.value.code == "answer_withheld" and not error.value.retryable
    assert error.value.metrics["llm_calls"] == 6
    assert not store.list_for("owner").matters
    with pytest.raises(ConversationRefused) as replay: run(store, model)
    assert replay.value.code == "answer_withheld"
    assert len(model.calls) == 6  # Model would accept now; the terminal owner refuses first.
    assert run(store, model, turn_id="genuinely-new-turn")["committed"] == "committed"


def test_shape_repair_and_semantic_repair_cannot_each_get_new_allowance(store):
    model = ScriptedModel(malformed_writer=1, reject=1)
    with pytest.raises(ConversationRefused) as error: run(store, model)
    assert error.value.code == "answer_withheld"
    assert len(model.calls) == 5
    assert not store.list_for("owner").matters


def test_provider_outage_never_saves_an_empty_success(store):
    with pytest.raises(ConversationRefused) as error:
        run(store, ScriptedModel(failure="core_response_review"))
    assert error.value.code == "response_unavailable" and error.value.committed == "not_committed"
    assert not store.list_for("owner").matters


def test_lost_acknowledgement_replays_saved_checked_response_once(store):
    class LostAck:
        _root = store._root
        load = store.load
        def commit(self, matter, **kw):
            store.commit(matter, **kw)
            raise OSError("Synthetic lost acknowledgement")
    model = ScriptedModel()
    first = run(LostAck(), model)
    assert run(store, model)["replayed"]
    assert len(model.calls) == 4
    assert len(store.load(chat_matter_id("owner", first["chat_id"])).brain_chat) == 1


def test_spent_correction_survives_retry_after_provider_outage(store):
    model = ScriptedModel(malformed_writer=1, failure="core_response_review")
    with pytest.raises(ConversationRefused): run(store, model)
    assert len(model.calls) == 5
    model.failure, model.reject = None, 1
    with pytest.raises(ConversationRefused) as retry: run(store, model)
    assert retry.value.code == "answer_withheld"
    assert len(model.calls) == 9  # No second rewrite after the same request resumes.


def test_permission_loss_after_correction_does_not_reset_allowance(store):
    model = ScriptedModel(malformed_writer=1)
    original = model.structured
    def guarded(prompt, *args, **kw):
        if prompt.operation == "core_response_review":
            raise ModelPermissionRefused("Synthetic revoked permission")
        return original(prompt, *args, **kw)
    model.structured = guarded
    with pytest.raises(ModelPermissionRefused): run(store, model)
    model.structured, model.reject = original, 1
    with pytest.raises(ConversationRefused) as rejected: run(store, model)
    assert rejected.value.code == "answer_withheld"
    assert len(model.calls) == 8  # Four before denied review, then four; no second correction.


def test_known_pre_save_session_loss_allows_same_request_recovery(store):
    checks = iter([True, False])
    model = ScriptedModel()
    with pytest.raises(ConversationRefused) as refused:
        run(store, model, session_current=lambda: next(checks))
    assert refused.value.committed == "not_committed"
    assert not store.list_for("owner").matters
    assert run(store, model)["committed"] == "committed"


def test_post_commit_auxiliary_policy_failure_cannot_hide_saved_response(store):
    inner = FileTurnAttempts(store._root / "auxiliary.sqlite")
    class DeniedFinish:
        claim = inner.claim
        consume_correction = inner.consume_correction
        def finish(self, *args, **kw):
            raise EgressRefused("Synthetic auxiliary storage policy denial")
    model = ScriptedModel()
    reply = run(store, model, attempts=DeniedFinish())
    assert reply["committed"] == "committed"
    assert run(store, model, attempts=DeniedFinish())["replayed"]
    assert len(model.calls) == 4


@pytest.mark.parametrize("damage", ["rendering", "review", "text"])
def test_resealed_but_incompatible_saved_evidence_is_never_upgraded(store, damage):
    model = ScriptedModel()
    first = run(store, model)
    matter = store.load(chat_matter_id("owner", first["chat_id"]))
    rows = deepcopy(matter.brain_chat)
    if damage == "rendering": rows[0]["activities"]["rendering_contract"] = "unknown_future"
    elif damage == "review": rows[0]["activities"]["review"]["accepted"] = False
    else: rows[0]["response"]["elements"][0]["text"] = "Altered response"
    rows[0]["digest"] = digest({k: v for k, v in rows[0].items() if k != "digest"})
    metadata = deepcopy(matter.intake_answers)
    metadata["core_conversation"]["tail_digest"] = rows[0]["digest"]
    store.commit(replace(matter, brain_chat=rows, intake_answers=metadata, version=matter.version + 1),
                 expected_version=matter.version)
    with pytest.raises(ConversationRefused, match="read reliably"): run(store, model)
    assert len(model.calls) == 4
