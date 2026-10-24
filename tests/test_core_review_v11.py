"""Review v11 (owner decisions P41 and P43, 24 Oct 2026; plan AN.6 piece 4): the review of a
section written for the advocate and placed (writer v13) also says what could go, and names any
paragraph folded under "More on this" that the advice depends on, which code then shows."""
import json

import pytest

from nm.core_engine import response_authorities, response_review, response_writer, turn
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.test_core_response_writer import two_disputes

pytestmark = pytest.mark.class_a

LIMITS = {"worked_out": [{"what": "File the complaint"}], "not_assessed": []}


def unit(kind, text, place):
    return {"kind": kind, "text": text, "uses": [], "place": place}


def piece(contract=response_writer.PRESENTED_CONTRACT):
    """A v13 section of the two-dispute matter: its row, its advice, one paragraph folded."""
    ctx, record, sources = two_disputes()
    units = [unit("summary", "Criminal complaint under section 138", "row_action"),
             unit("summary", "File by Wednesday.", "advice"),
             unit("summary", "Proof can be given by affidavit.", "more")]
    if contract == response_writer.SECTION_CONTRACT:
        units = [{key: value for key, value in item.items() if key != "place"} for item in units]
    part = {"checklist": [], "time_limit_ids": [],
            **({"by_when": None} if contract == response_writer.PRESENTED_CONTRACT else {})}
    draft = response_writer.accept({"units": units, "checklists": [part]}, ctx, sources, contract=contract,
                                   parts=[{"dispute_id": "D1", "units": 3}], section=1)
    return ctx, record, sources, draft, response_authorities.check(ctx, record, sources, draft)


def admitted(returned):
    ctx, record, sources, draft, authorities = piece()
    deps = response_review._dependencies(ctx, record, sources, draft, turn.execution_record(record),
                                         authority_evidence=authorities, time_limits=LIMITS,
                                         contract=response_review.PRESENTED_CONTRACT)
    return response_review._accept_v10(returned, deps, response_review.PRESENTED_CONTRACT), draft


def test_what_could_go_is_its_own_kind_of_suggestion_and_asks_for_no_removal():
    record, draft = admitted({"misleading": [], "keep_shown": [], "could_be_better": [
        {"where": ["U2"], "what": "Say which court hears it.", "change": "add_or_put_better"},
        {"where": ["U3"], "what": "The affidavit point repeats the next section.", "change": "could_go"}]})
    assert record["contract"] == "core_response_review_v11"
    assert [(finding["category"], finding["unit_ids"]) for finding in record["proposal"]["findings"]] == [
        ("better", [draft["units"][1]["id"]]), ("could_go", [draft["units"][2]["id"]])]
    assert set(response_review.SUGGESTIONS) == {"better", "could_go"}
    assert record["proposal"]["keep_shown"] == []


def test_a_folded_paragraph_the_advice_depends_on_is_kept_shown_and_no_other_is():
    record, draft = admitted({"misleading": [], "could_be_better": [], "keep_shown": ["U3", "U2", "U3"]})
    assert record["proposal"]["keep_shown"] == [draft["units"][2]["id"]]
    assert record["accepted"] is True  # keeping a fold shown asks nothing of the writer
    assert [entry["why"] for entry in record["proposal"]["set_aside"]] == [
        "not a paragraph placed under More on this: U2"]


def test_a_v11_review_replays_from_its_own_output():
    ctx, record, sources, draft, authorities = piece()

    class Reviewer:
        def context_budget(self, tier): return 100_000

        def structured(self, prompt, schema, tier, **kwargs):
            self.prompt, self.schema, self.payload = prompt, schema, json.loads(prompt.user)
            return ModelResult(None, {"misleading": [], "keep_shown": ["U3"], "could_be_better": [
                {"where": ["U3"], "what": "Could go.", "change": "could_go"}]}, tier, "synthetic", "fixture",
                Usage(1, 1, 0), 0, completion=Completion.COMPLETE)
    model = Reviewer()
    review = response_review.review(model, ctx, record, sources, draft, turn.execution_record(record),
                                    authority_evidence=authorities, time_limits=LIMITS,
                                    contract=response_review.PRESENTED_CONTRACT)
    assert model.prompt.system == response_review.SYSTEM_V11 and model.schema == response_review.SCHEMA_V11
    # The review sees each paragraph's place and the time limit that answers by when.
    shown = model.payload["complete_draft_proposal"]
    assert [unit["place"] for unit in shown["units"]] == ["row_action", "advice", "more"]
    assert shown["checklists"][0]["by_when"] is None
    assert response_review.validate(review, ctx, record, sources, draft, turn.execution_record(record),
                                    authority_evidence=authorities, time_limits=LIMITS) == review


def test_a_v13_piece_is_reviewed_by_v11_and_a_v12_piece_never_is():
    for contract, review in ((response_writer.PRESENTED_CONTRACT, response_review.MISLEADS_CONTRACT),
                             (response_writer.SECTION_CONTRACT, response_review.PRESENTED_CONTRACT)):
        ctx, record, sources, draft, authorities = piece(contract)
        with pytest.raises(ValueError, match="Review version"):
            response_review._dependencies(ctx, record, sources, draft, turn.execution_record(record),
                                          authority_evidence=authorities, contract=review)


def test_the_overview_and_the_cross_check_see_a_v13_section_s_row_and_places():
    ctx, record, sources, draft, _ = piece()
    shown, = response_review.shown_sections([draft], record)
    assert shown["row"] == {"what_to_do": "Criminal complaint under section 138", "have_ready": None,
                            "by_when": None}
    assert [paragraph["place"] for paragraph in shown["paragraphs"]] == ["row_action", "advice", "more"]
