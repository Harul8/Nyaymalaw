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
from tests import core_whole_answer
from tests.test_core_answer_sources import AdjacentJudgment
from tests.test_core_research import Model as ResearchModel, understanding
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a


class ScriptedModel:
    """Payload-dependent wire fixture; never presented as an accurate model reviewer."""
    def __init__(self, *, legal=False, reject=0, malformed_writer=0, failure=None, disputes=1):
        self.legal, self.reject, self.disputes = legal, reject, disputes
        self.malformed_writer, self.failure, self.calls = malformed_writer, failure, []

    def context_budget(self, tier): return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_calculation":
            # Item 9: the scripted turns need no time limit unless a test says otherwise.
            self.calls.append((prompt.operation, prompt.user))
            return ModelResult(None, {"needed": False, "why": "No time limit is asked about.",
                                      "calculations": [], "not_assessed": []}, tier, "synthetic", "fixture",
                               Usage(1, 1, 0), 0, completion=Completion.COMPLETE)
        if prompt.operation.startswith("core_research_"):
            # Research v7 reads the conversation as attributed text, not JSON.
            self.calls.append((prompt.operation, prompt.user))
            if prompt.operation == self.failure:
                raise ProviderUnavailable("Synthetic provider outage")
            if prompt.operation in ("core_research_chronology", "core_research_transfers"):
                # The papers are read beside the understanding (research v12); these scripted ones record nothing.
                data = {"events": []} if prompt.operation == "core_research_chronology" else {"transfers": []}
                return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                                   completion=Completion.COMPLETE)
            if prompt.operation == "core_research_understand":
                latest = prompt.user.split("(the one we act on now):\n", 1)[1].split(
                    "\n\nCurrent records of this matter:", 1)[0]
                self.research = ResearchModel(understanding(disputes=self.disputes, needs_research=self.legal,
                                                            words=latest))
            return self.research.structured(prompt, schema, tier, **kwargs)
        data = json.loads(prompt.user)
        self.calls.append((prompt.operation, data))
        if prompt.operation == self.failure:
            raise ProviderUnavailable("Synthetic provider outage")
        ctx = data if prompt.operation == "core_understanding" else data["original_context"]
        latest = ctx["latest"]
        ref = {"source_id": latest["source_id"], "quote": latest["text"]}
        if prompt.operation == "core_understanding":
            # A legal turn carries information, so research v7 runs its loop; a courtesy
            # alone spares it.
            out = {"courtesies": [{"quote": latest["text"], "meaning": "A social message",
                "context": [], "unresolved": []}], "requests": [], "restrictions": [],
                "information": [{"quote": latest["text"], "meaning": "A reported position",
                                 "context": [], "unresolved": []}] if self.legal else []}
        elif prompt.operation == "core_response_writer":
            uses = []
            text = "Hello. How can I help?"
            if self.legal:
                source = next(s for s in data["held_passages"]["passages"] if s["kind"] == "judgment"
                              and "Counsel submitted" in s["text"])
                treatment = next(s for s in data["held_passages"]["passages"] if "Court rejected" in s["text"])
                uses = [{"source_id": source["id"], "source_kind": "judgment",
                    "role": "party_submission", "speaker": "Counsel",
                    "court_treatment": {"status": "rejected", "source": {"source_id": treatment["id"]}}}]
                # Writer v7: the source is linked from the writer's own words.
                text = f"The court rejected [counsel's submission]({source['id']}) because its condition was unmet."
            # Writer v8: a unit names no address; code records the latest message.
            out = {"units": [{"kind": "law" if uses else "greeting", "text": text, "uses": uses}],
                   "checklist": [], "time_limit_ids": []}
            if self.malformed_writer:
                self.malformed_writer -= 1
                out["units"][0]["text"] += " [An unoffered source](P999)."  # a link to no offered source
        elif prompt.operation == "core_response_review":
            units = data["complete_draft_proposal"]["units"]
            rejected = self.reject > 0
            self.reject -= int(rejected)
            # Review v7 (18 Oct 2026): verdict rows for the units; a wrong checklist item
            # would be named in a finding.
            out = {"verdict": "reject" if rejected else "accept",
                "units": [{"unit_id": u["id"], "verdict": "rejected" if rejected else "supported",
                           "reason": "Synthetic unit decision"} for u in units],
                "request_coverage": [{"request": ref, "disposition": "addressed",
                    "unit_ids": [u["id"] for u in units], "reason": "Synthetic coverage"}],
                "findings": [{"category": "attribution", "unit_ids": [units[0]["id"]],
                    "sources": [ref], "mismatch": "Synthetic attribution rejection"}] if rejected else []}
            if "units" not in schema["properties"]:  # review v8 names only what is wrong
                out.pop("units")
            if "misleading" in schema["properties"]:  # review v10 (P29): what misleads, what could be better
                out = {"misleading": [{"kind": "misattributed", "where": [units[0]["id"]], "evidence": [ref],
                                       "why": "Synthetic attribution rejection"}] if rejected else [],
                       "could_be_better": []}
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
    assert response["committed"] == "committed" and response["metrics"]["llm_calls"] == 9
    names = [name for name, _ in model.calls]
    # The interpretation and the matter's first understanding are written together (18 Oct 2026).
    assert sorted(names[:2]) == ["core_research_understand", "core_understanding"]
    assert sorted(names[3:5]) == ["core_research_judgment_phrases", "core_research_phrases"]  # in parallel
    assert sorted(names[5:7]) == ["core_research_judgment_pick", "core_research_pick"]  # in parallel
    assert names[2:3] + names[7:] == ["core_research_check", "core_response_writer", "core_response_review"]
    stored = store.load(chat_matter_id("owner", response["chat_id"]))
    rows = saved_rows(stored, "owner")
    # Answered dispute by dispute (owner decisions P25-P27, 19 Oct 2026): one dispute, one section.
    assert rows[0]["activities"]["contract"] == "core_turn_v9"
    # No held Acts were given to this turn, so no time limit was worked out (item 9).
    assert rows[0]["activities"]["calculation"]["state"] == "not_needed"
    section, = rows[0]["activities"]["sections"]
    assert section["reviewed"]["review"]["contract"] == "core_response_review_v12"
    assert section["looks"] == [] and section["reviewed"]["writer_notes"] == []
    assert section["reviewed"]["authority_evidence"]["contract"] == "core_response_authorities_v1"
    assert section["trims"] == [] and section["fallback"] is None and section["edit"] is None
    assert rows[0]["activities"]["cross_check"] is None and rows[0]["activities"]["overview"] is None
    assert rows[0]["response"] == response
    cited = next(element for element in response["elements"] if element.get("sources"))
    source = cited["source"]
    assert source["verification"]["source_treatment"] == "rejected"
    assert "Court rejected" in source["verification"]["treatment_excerpt"]
    assert len(cited["sources"]) == 2
    assert run(store, model) == {**response, "replayed": True}
    assert len(model.calls) == 9


def test_mixed_legacy_and_current_history_reopens_without_fresh_authority_checks(store, monkeypatch):
    from nm.core_engine import response_authorities, response_rendering, response_review, turn
    from nm.core_engine.conversation import commit_turn, open_turn

    context = open_turn(store, advocate_id="owner", message="Earlier account.", turn_id="old")
    _, activity, metrics = core_whole_answer.prepare(ScriptedModel(), context.payload(), searcher())
    original = context.payload()
    activity.pop("authority_evidence")
    activity.pop("calculation")
    activity.pop("release")
    activity["contract"] = turn.LEGACY_CONTRACT
    activity["rendering_contract"] = response_rendering.LEGACY_CONTRACT
    dependencies = response_review._dependencies(original, activity["research"],
        activity["sources"], activity["draft"], activity["execution"],
        contract=response_review.LEGACY_CONTRACT)
    # A legacy record holds owned IDs only; short IDs began on 16 Oct 2026.
    from nm.core_engine import answer_sources
    from nm.core_engine.understanding import renamed
    legacy = renamed(activity["review"]["proposal"], answer_sources.aliases(activity["sources"]))
    # A legacy review gave every unit a verdict row; review v8 gives none.
    legacy["units"] = [{"unit_id": unit["id"], "verdict": "supported", "reason": "Synthetic unit decision"}
                       for unit in activity["draft"]["units"]]
    activity["review"] = response_review._accept(legacy, dependencies, contract=response_review.LEGACY_CONTRACT)
    elements = response_rendering.render(original, activity["research"], activity["sources"],
        activity["draft"], activity["review"], execution=activity["execution"],
        contract=response_rendering.LEGACY_CONTRACT)
    first = commit_turn(store, context, elements=elements, activities=activity, metrics=metrics,
                        session_current=lambda: True)
    model = ScriptedModel()
    second = run(store, model, chat_id=first["chat_id"], turn_id="new", message="Continue.")
    # The matter's first understanding is written beside the interpretation, which finds no
    # matter here, so that understanding is the one call more (18 Oct 2026).
    assert second["committed"] == "committed" and len(model.calls) == 4

    def no_new_check(*args, **kwargs):
        raise AssertionError("Saved readback cannot consult current authority indexes")
    monkeypatch.setattr(response_authorities, "check", no_new_check)
    rows = saved_rows(store.load(chat_matter_id("owner", first["chat_id"])), "owner")
    assert [row["activities"]["contract"] for row in rows] == ["core_turn_v1", "core_turn_v9"]
    assert rows[0]["response"]["elements"] == elements
    assert run(store, model, chat_id=first["chat_id"], turn_id="new", message="Continue.")["replayed"]
    assert len(model.calls) == 4


@pytest.mark.parametrize("saved", ["core_response_rendering_v2", "core_response_rendering_v3",
                                   "core_response_rendering_v4", "core_response_rendering_v5",
                                   "core_response_rendering_v6", "core_response_rendering_v7"])
def test_a_turn_saved_under_an_earlier_rendering_reopens_unchanged_beside_a_current_turn(store, saved):
    """Shown names (v3) and cited-word links (v4) never rewrite an earlier saved response."""
    from nm.core_engine import response_rendering, turn
    from nm.core_engine.conversation import commit_turn, open_turn

    context = open_turn(store, advocate_id="owner", message="Earlier account.", turn_id="old")
    _, activity, metrics = core_whole_answer.prepare(ScriptedModel(), context.payload(), searcher())
    original = context.payload()
    # A turn saved before item 9: no calculation, under the version with authority evidence.
    activity.pop("calculation")
    activity.pop("release")
    activity["contract"] = turn.AUTHORITY_CONTRACT
    activity["rendering_contract"] = saved
    elements = response_rendering.render(original, activity["research"], activity["sources"],
        activity["draft"], activity["review"], execution=activity["execution"],
        authority_evidence=activity["authority_evidence"], contract=saved)
    first = commit_turn(store, context, elements=elements, activities=activity, metrics=metrics,
                        session_current=lambda: True)
    second = run(store, ScriptedModel(), chat_id=first["chat_id"], turn_id="new", message="Continue.")
    assert second["committed"] == "committed"
    rows = saved_rows(store.load(chat_matter_id("owner", first["chat_id"])), "owner")
    assert [row["activities"]["rendering_contract"] for row in rows] == [
        saved, "core_response_rendering_v19"]
    assert rows[0]["response"]["elements"] == elements
    if saved not in ("core_response_rendering_v4", "core_response_rendering_v5", "core_response_rendering_v6",
                     "core_response_rendering_v7"):
        assert all("citation_markers" not in element for element in rows[0]["response"]["elements"])


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
    # The review is shown each reply unit by its short ID (16 Oct 2026), in order.
    plain = lambda units: [{k: v for k, v in unit.items() if k != "unit_id"} for unit in units]  # noqa: E731
    assert [plain(row["units"]) for row in checked] == [plain(row["units"]) for row in reviews]
    assert all([u["unit_id"] for u in row["units"]] == [f"U{n}" for n in range(1, len(row["units"]) + 1)]
               for row in reviews)


def test_complete_conversation_survives_followup_and_restriction_words(store):
    model = ScriptedModel()
    first = run(store, model, message="Do not contact anyone. The account is disputed.")
    second = run(store, model, chat_id=first["chat_id"], turn_id="t2", message="Hello again.")
    assert second["metrics"]["llm_calls"] == 4
    for operation, payload in model.calls[4:]:
        if operation == "core_research_understand":
            continue  # the matter's first understanding reads the conversation as text
        context = payload if operation == "core_understanding" else payload["original_context"]
        assert context["conversation"][0]["text"] == "Do not contact anyone. The account is disputed."
        assert context["conversation"][1]["text"] == first["elements"][0]["text"]


def answering(model):
    """The writer and review calls, in order."""
    return [payload for name, payload in model.calls if name in ("core_response_writer", "core_response_review")]


def test_reviewer_rejection_uses_one_second_look_and_new_independent_review(store):
    # Turn v9 (AN.28, D2): only the paragraph the review faults goes back, and the answer is reviewed again.
    model = ScriptedModel(reject=1)
    model.second_looks = []
    response = run(store, model)
    assert response["metrics"]["llm_calls"] == 6
    assert response["metrics"]["draft_corrections"] == 1
    assert [call["operation"] for call in response["metrics"]["calls"]][-3:] == [
        "core_response_review", "core_response_repair", "core_response_review"]
    looked, = model.second_looks
    assert [entry["paragraph"] for entry in looked] == ["U1"] and looked[0]["why"] == ["Synthetic attribution rejection"]


def test_a_section_has_two_second_looks_each_told_what_was_found(store):
    # Owner decision P25, 19 Oct 2026: "At most we can do a third try"; from turn v9 (AN.28, D2) each try after
    # the first is a second look at only the paragraphs at fault, told why and shown the piece as written.
    model = ScriptedModel(reject=2)
    model.second_looks = []
    response = run(store, model)
    assert response["committed"] == "committed"
    assert response["metrics"]["llm_calls"] == 8 and response["metrics"]["draft_corrections"] == 2
    assert [call["operation"] for call in response["metrics"]["calls"]].count("core_response_repair") == 2
    assert [[entry["paragraph"] for entry in looked] for looked in model.second_looks] == [["U1"], ["U1"]]
    assert all(looked[0]["why"] == ["Synthetic attribution rejection"] for looked in model.second_looks)
    # A reply covering no dispute is a simple, straight answer (P40, O13): its paragraph as advice.
    assert [element["kind"] for element in response["elements"]] == ["ADVICE"]


def test_nothing_is_withheld_whole_a_note_stands_where_nothing_survives(store):
    # Owner decision P25: after the third try the faulted statements are left out; here the
    # only one is, so code's own note stands in the answer's place and is saved.
    model = ScriptedModel(reject=3)
    response = run(store, model)
    assert response["committed"] == "committed" and response["metrics"]["llm_calls"] == 8
    note, = response["elements"]
    assert note["kind"] == "FALLBACK" and note["disclosure"] and note["sources"] == []
    # What the check found is said in code's words, never the reviewer's words about it.
    assert note["text"] == (
        "NM could not give a reliable reply to this message: after the rewrites NM may make, the checks still "
        "found problems in it that leaving statements out could not settle. What was found: A statement was "
        "attributed to a judgment from a passage that is not the court's own reasoning. You can send it again, or "
        "narrow it.")
    assert "Synthetic attribution rejection" not in str(note)
    rows = saved_rows(store.load(chat_matter_id("owner", response["chat_id"])), "owner")
    assert rows[0]["activities"]["sections"][0]["fallback"] == {"reason": "found"}
    assert run(store, model) == {**response, "replayed": True} and len(model.calls) == 8


def test_a_shape_repair_counts_among_the_sections_tries(store):
    # The section's draft and two rewrites, whatever asked for them (P25).
    model = ScriptedModel(malformed_writer=1, reject=1)
    assert run(store, model)["metrics"]["draft_corrections"] == 2
    assert len(model.calls) == 7
    model = ScriptedModel(malformed_writer=1, reject=2)
    response = run(store, model, turn_id="another-turn")
    assert len(model.calls) == 7 and response["metrics"]["draft_corrections"] == 2
    assert [element["kind"] for element in response["elements"]] == ["FALLBACK"]


def test_provider_outage_never_saves_an_empty_success(store, caplog):
    with pytest.raises(ConversationRefused) as error:
        run(store, ScriptedModel(failure="core_response_review"))
    assert error.value.code == "response_unavailable" and error.value.committed == "not_committed"
    assert not store.list_for("owner").matters
    # The provider failure's own kind and message are logged for diagnosis (17 Oct 2026).
    logged, = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Message not answered")]
    assert logged.endswith("(ProviderUnavailable: Synthetic provider outage)")


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
    with pytest.raises(ConversationRefused) as outage: run(store, model)
    # The service failed for the only section: nothing is saved and the message can be sent again.
    assert outage.value.code == "response_unavailable" and outage.value.retryable
    assert len(model.calls) == 5
    model.failure, model.reject = None, 2
    retry = run(store, model)
    # The resumed request keeps its spent correction in the turn's durable count; its
    # section has its own tries again (owner decision P25).
    assert retry["committed"] == "committed" and retry["metrics"]["draft_corrections"] == 3
    assert len(model.calls) == 13


def test_permission_loss_after_correction_does_not_reset_allowance(store):
    model = ScriptedModel(malformed_writer=1)
    original = model.structured
    def guarded(prompt, *args, **kw):
        if prompt.operation == "core_response_review":
            raise ModelPermissionRefused("Synthetic revoked permission")
        return original(prompt, *args, **kw)
    model.structured = guarded
    with pytest.raises(ModelPermissionRefused): run(store, model)
    model.structured, model.reject = original, 2
    resumed = run(store, model)
    # Four calls before the denied review, then the section's three tries; the spent shape
    # correction stays in the turn's durable count.
    assert resumed["committed"] == "committed" and resumed["metrics"]["draft_corrections"] == 3
    assert len(model.calls) == 12


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
def test_a_resealed_record_is_read_as_saved_and_one_of_an_unknown_version_is_never_upgraded(store, damage):
    # P46 (24 Oct 2026): reading a saved conversation checks the record - its seal, receipts,
    # digest chain, owner and versions - and never rebuilds an answer. A record resealed with
    # its digests made whole is read exactly as saved; one of a version this code does not
    # read is refused.
    from nm.core_engine import turn

    model = ScriptedModel()
    first = run(store, model)
    matter = store.load(chat_matter_id("owner", first["chat_id"]))
    rows = deepcopy(matter.brain_chat)
    if damage == "rendering": rows[0]["activities"]["rendering_contract"] = "unknown_future"
    elif damage == "review": rows[0]["activities"]["sections"][0]["reviewed"]["review"]["accepted"] = False
    else: rows[0]["response"]["elements"][0]["text"] = "Altered response"
    rows[0]["digest"] = digest({k: v for k, v in rows[0].items() if k != "digest"})
    metadata = deepcopy(matter.intake_answers)
    metadata["core_conversation"]["tail_digest"] = rows[0]["digest"]
    store.commit(replace(matter, brain_chat=rows, intake_answers=metadata, version=matter.version + 1),
                 expected_version=matter.version)
    resealed = store.load(matter.id)
    if damage == "rendering":
        with pytest.raises(ConversationRefused, match="read reliably"): run(store, model)
        with pytest.raises(ConversationRefused, match="read reliably"): turn.saved_rows(resealed, "owner")
    else:
        assert list(turn.saved_rows(resealed, "owner")) == list(rows)
    assert len(model.calls) == 4


@pytest.mark.parametrize("saved", ["core_response_rendering_v8", "core_response_rendering_v9"])
def test_a_turn_saved_before_sections_could_be_held_reopens_unchanged(store, saved):
    # 17 Oct 2026: v4 records what was released; a v3 turn has no such record and keeps its rendering.
    from nm.core_engine import response_rendering, turn
    from nm.core_engine.conversation import commit_turn, open_turn

    context = open_turn(store, advocate_id="owner", message="Earlier account.", turn_id="old")
    _, activity, metrics = core_whole_answer.prepare(ScriptedModel(), context.payload(), searcher())
    original = context.payload()
    activity.pop("release")
    activity["contract"] = turn.CALCULATION_CONTRACT
    activity["rendering_contract"] = saved
    elements = response_rendering.render(original, activity["research"], activity["sources"],
        activity["draft"], activity["review"], execution=activity["execution"],
        authority_evidence=activity["authority_evidence"], contract=saved, time_limits=activity["calculation"])
    first = commit_turn(store, context, elements=elements, activities=activity, metrics=metrics,
                        session_current=lambda: True)
    second = run(store, ScriptedModel(), chat_id=first["chat_id"], turn_id="new", message="Continue.")
    assert second["committed"] == "committed"
    rows = saved_rows(store.load(chat_matter_id("owner", first["chat_id"])), "owner")
    assert [row["activities"]["contract"] for row in rows] == ["core_turn_v3", "core_turn_v9"]
    assert rows[0]["response"]["elements"] == elements
    assert all("unit" not in element for element in elements)
    assert all("unit" in element for element in rows[1]["response"]["elements"])


def test_the_interpretation_and_the_matters_first_understanding_are_written_together(store):
    """Owner, 18 Oct 2026, for speed: the matter's first understanding reads the conversation
    itself, so it no longer waits for the message's interpretation."""
    import threading
    started = threading.Event()

    class Together(ScriptedModel):
        def structured(self, prompt, schema, tier, **kwargs):
            if prompt.operation == "core_research_understand":
                started.set()
            elif prompt.operation == "core_understanding":
                assert started.wait(timeout=10), "the matter's understanding waited for the interpretation"
            return super().structured(prompt, schema, tier, **kwargs)
    response = run(store, Together(legal=True))
    assert response["committed"] == "committed" and response["metrics"]["llm_calls"] == 9
