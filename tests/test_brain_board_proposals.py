"""The served board reads dispute proposals without admitting them as threads."""
import json
from dataclasses import replace

from nm.brain.conversation import Message
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, Usage
from nm.work_the_file.matter_contracts import Matter
from nm.work_the_file.projections_api import _proposed_disputes
from tests.brain_continuation_fixture import continuation_reply, interpretation
from tests.brain_reader_fixture import reader_operations, reviewed_record_verdicts


class ScriptedBrain:
    def __init__(self, answers):
        self.routes = iter(answers[::2])
        self.disputes = {route["items"][0]["request"]: material["disputes"]
                         for route, material in zip(answers[::2], answers[1::2], strict=True)}
        self.calls = []
        self.current_items = []

    def context_budget(self, tier):
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return 20000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.calls.append(payload)
        continuation = continuation_reply(prompt.operation, payload,
                                          scripted_items=self.current_items)
        if continuation is not None:
            answer = continuation
        elif prompt.operation == "interpret_conversation":
            answer = interpretation(next(self.routes))
            self.current_items = answer["items"]
        elif prompt.operation == "extract_legal_details":
            answer = {"new_items": [], "changes": []}
        elif prompt.operation in ("verify_disputes", "verify_material_grounding"):
            answer = {"verdicts": [{
                "candidate_id": row["candidate_id"], "verdict": "accept",
                "operation_supported": True,
                "reason": "The scripted proposal is attributable.",
                **({"candidate_role": "independent_dispute"}
                   if prompt.operation == "verify_disputes" else {}),
            } for row in payload["candidates"]]}
        else:
            sources = payload.get("original_input", payload)
            latest = "".join(span["text"] for span in
                             sources["latest_message_spans"])
            rows = [_with_source_ids(row, sources)
                    for row in self.disputes[latest]]
            answer = reader_operations(rows, sources,
                                       link_field="related_dispute_ids")
        if prompt.operation in ("verify_disputes", "verify_material_grounding"):
            answer = reviewed_record_verdicts(payload, answer)
        return ModelResult(text=None, data=answer, tier=tier,
                           provider="offline", model="offline", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=Completion.COMPLETE)


def _with_source_ids(row, payload):
    """Choose IDs from the supplied transcript, as the reader now must."""
    current = payload["latest_message_spans"]
    latest_id = next(span["id"] for span in current
                     if row["quoted"] in span["text"])
    converted = {key: value for key, value in row.items()
                 if key not in {"kind", "quoted", "prior_references"}}
    converted["source_id"] = latest_id
    if payload["earlier_conversation"]:
        converted["prior_source_ids"] = [
            next(span["id"] for message in payload["earlier_conversation"]
                 if message["turn_id"] == ref["turn_id"]
                 and message["role"] == ref["role"]
                 for span in message["source_spans"]
                 if ref["quoted"] in span["text"])
            for ref in row["prior_references"]]
    return converted


def route(request, *, relation, scope, opening=False):
    return {
        "items": [{"request": request, "relation": relation,
                   "matter_scope": scope, "priority": "ordinary",
                   "next_step": "legal_work",
                   "reply": "I will assess the issues against the available record.",
                   "clarification": ""}],
        "active_work_after": request,
        "opening": {"ready": opening,
                    "party_name": "",
                    "subject": "Supply dispute" if opening else "",
                    "summary": "The client reports disputes concerning the supply relationship."
                    if opening else ""},
        "material_review": True,
    }


def dispute(statement, quoted, *, relation="new", scope="proposed", prior=(),
            related=(), identification="identified"):
    return {"kind": "dispute", "statement": statement, "quoted": quoted,
            "relation": relation, "prior_references": list(prior),
            "matter_scope": scope, "basis": "stated", "importance": "central",
            "why_material": "This contested issue needs its own practical conclusion.",
            "label": statement, "identification": identification,
            "clarification": "What fact would distinguish the issue?"
            if identification == "needs_clarification" else "",
            "related_dispute_ids": list(related)}


def saved_turn(turn_id, message, material, matter_id="mat_links"):
    response = {"turn_id": turn_id, "elements": [{"text": "Recorded."}],
                "material": material}
    return {"turn_id": turn_id, "matter_id": matter_id,
            "advocate_id": "adv", "message": message, "response": response,
            "elements": response["elements"], "committed": True,
            "release_state": "released"}


def test_board_can_validate_a_correction_against_authorised_older_words():
    earlier = Message("legacy-turn", "advocate", "The supplier refused a refund.")
    response = {"turn_id": "new-turn", "elements": [{"text": "Recorded provisionally."}],
                "material": [{
                    "id": "new-turn:material:1", "source_turn_id": "new-turn",
                    "state": "proposed", "kind": "dispute", "relation": "corrects",
                    "matter_scope": "current", "statement": "The refusal is disputed.",
                    "quoted": "The supplier has not answered.",
                    "prior_references": [{"turn_id": "legacy-turn", "role": "advocate",
                                          "quoted": "The supplier refused a refund."}],
                }]}
    matter = Matter(
        id="mat_legacy", advocate_id="adv", title="Supply matter",
        brain_ready=True, brain_chat=({
            "turn_id": "new-turn", "matter_id": "mat_legacy",
            "advocate_id": "adv", "message": "The supplier has not answered.",
            "response": response, "elements": response["elements"],
            "committed": True, "release_state": "released",
        },))

    assert _proposed_disputes(matter)["state"] == "incomplete"
    result = _proposed_disputes(matter, prior_conversation=(earlier,))
    assert result["state"] == "ok"
    assert result["rows"][0]["prior_references"][0]["turn_id"] == "legacy-turn"
    assert result["rows"][0]["identification"] == "unassessed"
    assert result["rows"][0]["related_dispute_ids"] == []

    explicit = {**response["material"][0], "identification": "unassessed"}
    invalid_response = {**response, "material": [explicit]}
    invalid_turn = {**matter.brain_chat[0], "response": invalid_response}
    invalid = replace(matter, brain_chat=(invalid_turn,))
    assert _proposed_disputes(
        invalid, prior_conversation=(earlier,))["state"] == "incomplete"


def test_legacy_label_uses_the_short_saved_source_instead_of_a_long_question():
    source = "The invoice amount is disputed."
    statement = ("Whether the invoice amount is payable after considering the "
                 "parties' differing accounts of the work, the agreed price, "
                 "the credits claimed, and the timing of each payment?")
    legacy_fields = {"label", "identification", "clarification",
                     "related_dispute_ids"}
    row = {key: value for key, value in dispute(statement, source).items()
           if key not in legacy_fields}
    row.update(id="first:material:1", source_turn_id="first", state="proposed")
    matter = Matter(id="mat_links", advocate_id="adv", title="Conversation",
                    brain_ready=True,
                    brain_chat=(saved_turn("first", source, [row]),))

    result = _proposed_disputes(matter)
    assert result["state"] == "ok"
    assert len(statement) > 120
    assert result["rows"][0]["label"] == source
    assert result["rows"][0]["identification"] == "unassessed"


def test_board_exposes_sourced_proposals_separately_from_worked_threads(
        client, wired, monkeypatch):
    first = ("Our client contests the termination. "
             "A separate unpaid invoice is also contested.")
    second = ("Correction: the invoice has been paid; the termination notice was "
              "never sent. A different client's lease is also contested.")
    prior_invoice = {"turn_id": "turn-opening", "role": "advocate",
                     "quoted": "A separate unpaid invoice is also contested."}
    prior_termination = {"turn_id": "turn-opening", "role": "advocate",
                         "quoted": "Our client contests the termination."}
    model = ScriptedBrain([
        route(first, relation="new", scope="proposed", opening=True),
        {"disputes": [
            dispute("The client contests the termination.",
                    "contests the termination"),
            dispute("The client contests a separate unpaid invoice.",
                    "A separate unpaid invoice"),
        ], "details": []},
        route(second, relation="changes", scope="current"),
        {"disputes": [
            dispute("The earlier invoice dispute is withdrawn after payment.",
                    "the invoice has been paid", relation="withdraws",
                    scope="current", prior=[prior_invoice],
                    related=["turn-opening:material:2"]),
            dispute("The termination account is corrected to report no notice.",
                    "the termination notice was never sent", relation="corrects",
                    scope="current", prior=[prior_termination],
                    related=["turn-opening:material:1"]),
            dispute("Another client's lease is contested.",
                    "A different client's lease is also contested",
                    scope="other"),
        ], "details": []},
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = client.post("/api/turn", json={"message": first,
                                            "turn_id": "turn-opening"})
    assert opened.status_code == 200, opened.text
    matter_id = opened.json()["matter_id"]
    continued = client.post("/api/turn", json={"message": second,
                                               "turn_id": "turn-correction",
                                               "matter_id": matter_id,
                                               "chat_id": opened.json()["chat_id"]})
    assert continued.status_code == 200, continued.text

    response = client.get(f"/api/matters/{matter_id}")
    assert response.status_code == 200, response.text
    board = response.json()
    assert board["agenda"]["disputes"] == []
    assert board["threads"] == []
    assert board["row_count"] == 0
    proposals = board["proposed_disputes"]
    assert proposals["state"] == "ok"
    assert [row["relation"] for row in proposals["rows"]] == ["corrects"]
    assert [row["relation"] for row in proposals["history"]] == [
        "new", "new", "withdraws", "corrects"]
    assert proposals["history"][2]["prior_references"] == [prior_invoice]
    assert proposals["history"][3]["prior_references"] == [prior_termination]
    assert proposals["rows"][0]["identification"] == "identified"
    assert all(row["state"] == "proposed" for row in proposals["rows"])
    assert all(row["source_turn_id"] in ("turn-opening", "turn-correction")
               for row in proposals["rows"])
    assert len(model.calls) == 15  # One source-treatment read for each material turn.

    # If the saved words no longer support a proposal, the board reports an
    # incomplete read rather than presenting a shorter list as complete.
    matter = wired.store.load(matter_id)
    damaged = dict(matter.brain_chat[0])
    answer = dict(damaged["response"])
    material = [dict(row) for row in answer["material"]]
    material[0]["quoted"] = "words absent from the saved message"
    answer["material"] = material
    damaged["response"] = answer
    altered = replace(matter, brain_chat=(damaged, *matter.brain_chat[1:]),
                      version=matter.version + 1)
    wired.store.commit(altered, expected_version=matter.version)
    reread = client.get(f"/api/matters/{matter_id}")
    assert reread.status_code == 200, reread.text
    assert reread.json()["proposed_disputes"]["state"] == "incomplete"
    assert reread.json()["proposed_disputes"]["problems"]

    # A withheld response never contributes board proposals, even if its
    # response object still contains a previously generated proposal.
    unreleased = dict(matter.brain_chat[1])
    unreleased["release_state"] = "withheld"
    altered_again = replace(matter, brain_chat=(matter.brain_chat[0], unreleased),
                            version=altered.version + 1)
    wired.store.commit(altered_again, expected_version=altered.version)
    withheld_board = client.get(f"/api/matters/{matter_id}")
    assert withheld_board.status_code == 200, withheld_board.text
    projected = withheld_board.json()["proposed_disputes"]
    assert projected["state"] == "incomplete"
    assert [row["source_turn_id"] for row in projected["rows"]] == [
        "turn-opening", "turn-opening"]


def test_wrong_related_issue_cannot_retire_another_dispute_from_the_same_turn():
    first_message = "The delivery is disputed. The fee is disputed."
    first_material = [
        {**dispute("Delivery", "The delivery is disputed."),
         "id": "first:material:1", "source_turn_id": "first", "state": "proposed"},
        {**dispute("Fee", "The fee is disputed."),
         "id": "first:material:2", "source_turn_id": "first", "state": "proposed"},
    ]
    second_message = "Correction: delivery happened."
    second_material = [{
        **dispute("Delivery is resolved", second_message, relation="corrects",
                  scope="current", related=["first:material:2"], prior=[{
                      "turn_id": "first", "role": "advocate",
                      "quoted": "The delivery is disputed."}]),
        "id": "second:material:1", "source_turn_id": "second",
        "state": "proposed",
    }]

    matter = Matter(id="mat_links", advocate_id="adv", title="Two issues",
                    brain_ready=True, brain_chat=(
                        saved_turn("first", first_message, first_material),
                        saved_turn("second", second_message, second_material)))
    result = _proposed_disputes(matter)
    assert result["state"] == "incomplete"
    assert [row["id"] for row in result["rows"]] == [
        "first:material:1", "first:material:2"]
    assert [row["id"] for row in result["history"]] == [
        "first:material:1", "first:material:2"]


def test_uncertain_matter_scope_stays_in_source_turn_until_assigned():
    message = "The delivery is contested, but this may concern another file."
    row = {**dispute("Delivery dispute", message, scope="uncertain"),
           "id": "first:material:1", "source_turn_id": "first",
           "state": "proposed"}
    matter = Matter(id="mat_links", advocate_id="adv", title="Conversation",
                    brain_ready=True,
                    brain_chat=(saved_turn("first", message, [row]),))

    result = _proposed_disputes(matter)
    assert result["state"] == "ok"
    assert result["rows"] == []
    assert result["history"] == []
    assert matter.brain_chat[0]["response"]["material"][0]["matter_scope"] == "uncertain"
    assert matter.brain_chat[0]["response"]["material"][0]["identification"] == "identified"


def test_pre_opening_chat_proposals_belong_to_the_opened_matter():
    messages = (
        "The delivery is contested.",
        "The invoice is also contested.",
        "The acceptance date is contested.",
        "A different client's lease is contested.",
    )
    routes = ("non_matter", "non_matter", "matter", "matter")
    turns = []
    for index, (message, route_name) in enumerate(zip(messages, routes, strict=True)):
        turn_id = f"turn-{index + 1}"
        row = {**dispute(f"Dispute {index + 1}", message),
               "id": f"{turn_id}:material:1", "source_turn_id": turn_id,
               "state": "proposed"}
        saved = saved_turn(turn_id, message, [row])
        saved["response"]["route"] = route_name
        turns.append(saved)
    matter = Matter(id="mat_links", advocate_id="adv", title="Conversation",
                    brain_ready=True, brain_chat=tuple(turns))

    result = _proposed_disputes(matter)
    assert result["state"] == "ok"
    assert [row["id"] for row in result["rows"]] == [
        "turn-1:material:1", "turn-2:material:1", "turn-3:material:1"]
    assert [row["id"] for row in result["history"]] == [
        "turn-1:material:1", "turn-2:material:1", "turn-3:material:1"]
    assert matter.brain_chat[3]["response"]["material"][0]["id"] == (
        "turn-4:material:1")


def test_unlinked_dispute_withdrawal_marks_projection_incomplete():
    first_message = "The delivery is disputed."
    first = {**dispute("Delivery dispute", first_message),
             "id": "first:material:1", "source_turn_id": "first",
             "state": "proposed"}
    second_message = "I withdraw that delivery dispute."
    withdrawal = {**dispute("Delivery dispute withdrawn", second_message,
                            relation="withdraws", scope="current", prior=[{
                                "turn_id": "first", "role": "advocate",
                                "quoted": first_message}]),
                  "id": "second:material:1", "source_turn_id": "second",
                  "state": "proposed"}
    matter = Matter(id="mat_links", advocate_id="adv", title="Conversation",
                    brain_ready=True, brain_chat=(
                        saved_turn("first", first_message, [first]),
                        saved_turn("second", second_message, [withdrawal])))

    result = _proposed_disputes(matter)
    assert result["state"] == "incomplete"
    assert [row["id"] for row in result["rows"]] == ["first:material:1"]
    assert result["problems"]
    assert matter.brain_chat[1]["response"]["material"][0]["relation"] == "withdraws"


def test_unlinked_correction_preserves_identification_and_prior_active_issue():
    first_message = "The delivery is disputed."
    first = {**dispute("Delivery dispute", first_message),
             "id": "first:material:1", "source_turn_id": "first",
             "state": "proposed"}
    second_message = "Correction: delivery took place later."
    second = {**dispute("Delivery timing dispute", second_message,
                        relation="corrects", scope="current", prior=[{
                            "turn_id": "first", "role": "advocate",
                            "quoted": first_message}]),
              "id": "second:material:1", "source_turn_id": "second",
              "state": "proposed"}
    matter = Matter(id="mat_links", advocate_id="adv", title="Conversation",
                    brain_ready=True, brain_chat=(
                        saved_turn("first", first_message, [first]),
                        saved_turn("second", second_message, [second])))

    result = _proposed_disputes(matter)
    assert result["state"] == "ok"
    assert [row["id"] for row in result["rows"]] == [
        "first:material:1", "second:material:1"]
    assert result["rows"][1]["identification"] == "identified"


def test_clarification_replaces_only_the_linked_uncertain_dispute(
        client, wired, monkeypatch):
    first = "We dispute the invoice, but cannot tell which of our two orders it concerns."
    second = "It concerns the later order only."
    clarification = "Which order does the disputed invoice concern?"
    opening = route(first, relation="new", scope="proposed", opening=True)
    opening["items"][0].update(next_step="clarify", reply="",
                               clarification=clarification)
    opening["opening"].update(subject="Invoice dispute",
                              summary="The client disputes an invoice for an order.")
    model = ScriptedBrain([
        opening,
        {"disputes": [dispute("Invoice dispute", first,
                              identification="needs_clarification")]},
        route(second, relation="continues", scope="current"),
        {"disputes": [dispute(
            "Later order invoice dispute", second, relation="adds",
            scope="current", related=["turn-uncertain:material:1"], prior=[{
                "turn_id": "turn-uncertain", "role": "advocate",
                "quoted": first}])]},
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = client.post("/api/turn", json={"message": first,
                                            "turn_id": "turn-uncertain"})
    assert opened.status_code == 200, opened.text
    assert opened.json()["metrics"]["llm_calls"] == 8
    assert clarification in opened.json()["elements"][0]["text"]
    matter_id = opened.json()["matter_id"]
    initial_board = client.get(f"/api/matters/{matter_id}").json()
    assert initial_board["proposed_disputes"]["rows"][0][
        "identification"] == "needs_clarification"

    continued = client.post("/api/turn", json={"message": second,
                                               "turn_id": "turn-clarified",
                                               "matter_id": matter_id,
                                               "chat_id": opened.json()["chat_id"]})
    assert continued.status_code == 200, continued.text
    assert continued.json()["metrics"]["llm_calls"] == 7
    routing = [payload for payload in model.calls if "latest_message" in payload]
    assert len(routing) == 2
    assert routing[1]["open_disputes"] == [{
        "id": "turn-uncertain:material:1", "label": "Invoice dispute",
        "statement": "Invoice dispute", "identification": "needs_clarification",
        "clarification": "What fact would distinguish the issue?"}]
    board = client.get(f"/api/matters/{matter_id}").json()["proposed_disputes"]
    assert board["state"] == "ok"
    assert [row["id"] for row in board["rows"]] == [
        "turn-clarified:material:1"]
    assert board["rows"][0]["identification"] == "identified"
    assert [row["id"] for row in board["history"]] == [
        "turn-uncertain:material:1", "turn-clarified:material:1"]


def test_same_turn_split_shares_prior_link_and_invalid_sibling_cannot_retire_it():
    first_message = "The deal is disputed."
    first = {**dispute("Deal dispute", first_message),
             "id": "first:material:1", "source_turn_id": "first",
             "state": "proposed"}
    second_message = "Delivery and payment are separate disputes."
    prior = [{"turn_id": "first", "role": "advocate",
              "quoted": first_message}]
    replacements = [{
        **dispute(label, second_message, relation="corrects", scope="current",
                  prior=prior, related=["first:material:1"]),
        "id": f"second:material:{index}", "source_turn_id": "second",
        "state": "proposed",
    } for index, label in enumerate(("Delivery dispute", "Payment dispute"), 1)]

    def matter(rows):
        return Matter(id="mat_links", advocate_id="adv", title="Two issues",
                      brain_ready=True, brain_chat=(
                          saved_turn("first", first_message, [first]),
                          saved_turn("second", second_message, rows)))

    split = _proposed_disputes(matter(replacements))
    assert split["state"] == "ok"
    assert [row["id"] for row in split["rows"]] == [
        "second:material:1", "second:material:2"]
    assert len(split["history"]) == 3

    invalid = {**replacements[1], "related_dispute_ids": ["missing"]}
    incomplete = _proposed_disputes(matter([replacements[0], invalid]))
    assert incomplete["state"] == "incomplete"
    assert [row["id"] for row in incomplete["rows"]] == [
        "first:material:1"]
