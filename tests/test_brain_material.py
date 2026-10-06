"""Legal material is a sourced proposal from each served conversation turn."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.turn import chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, Usage
from tests.brain_continuation_fixture import (
    continuation_reply,
    interpretation,
    no_record_requirement,
)
from tests.brain_reader_fixture import (
    fixture_scoped_coverage,
    fresh_review_reply,
    reader_operations,
    reader_repairs,
    reviewed_record_verdicts,
    source_portion_reply,
)


def fixture_scope_judgment(payload, reviewed, *, source_purposes=None,
                           dispute_scope=None, coverage_links=None):
    """Normal scenarios author account and framed instruction purposes explicitly."""
    authored = source_purposes or {}
    decisions = {identity: authored.get(
        payload["source_treatments"][identity]["quoted"].strip(), "account")
        for identity in payload["coverage_source_ids"]}
    if dispute_scope is not None:
        # The fixture author declares the distinct-dispute stage's scope
        # before extraction. Reader emptiness and rejected output are ignored.
        decisions = {identity: purpose if purpose == "non_account" else dispute_scope.get(
            payload["source_treatments"][identity]["quoted"].strip(), "outside_scope")
            for identity, purpose in decisions.items()}
    links = {identity: deepcopy(coverage_links[reference["quoted"].strip()])
             for identity, reference in payload["source_treatments"].items()
             if reference["quoted"].strip() in (coverage_links or {})}
    return fixture_scoped_coverage(payload, reviewed, source_decisions=decisions,
                                   representation_choices=links)



class Model:
    def __init__(self, plans, *, source_purposes=None):
        self.plans = iter(plans)
        self.source_purposes = dict(source_purposes or {})
        self.dispute_scope = {}
        self.coverage_links = {}
        self.calls = []
        self.material_calls = []
        self.next_material = []
        self.current_items = []
        self.current_record_disposition = None
        self.current_response_expressions = {}

    def context_budget(self, tier):
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return 20000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        continuation = continuation_reply(prompt.operation, json.loads(prompt.user),
                                          scripted_items=self.current_items)
        if prompt.operation == "classify_account_sources":
            payload = json.loads(prompt.user)
            original = payload.get("original_input", payload)
            data = source_portion_reply(payload, {"source_treatments": {identity: {
                "content_role": ("work_instruction" if self.source_purposes.get(
                    reference["quoted"].strip()) == "non_account"
                    else "reported_matter_account"),
                "reason": "The scenario owner independently declares the source purpose.",
            } for identity, reference in original["original_source_catalogue"].items()}})
        elif continuation is not None:
            data = continuation
            if prompt.operation == "continue_conversation":
                for unit in data["units"]:
                    expression = self.current_response_expressions.get(unit["request_index"])
                    if expression is not None:
                        unit["blocks"][0]["evidence_expression"] = deepcopy(expression)
        elif prompt.operation in ("extract_disputes", "extract_legal_details"):
            self.material_calls.append(prompt)
            payload = json.loads(prompt.user)
            sources = payload.get("original_input", payload)
            rows = [_with_source_ids(row, sources) for row in self.next_material]
            if prompt.operation == "extract_disputes":
                data = reader_operations([
                    {key: value for key, value in row.items() if key != "kind"}
                    for row in rows if row["kind"] == "dispute"], sources,
                    link_field="related_dispute_ids")
            else:
                data = reader_operations([row for row in rows
                                          if row["kind"] != "dispute"], sources,
                                         link_field="related_material_ids")
            data = reader_repairs(data, schema)
        elif prompt.operation in ("verify_disputes", "verify_material_grounding"):
            payload = json.loads(prompt.user)
            data = {"verdicts": [
                {"candidate_id": row["candidate_id"],
                 "operation_supported": True,
                 **({"candidate_role": "independent_dispute"}
                    if prompt.operation == "verify_disputes" else {}),
                 "verdict": "accept", "reason": "Attributable proposal"}
                for row in payload["candidates"]]}
            data = reviewed_record_verdicts(
                payload, data, scripted_full_scope=True, scripted_source_account=True,
                    coverage_judgment=lambda p, rows: fixture_scope_judgment(
                        p, rows, source_purposes=self.source_purposes,
                        dispute_scope=self.dispute_scope
                        if prompt.operation == "verify_disputes" else None,
                        coverage_links=self.coverage_links
                        if prompt.operation == "verify_material_grounding" else None))
        else:
            self.calls.append(prompt)
            planned = next(self.plans)
            self.next_material = planned["material"]
            self.source_purposes.update(planned.get("_source_purposes", {}))
            self.dispute_scope.update(planned.get("_dispute_scope", {}))
            self.coverage_links = planned.get("_coverage_links", {})
            self.current_record_disposition = planned.get("_record_disposition")
            self.current_response_expressions = planned.get("_response_expressions", {})
            data = {key: value for key, value in planned.items()
                    if key not in ("material", "_record_disposition", "_response_expressions",
                                   "_source_purposes", "_dispute_scope", "_coverage_links")}
            if prompt.operation == "interpret_conversation":
                data = interpretation(data)
                data = scripted_request_scope_transport(
                    data, json.loads(prompt.user), scripted_items=planned["items"])
                self.current_items = data["items"]
        data = scripted_record_result(
            prompt.operation, json.loads(prompt.user), data, self.current_record_disposition)
        data = fresh_review_reply(json.loads(prompt.user), data)
        return ModelResult(text=None, data=data, tier=tier,
                           provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


def scripted_request_scope_transport(data, payload, *, scripted_items):
    """Transport only independently authored permission, never reader proposals.

    Explicit interpreter scopes pass through unchanged. An independently typed
    change request can provide its own targets and relation. Reader proposals
    are not an input to this transport boundary.
    """
    from copy import deepcopy

    from nm.brain.conversation import Message
    from nm.brain.material import addressed_sources

    result = deepcopy(data)
    payload = payload.get("original_input", payload)
    earlier = tuple(Message(row["turn_id"], row["role"], row["text"])
                    for row in payload["earlier_conversation"])
    _, current, _ = addressed_sources(earlier, payload["latest_message"])
    for item, authored in zip(result["items"], scripted_items, strict=True):
        if "mutation_scopes" in authored:
            continue
        requirement = item.get("record_requirement", no_record_requirement())
        scopes = []
        if requirement["kind"] == "change":
            # The request owner supplies permission independently of extraction.
            # Empty, rejected or wrongly targeted reader output does not erase
            # its exact target/operation decision. Only literal source matches
            # transport the authored request; ambiguous associations stay empty.
            sources = [identity for identity, words in current.items()
                       if (item["request"] in words or words.strip() in item["request"])]
            if sources:
                scopes.append({
                    "authority_kind": (
                        "interpretation_review"
                        if item.get("material_purposes") == ["interpretation_review"]
                        else "account_contribution"
                    ),
                    "authority_source_ids": sources,
                    "target_scope": "exact",
                    "target_ids": list(requirement["target_ids"]),
                    "permitted_relations": [requirement["operation"]],
                })
        item["mutation_scopes"] = scopes
    return result



def scripted_record_result(operation, payload, data, disposition):
    """An owner-declared offline result; effects provide IDs, never meaning.

    Scenario owners explicitly select the disposition. The helper copies exact
    code-owned anchors for that scripted outcome and never decides whether a
    candidate, empty extraction or receipt fulfills a request.
    """
    if disposition is None or operation not in ("continue_conversation", "verify_continuation"):
        return data
    from copy import deepcopy

    result = deepcopy(data)
    status = disposition
    reason = {
        "performed": "The scripted independent judgment confirms the full requested record result.",
        "review_no_change": ("The scripted independent judgment confirms the unchanged record "
                             "meets the full review scope."),
        "unresolved": ("The scripted independent judgment leaves the requested record "
                       "result unfinished."),
    }[status]
    if operation == "continue_conversation":
        requests = {row["request_index"]: row for row in payload["work_items"]}
        for unit in result["units"]:
            request = requests[unit["request_index"]]
            requirement = request["record_requirement"]
            if (requirement["kind"] == "none"
                    and "none" in request.get("record_outcome_statuses", ["none"])):
                continue
            unit["record_outcome"] = {
                "status": status, "block_id": unit["blocks"][0]["id"],
                "effect_ids": [identity for identity, effect in
                               payload["record_effect_catalogue"].items()
                               if effect["performed"]] if status == "performed" else [],
                "current_record_ids": list(requirement["target_ids"])
                if status == "review_no_change" else [],
                "reason": reason,
            }
            if status == "unresolved":
                unit["sufficiency"]["status"] = "partial"
                unit["progress_updates"] = []
    else:
        requests = {row["request_index"]: row for row in payload["input"]["work_items"]}
        for row in result["verdicts"]:
            request = requests[row["request_index"]]
            if (request["record_requirement"]["kind"] == "none"
                    and "none" in request.get("record_outcome_statuses", ["none"])):
                continue
            row["record_check"] = {
                "outcome": {"performed": "fulfilled", "review_no_change": "no_change_justified",
                            "unresolved": "unfinished"}[status],
                "reason": reason,
            }
    return result

def _with_source_ids(row, payload):
    """Script citations from the immutable spans supplied to the model."""
    matching = [span["id"] for span in payload["latest_message_spans"]
                if row["quoted"] in span["text"]]
    converted = {key: value for key, value in row.items()
                 if key not in {"quoted", "prior_references"}}
    converted["source_id"] = matching[0] if matching else "unsupported_source"
    earlier = payload["earlier_conversation"]
    if earlier:
        converted["prior_source_ids"] = []
        for ref in row["prior_references"]:
            matching = [span["id"] for message in earlier
                        if message["turn_id"] == ref["turn_id"]
                        and message["role"] == ref["role"]
                        for span in message["source_spans"]
                        if ref["quoted"] in span["text"]]
            converted["prior_source_ids"].append(
                matching[0] if matching else "unsupported_prior_source")
    return converted


def material(kind, statement, quoted, *, relation="new", references=(),
             scope="proposed", basis="stated", importance="relevant",
             why="It may affect the requested legal work.",
             placement="unresolved", dispute_ids=(), related_material_ids=()):
    row = {"kind": kind, "statement": statement, "quoted": quoted,
           "relation": relation, "prior_references": list(references),
           "matter_scope": scope, "basis": basis,
           "importance": importance, "why_material": why}
    if kind == "dispute":
        row.update(label=statement[:80], identification="identified",
                   clarification="", related_dispute_ids=[])
    else:
        row.update(placement=placement, dispute_ids=list(dispute_ids),
                   related_material_ids=list(related_material_ids))
    return row


def plan(message, *, candidates=(), items=None, opening=False,
         active_work="review the account", material_purposes=(), record_requirement=None,
         record_disposition=None, mutation_scopes=None, response_expressions=None,
         source_purposes=None, dispute_scope=None, coverage_links=None):
    if items is None:
        items = [{"request": message, "relation": "new",
                  "matter_scope": "proposed" if opening else "current",
                  "priority": "ordinary",
                  "next_step": "legal_work",
                  "reply": ("I will check the account and available material "
                            "before reaching a legal view."),
                  "clarification": "",
                  "record_requirement": (no_record_requirement() if record_requirement is None
                                         else record_requirement)}]
    items = [{**item, "material_purposes": item.get(
        "material_purposes", list(material_purposes))} for item in items]
    if mutation_scopes is not None:
        assert len(items) == 1, "Author independent scopes on each item of a mixed plan"
        items[0]["mutation_scopes"] = list(mutation_scopes)
    return {"items": items, "material": list(candidates),
            **({"_dispute_scope": deepcopy(dispute_scope)}
               if dispute_scope is not None else {}),
            **({"_coverage_links": deepcopy(coverage_links)}
               if coverage_links is not None else {}),
            **({"_source_purposes": deepcopy(source_purposes)}
               if source_purposes is not None else {}),
            **({"_response_expressions": deepcopy(response_expressions)}
               if response_expressions is not None else {}),
            **({"_record_disposition": record_disposition}
               if record_disposition is not None else {}),
            "active_work_after": active_work,
            "opening": {"ready": opening,
                        "party_name": "",
                        "subject": "Contractor dispute" if opening else "",
                        "summary": "The advocate describes a dispute over stopped work."
                        if opening else "",
                        }}


def mutation_scope(*targets, relations=("corrects",), source_ids=("L1",),
                   authority_kind="account_contribution"):
    """Copy scenario-authored authority; no reader output is consulted."""
    return {"authority_kind": authority_kind, "authority_source_ids": list(source_ids),
            "target_scope": "exact", "target_ids": list(targets),
            "permitted_relations": list(relations)}


def send(client, message, turn_id, *, opened=None):
    body = {"message": message, "turn_id": turn_id}
    if opened is not None:
        body.update(matter_id=opened["matter_id"], chat_id=opened["chat_id"])
    return client.post("/api/turn", json=body)


def test_greeting_and_general_question_add_no_matter_material(
        client, wired, monkeypatch):
    greeting = "Hello"
    question = "What is the legal meaning of consideration?"
    model = Model([
        plan(greeting, candidates=[], items=[
            {"request": greeting, "relation": "new",
             "matter_scope": "none", "priority": "ordinary",
             "next_step": "answer",
             "reply": "Hello. What would you like help with?", "clarification": "",
             "record_requirement": no_record_requirement()}],
             active_work=""),
        plan(question, candidates=[], items=[
            {"request": question, "relation": "new",
             "matter_scope": "none", "priority": "ordinary",
             "next_step": "legal_work",
             "reply": "I will check the applicable law before explaining it.",
             "clarification": "",
             "record_requirement": no_record_requirement()}], active_work="answer legal question"),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    first = send(client, greeting, "greeting-turn").json()
    second = client.post("/api/turn", json={
        "message": question, "turn_id": "question-turn", "chat_id": first["chat_id"]})

    assert second.status_code == 200, second.text
    assert first["matter_id"] is None and second.json()["matter_id"] is None
    assert first["material"] == second.json()["material"] == []
    saved = wired.store.load(chat_matter_id("adv_demo", first["chat_id"]))
    assert [row["response"]["material"] for row in saved.brain_chat] == [[], []]
    assert saved.facts == ()
    assert len(model.calls) == 2
    assert model.material_calls == []


def test_first_account_retains_distinct_sourced_material_without_admission(
        client, wired, monkeypatch):
    message = ("The contractor stopped work on 12 June. "
               "We paid an advance of 4 lakh. They say materials were not supplied.")
    candidates = [
        material("event", "The contractor stopped work on 12 June.",
                 "contractor stopped work on 12 June", importance="central"),
        material("circumstance", "The advocate says an advance of 4 lakh was paid.",
                 "We paid an advance of 4 lakh", importance="central"),
        material("position", "The contractor says materials were not supplied.",
                 "They say materials were not supplied", basis="attributed"),
    ]
    model = Model([plan(message, candidates=candidates, opening=True,
                        material_purposes=("account_contribution",))])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    served = send(client, message, "material-first")

    assert served.status_code == 200, served.text
    response = served.json()
    assert [row["statement"] for row in response["material"]] == [
        row["statement"] for row in candidates]
    assert all(row["source_turn_id"] == "material-first" and row["id"]
               for row in response["material"])
    assert len({row["id"] for row in response["material"]}) == 3
    saved = wired.store.load(response["matter_id"])
    assert saved.brain_chat[0]["response"]["material"] == response["material"]
    assert saved.facts == ()
    assert len(model.calls) == 1
    assert len(model.material_calls) == 2
    assert response["metrics"]["llm_calls"] == 8
    payload = json.loads(model.calls[0].user)
    assert payload["earlier_conversation"] == []
    assert payload["latest_message"] == message
    assert all(label in model.calls[0].system for label in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))


def test_correction_and_diversion_keep_prior_words_and_proposals(
        client, wired, monkeypatch):
    first = "We paid the contractor an advance of 4 lakh."
    correction = "Correction: the advance was 3 lakh, not 4 lakh."
    aside = "Hi. What is the capital of France?"
    original = material("circumstance", "The advocate says 4 lakh was paid.",
                        "an advance of 4 lakh", importance="central")
    revised = material(
        "circumstance", "The advocate corrects the advance to 3 lakh.",
        "the advance was 3 lakh, not 4 lakh", relation="corrects",
        references=({"turn_id": "material-one", "role": "advocate",
                     "quoted": "an advance of 4 lakh"},),
        scope="current", importance="central")
    aside_item = {"request": aside, "relation": "aside",
                  "matter_scope": "none", "priority": "ordinary",
                  "next_step": "answer",
                  "reply": "Hello. Paris is the capital of France.",
                  "clarification": "", "record_requirement": no_record_requirement()}
    model = Model([
        plan(first, candidates=[original], opening=True,
             material_purposes=("account_contribution",)),
        plan(correction, candidates=[revised], material_purposes=("account_contribution",),
             mutation_scopes=[mutation_scope("material-one:material:1")],
             record_disposition="performed"),
        plan(aside, candidates=[], items=[aside_item]),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "material-one").json()
    corrected = send(client, correction, "material-two", opened=opened)
    diverted = send(client, aside, "material-three", opened=opened)

    assert corrected.status_code == 200, corrected.text
    assert diverted.status_code == 200, diverted.text
    assert corrected.json()["material"][0]["relation"] == "corrects"
    assert corrected.json()["material"][0]["prior_references"] == [
        {"turn_id": "material-one", "role": "advocate",
         "quoted": first}]
    assert diverted.json()["material"] == []
    saved = wired.store.load(opened["matter_id"])
    assert [row["message"] for row in saved.brain_chat] == [first, correction, aside]
    assert saved.brain_chat[0]["response"]["material"][0]["statement"] == original["statement"]
    assert saved.brain_chat[1]["response"]["material"][0]["statement"] == revised["statement"]
    assert saved.facts == ()
    assert len(model.calls) == 3
    assert len(model.material_calls) == 4
    assert [row["text"] for row in json.loads(model.calls[2].user)["earlier_conversation"]
            if row["role"] == "advocate"] == [first, correction]


def test_reported_correction_is_read_when_interpretation_marks_material_content(
        client, wired, monkeypatch):
    first = "The keys were handed over on Monday."
    correction = "Correction: the keys were handed over on Tuesday."
    original = material("event", "The keys were handed over on Monday.",
                        first)
    revised = material(
        "event", "The keys were handed over on Tuesday.", correction,
        relation="corrects", scope="current",
        references=({"turn_id": "first", "role": "advocate", "quoted": first},),
        related_material_ids=("first:material:1",))
    second_plan = plan(correction, candidates=[revised], items=[{
        "request": "Correct the handover date", "relation": "continues",
        "matter_scope": "current", "priority": "ordinary",
        "next_step": "legal_work", "reply": "I have noted the corrected date.",
        "intent": "contribution",
        "clarification": "",
        "record_requirement": no_record_requirement(),
        "mutation_scopes": [mutation_scope("first:material:1")]}],
                       material_purposes=("account_contribution",),
                       record_disposition="performed")
    second_plan["items"][0]["material_purposes"] = ["account_contribution"]
    model = Model([plan(first, candidates=[original], opening=True,
                        material_purposes=("account_contribution",)), second_plan])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "first")
    assert opened.status_code == 200, opened.text
    changed = send(client, correction, "second", opened=opened.json())

    assert changed.status_code == 200, changed.text
    assert changed.json()["metrics"]["llm_calls"] == 8
    matter = wired.store.load(opened.json()["matter_id"])
    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    record = material_record(matter, disputes=proposed_disputes(matter))
    assert [row["id"] for row in record["rows"]] == ["second:material:1"]
    assert len(record["history"]) == 2


@pytest.mark.parametrize("relation", ("new", "changes"))
def test_work_request_without_new_material_preserves_record_with_three_calls(
        client, wired, monkeypatch, relation):
    first = "The reported delivery date is disputed. We have an unsigned note."
    request = "Please assess the account already on this file."
    original = [
        material("dispute", "Disputed delivery date",
                 "The reported delivery date is disputed."),
        material("evidence", "The advocate reports an unsigned note.",
                 "We have an unsigned note.", placement="disputes",
                 dispute_ids=("recorded:material:1",)),
    ]
    work_plan = plan(request, items=[{
        "request": request, "relation": relation, "matter_scope": "current",
        "priority": "ordinary", "next_step": "legal_work",
        "reply": "I will assess the existing account and identify any limit in its support.",
        "clarification": "", "record_requirement": no_record_requirement()}])
    assert work_plan["items"][0]["material_purposes"] == []
    model = Model([plan(first, candidates=original, opening=True,
                        material_purposes=("account_contribution",),
                        dispute_scope={"The reported delivery date is disputed.": "account"}),
                   work_plan])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, first, "recorded")
    assert opened.status_code == 200, opened.text
    matter_id = opened.json()["matter_id"]
    before = client.get(f"/api/matters/{matter_id}").json()
    reader_count = len(model.material_calls)

    response = send(client, request, "work-request", opened=opened.json())

    assert response.status_code == 200, response.text
    released = response.json()
    assert released["metrics"]["llm_calls"] == 3
    assert [row["operation"] for row in released["metrics"]["model_calls"]] == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
    assert released["material"] == []
    assert len(model.material_calls) == reader_count
    after = client.get(f"/api/matters/{matter_id}").json()
    assert after["proposed_disputes"] == before["proposed_disputes"]
    assert after["material_record"] == before["material_record"]
    saved = wired.store.load(matter_id)
    assert [row["message"] for row in saved.brain_chat] == [first, request]
    assert saved.facts == ()


def test_public_authorised_formulation_review_reads_saved_account_without_new_facts(
        client, wired, monkeypatch):
    from copy import deepcopy

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record

    account = "Our packages are withheld in the depot by someone whose identity I do not know."
    request = ("Reconcile the board descriptions with my saved account and repair your wording "
               "without treating this review request as any new facts.")
    # Simulate an earlier accepted NM interpretation; the saved advocate words
    # never identified this actor. The review repairs that interpretation only.
    old_dispute = material("dispute", "Depot manager withheld packages", account,
                           basis="inferred")
    old_detail = material("event", "The depot manager withheld the packages.", account,
                          basis="inferred", placement="disputes",
                          dispute_ids=("original:material:1",))
    lineage = ({"turn_id": "original", "role": "advocate", "quoted": account},)
    dispute = material("dispute", "Packages withheld in depot; actor unidentified", request,
                       relation="corrects", references=lineage, scope="current")
    dispute["related_dispute_ids"] = ["original:material:1"]
    detail = material("event", "The advocate reports withheld packages; the actor is unidentified.",
                      request, relation="corrects", references=lineage, scope="current",
                      placement="disputes", dispute_ids=("review:material:1",),
                      related_material_ids=("original:material:2",))
    review_plan = plan(
        request, candidates=[dispute, detail], material_purposes=("interpretation_review",),
        record_requirement={
            "kind": "change", "target_ids": ["original:material:1", "original:material:2"],
            "operation": "corrects", "success_condition": (
                "The saved dispute and detail preserve the withheld packages and unknown actor "
                "from the original account without adding facts."),
        }, record_disposition="performed")
    model = Model([plan(account, candidates=[old_dispute, old_detail], opening=True,
                        material_purposes=("account_contribution",),
                        dispute_scope={account: "account"}), review_plan])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, account, "original").json()
    original_turn = deepcopy(wired.store.load(opened["matter_id"]).brain_chat[0])

    response = send(client, request, "review", opened=opened)
    assert response.status_code == 200, response.text
    result = response.json()
    replay = send(client, request, "review", opened=opened).json()

    assert result["metrics"]["llm_calls"] == 8
    assert [row["operation"] for row in result["metrics"]["model_calls"]] == [
        "interpret_conversation", "classify_account_sources", "extract_disputes", "verify_disputes",
        "extract_legal_details", "verify_material_grounding",
        "continue_conversation", "verify_continuation"]
    assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0
    saved = wired.store.load(opened["matter_id"])
    assert [row["message"] for row in saved.brain_chat] == [account, request]
    assert saved.brain_chat[0] == original_turn
    assert saved.facts == ()
    disputes = proposed_disputes(saved)
    records = material_record(saved, disputes=disputes)
    assert [row["id"] for row in disputes["rows"]] == ["review:material:1"]
    assert [row["id"] for row in records["rows"]] == ["review:material:2"]
    assert disputes["rows"][0]["related_dispute_ids"] == ["original:material:1"]
    assert records["rows"][0]["related_material_ids"] == ["original:material:2"]
    assert all(row["quoted"] == request and row["source_turn_id"] == "review"
               and row["prior_references"] == list(lineage) for row in result["material"])
    assert len(disputes["history"]) == len(records["history"]) == 2
    interpreter = model.calls[-1]
    assert "review can need original account reading without a new" in interpreter.system
    assert "instruction authorises examination but does not supply the fact" in interpreter.system
    assert review_plan["items"][0]["material_purposes"] == ["interpretation_review"]
    assert json.loads(interpreter.user)["latest_message"] == request
    assert [row["text"] for row in json.loads(interpreter.user)["earlier_conversation"]
            if row["role"] == "advocate"] == [account]


def test_authorised_formulation_review_may_leave_the_record_unchanged(
        client, wired, monkeypatch):
    account = "A party disputes the handover and the responsible actor is unknown."
    request = "Check whether your saved description faithfully reflects my account."
    original = material("dispute", "Disputed handover; actor unknown", account)
    review = plan(request, material_purposes=("interpretation_review",),
                  record_requirement={
                      "kind": "review", "target_ids": ["original-review-empty:material:1"],
                      "operation": "none", "success_condition": (
                          "The saved handover description preserves the reported dispute "
                          "and unknown actor."),
                  }, record_disposition="review_no_change",
                  source_purposes={request: "non_account"})
    model = Model([plan(account, candidates=[original], opening=True,
                        material_purposes=("account_contribution",),
                        dispute_scope={account: "account"}), review])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, account, "original-review-empty").json()
    matter_id = opened["matter_id"]
    before = client.get(f"/api/matters/{matter_id}").json()["proposed_disputes"]

    response = send(client, request, "review-empty", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["material"] == []
    assert result["metrics"]["llm_calls"] == 8
    assert [row["operation"] for row in result["metrics"]["model_calls"]] == [
        "interpret_conversation", "classify_account_sources", "extract_disputes", "verify_disputes",
        "extract_legal_details", "verify_material_grounding",
        "continue_conversation", "verify_continuation"]
    assert client.get(f"/api/matters/{matter_id}").json()["proposed_disputes"] == before


def test_answer_to_prior_nm_question_can_support_material(
        client, wired, monkeypatch):
    first = "The contractor may have stopped work on 12 June."
    question = "Did the stoppage occur on 12 June?"
    answer = "Yes."
    first_item = {"request": first, "relation": "new",
                  "matter_scope": "proposed", "priority": "ordinary",
                  "next_step": "clarify",
                  "reply": "", "clarification": question,
                  "record_requirement": no_record_requirement()}
    confirmed = material(
        "event", "The advocate confirms the stoppage occurred on 12 June.",
        "Yes", scope="current", importance="relevant",
        references=({"turn_id": "question-turn", "role": "nm",
                     "quoted": question},))
    model = Model([
        plan(first, opening=True, items=[first_item], material_purposes=("account_contribution",),
             response_expressions={0: {
                 "operator": "question", "source_ids": ["L1"],
                 "record_ids": [], "focus": "certainty",
             }}),
        # The confirmation represents the same tentative prior event. This
        # independent coverage choice does not add support or change authority
        # to D1's latest-message account check.
        plan(answer, candidates=[confirmed], material_purposes=("account_contribution",),
             coverage_links={first: {"record_ids": [], "candidate_ids": ["D1"]}}),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "question-turn").json()
    # Quote the actually released question as context. The independently
    # authored candidate/date is unchanged; display prose cannot supply it.
    question = next(block["text"] for unit in opened["continuation"]["units"]
                    for block in unit["blocks"] if block["kind"] == "question")
    assert "12 June" in question and first in question
    from nm.brain.conversation import Message
    from nm.brain.material import addressed_sources

    _, _, question_sources = addressed_sources(
        (Message("question-turn", "nm", question),), answer)
    contextual_references = [
        {"turn_id": ref.turn_id, "role": ref.role, "quoted": ref.quoted}
        for ref in question_sources.values()
    ]
    confirmed["prior_references"] = contextual_references
    served = send(client, answer, "answer-turn", opened=opened)

    assert served.status_code == 200, served.text
    assert served.json()["material"][0]["quoted"] == "Yes."
    assert served.json()["material"][0]["relation"] == "new"
    assert served.json()["material"][0]["related_material_ids"] == []
    assert served.json()["material"][0]["prior_references"] == contextual_references
    assert " ".join(ref["quoted"] for ref in contextual_references) == question
    assert wired.store.load(opened["matter_id"]).facts == ()
    assert len(model.calls) == 2
    assert len(model.material_calls) == 4


def test_one_message_keeps_separate_disputes_and_work_in_two_focused_calls(
        client, wired, monkeypatch):
    first = "The contractor stopped work"
    second = "my tenant has withheld rent"
    research = "find authorities on the contractor issue"
    message = f"{first}; separately, {second}. Also {research}."
    items = [
        {"request": research, "relation": "new",
         "matter_scope": "proposed", "priority": "ordinary",
         "next_step": "legal_work",
         "reply": "I will check the applicable authorities.",
         "clarification": "", "record_requirement": no_record_requirement()},
    ]
    candidates = [
        material("dispute", "The advocate describes a contractor work dispute.",
                 first, importance="central"),
        material("dispute", "The advocate describes a separate rent dispute.",
                 second, scope="other", importance="central"),
    ]
    model = Model([plan(message, candidates=candidates, opening=True,
                        items=items, material_purposes=("account_contribution",),
                        source_purposes={f"Also {research}.": "non_account",
                                         f"separately, {second}.": "outside_scope"},
                        dispute_scope={f"{first};": "account",
                                       f"separately, {second}.": "account"})])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    served = send(client, message, "multiple-material")

    assert served.status_code == 200, served.text
    assert [row["matter_scope"] for row in served.json()["material"]] == [
        "proposed", "other"]
    assert [row["quoted"] for row in served.json()["material"]] == [
        f"{first};", f"separately, {second}."]
    assert len(model.calls) == 1
    assert len(model.material_calls) == 2
    assert served.json()["metrics"]["llm_calls"] == 8


@pytest.mark.parametrize("invalid_candidate", [
    material("event", "A date was provided.", "words absent from the message",
             scope="current"),
    material("event", "The advocate corrects the date.", "the date was Tuesday",
             relation="corrects", scope="current",
             references=({"turn_id": "valid-first", "role": "advocate",
                          "quoted": "words absent from the earlier message"},)),
])
def test_unsupported_material_refuses_the_whole_turn_without_a_write(
        client, wired, monkeypatch, invalid_candidate):
    first = "The contractor stopped work on Monday."
    next_message = "The date was Tuesday, not Monday."
    if invalid_candidate["quoted"] == "the date was Tuesday":
        next_message = "Correction: the date was Tuesday, not Monday."
    model = Model([
        plan(first, opening=True, material_purposes=("account_contribution",)),
        plan(next_message, candidates=[invalid_candidate],
             material_purposes=("account_contribution",)),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "valid-first").json()
    refused = send(client, next_message, "invalid-second", opened=opened)

    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["committed"] == "not_committed"
    assert refused.json()["detail"]["why"] == (
        "NM could not validate the analysis returned by the AI service. "
        "Please try again later.")
    saved = wired.store.load(opened["matter_id"])
    assert [row["turn_id"] for row in saved.brain_chat] == ["valid-first"]
    assert saved.facts == ()
    assert len(model.calls) == 2
    assert len(model.material_calls) == 5
    retries = [json.loads(prompt.user) for prompt in model.material_calls
               if "original_input" in json.loads(prompt.user)]
    assert len(retries) == 1
    assert retries[0]["validation_issue"]
    failed = retries[0]["failed_units"][0]
    field = "new_items" if invalid_candidate["relation"] == "new" else "changes"
    assert failed["unit_id"] == f"{field}:1" and failed["field"] == field
    assert "source" in failed["validation_issue"].lower()
    assert failed["proposal"]["source_id"] == "unsupported_source" or (
        "unsupported_prior_source" in failed["proposal"].get("prior_source_ids", []))


def test_invalid_first_source_selection_is_repaired_once_before_commit(
        client, wired, monkeypatch):
    message = "The delivery was delayed."
    candidate = material("event", "The advocate reports a delayed delivery.",
                         "delivery was delayed")

    class RepairingModel(Model):
        def __init__(self):
            super().__init__([plan(message, candidates=[candidate], opening=True,
                                   material_purposes=("account_contribution",))])
            self.rejected = False

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier,
                                        max_tokens=max_tokens)
            if prompt.operation == "extract_legal_details" and not self.rejected:
                self.rejected = True
                row = {**result.data["new_items"][0],
                       "source_id": "unsupported_source"}
                return replace(result, data={"new_items": [row], "changes": []})
            return result

    model = RepairingModel()
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    served = send(client, message, "repaired-source")

    assert served.status_code == 200, served.text
    assert served.json()["material"][0]["quoted"] == message
    assert served.json()["metrics"]["llm_calls"] == 9
    repair = [json.loads(prompt.user) for prompt in model.material_calls
              if "original_input" in json.loads(prompt.user)]
    assert len(repair) == 1
    failed = repair[0]["failed_units"][0]
    assert failed["unit_id"] == "new_items:1" and failed["field"] == "new_items"
    assert "source_id" in failed["validation_issue"]
    assert failed["proposal"]["source_id"] == "unsupported_source"
    assert repair[0]["original_input"]["latest_message_spans"][0]["text"] == message
    saved = wired.store.load(served.json()["matter_id"])
    assert [row["turn_id"] for row in saved.brain_chat] == ["repaired-source"]
