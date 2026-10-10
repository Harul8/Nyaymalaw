"""Same-turn evidence selection/reuse; authored verdicts do not prove semantics."""
from copy import deepcopy

from nm.brain import record_review
from nm.brain.dispute_verification import verify_disputes
from nm.brain.material import PriorReference
from tests.brain_reader_fixture import fixture_coverage, fixture_disposition
from tests.test_brain_dispute_conflict_review_mechanics import (
    Model,
    candidate,
    decision,
    treatments,
)

FIRST = "The custodian denies receiving the original inventory."
SECOND = "The client says they handed it to the custodian."
LATEST = FIRST + " " + SECOND
SCOPE = {"requests": [{"request_index": 0, "material_purposes": ["account_contribution"]}]}


def combined_decision():
    row = decision("C1", "independent_dispute", accept=True, source="L1", words=FIRST)
    other = decision("C1", "independent_dispute", accept=True, source="L2", words=SECOND)
    row["account_check"]["source_checks"].extend(other["account_check"]["source_checks"])
    return row


def reply(payload):
    return {"verdicts": [combined_decision()], "coverage": fixture_coverage(
        payload, state="complete", source_decisions={"L1": "account", "L2": "account"},
        dispositions=[fixture_disposition(payload, identity, status="represented",
                                          candidate_ids=["C1"])
                      for identity in ("L1", "L2")])}


def test_owned_same_turn_choices_keep_explicit_prior_attribution():
    selected = candidate(FIRST, earlier=(PriorReference("prior", "advocate", "Earlier account"),))
    latest = {"L1": FIRST, "L2": SECOND, "L3": "Please examine the account."}
    prior = {"P1S1": PriorReference("prior", "advocate", "Earlier account"),
             "P2S1": PriorReference("nm", "nm", "NM's analysis"),
             "P3S1": PriorReference("other", "advocate", "Unselected earlier account")}
    before = deepcopy((selected, latest, prior))

    assert record_review.candidate_account_ids(selected, latest, prior) == {
        "L1", "L2", "L3", "P1S1"}
    assert (selected, latest, prior) == before


def test_one_issue_can_have_two_checked_current_sources_and_complete_coverage():
    proposed = candidate(
        FIRST, statement="The parties dispute whether the custodian received the inventory.")
    rows = treatments((), LATEST)
    model = Model(reply)
    coverage, audit, state = {}, [], {}
    before = deepcopy((proposed, rows, SCOPE))

    accepted = verify_disputes(model, candidates=(proposed,), earlier=(), latest=LATEST,
                              active_disputes=(), source_treatments=rows, review_scope=SCOPE,
                              coverage=coverage, audit=audit, review_state=state)

    assert accepted == (proposed,) and len(model.calls) == 1 and model.claims == []
    assert audit[0]["account_check"]["source_ids"] == ["L1", "L2"]
    assert coverage["state"] == "complete"
    assert [(row["source_id"], row["candidate_ids"]) for row in coverage["dispositions"]] == [
        ("L1", ["C1"]), ("L2", ["C1"])]
    assert model.calls[0][1]["candidates"][0]["allowed_account_source_ids"] == ["L1", "L2"]
    assert (proposed, rows, SCOPE) == before


def test_foreign_source_selection_stays_unadmitted_with_owned_peer_preserved():
    proposed = candidate(FIRST)
    good = decision("C1", "independent_dispute", accept=True, source="L1", words=FIRST)
    bad = deepcopy(good)
    bad["account_check"]["source_checks"][0]["source_id"] = "foreign"
    model = Model({"verdicts": [bad]}, {"verdicts": [good]})
    audit = []

    accepted = verify_disputes(model, candidates=(proposed,), earlier=(), latest=LATEST,
                              active_disputes=(), source_treatments=treatments((), LATEST),
                              audit=audit)

    assert accepted == (proposed,) and len(model.calls) == 2
    assert model.claims == ["verify_disputes:correction"]
    assert audit[0]["account_check"]["source_ids"] == ["L1"]


def test_unchanged_multi_source_review_reuses_its_exact_durable_proof():
    proposed = candidate(FIRST)
    source_rows = treatments((), LATEST)
    state, audit = {}, []
    first = Model({"verdicts": [combined_decision()]})
    accepted = verify_disputes(first, candidates=(proposed,), earlier=(), latest=LATEST,
                              active_disputes=(), source_treatments=source_rows,
                              review_state=state, audit=audit)
    before = deepcopy(state)
    later = Model()
    reread = []

    repeated = verify_disputes(later, candidates=(proposed,), earlier=(), latest=LATEST,
                             active_disputes=(), source_treatments=source_rows,
                             review_state=state, audit=reread)

    assert accepted == repeated == (proposed,)
    assert later.calls == [] and state == before
    assert reread[0]["account_check"] == audit[0]["account_check"]


def test_unselected_source_role_change_does_not_repeat_valid_review():
    proposed = candidate(FIRST)
    rows = treatments((), LATEST)
    state = {}
    checked = decision("C1", "independent_dispute", accept=True, source="L1", words=FIRST)
    first = Model({"verdicts": [checked]})
    verify_disputes(first, candidates=(proposed,), earlier=(), latest=LATEST,
                    active_disputes=(), source_treatments=rows, review_state=state)
    changed = treatments((), LATEST, roles={"L2": "work_instruction"})
    reread = Model()

    accepted = verify_disputes(reread, candidates=(proposed,), earlier=(), latest=LATEST,
                              active_disputes=(), source_treatments=changed,
                              review_state=state, recheck_source_ids=("L2",))

    assert accepted == (proposed,) and reread.calls == []


def test_selected_negative_source_judgment_remains_a_reuse_dependency():
    proposed = candidate(FIRST)
    rows = treatments((), LATEST, roles={"L2": "work_instruction"})
    checked = combined_decision()
    negative = checked["account_check"]["source_checks"][1]
    negative.update(supplies_account_content=False, supports_proposal=False, support_spans=[])
    state = {}
    first = Model({"verdicts": [checked]})
    assert verify_disputes(first, candidates=(proposed,), earlier=(), latest=LATEST,
                           active_disputes=(), source_treatments=rows,
                           review_state=state) == (proposed,)
    changed = treatments((), LATEST)
    replacement = combined_decision()
    replacement["account_check"]["source_checks"][1]["supports_proposal"] = False
    reread = Model({"verdicts": [replacement]})

    accepted = verify_disputes(reread, candidates=(proposed,), earlier=(), latest=LATEST,
                              active_disputes=(), source_treatments=changed,
                              review_state=state, recheck_source_ids=("L2",))

    assert accepted == (proposed,) and len(reread.calls) == 1
    assert state["cache"].decisions["C1"]["account_check"]["source_ids"] == ["L1", "L2"]


def test_public_save_and_replay_retain_both_current_support_dependencies(
        client, wired, monkeypatch):
    import json
    from dataclasses import replace

    from nm.brain.turn import _current_records, chat_matter_id
    from tests.test_brain_material import Model as PublicModel
    from tests.test_brain_material import material, plan, send

    first = "Our client gave the inventory to the reviewer."
    second = "The handover occurred on 4 June."
    latest = first + " " + second
    detail = material("event", latest, first, placement="matter")
    planned = plan(
        latest, candidates=[detail], material_purposes=("account_contribution",),
        items=[{"request": latest, "relation": "new", "matter_scope": "proposed",
                "priority": "ordinary", "next_step": "answer",
                "record_requirement": {"kind": "none", "target_ids": [],
                                       "operation": "none", "success_condition": ""}}],
        dispute_scope={first: "outside_scope", second: "outside_scope"},
        coverage_links={second: {"record_ids": [], "candidate_ids": ["D1"]}})
    class PublicMultiSourceModel(PublicModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation != "verify_material_grounding":
                return result
            payload, data = json.loads(prompt.user), deepcopy(result.data)
            for row in data["verdicts"]:
                assert row["candidate_id"] == "D1"
                row["account_check"]["source_checks"] = [{
                    "source_id": identity, "supplies_account_content": True,
                    "supports_proposal": True,
                    "support_spans": [{"start": 0, "end": len(
                        payload["source_treatments"][identity]["quoted"])}],
                    "reason": "The authored event judgment uses its act and date together.",
                } for identity in ("L1", "L2")]
            return replace(result, data=data)

    model = PublicMultiSourceModel([planned])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    response = send(client, latest, "same-turn-supported-account")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metrics"]["llm_calls"] == 8, ",".join(
        row["operation"] for row in result["metrics"]["model_calls"])
    assert len(result["material"]) == 1 and result["material"][0]["quoted"] == first
    matter_id = result["matter_id"] or chat_matter_id("adv_demo", result["chat_id"])
    saved = wired.store.load(matter_id)
    execution = saved.brain_chat[0]["response"]["material_coverage"]["execution"]
    binding, = execution["coverage_application"]["bindings"]
    assert binding["review"]["account_check"]["source_ids"] == ["L1", "L2"]
    assert execution["stages"]["detail_review"]["account_coverage"]["state"] == "complete"
    reopened, _, _ = _current_records(wired.store, saved)
    assert reopened.messages[0].text == latest
    replay = send(client, latest, "same-turn-supported-account")
    assert replay.status_code == 200, replay.text
    assert replay.json()["metrics"]["llm_calls"] == 0
    assert replay.json()["material"] == result["material"]
    assert wired.store.load(matter_id).brain_chat == saved.brain_chat
