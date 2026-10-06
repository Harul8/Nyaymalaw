"""Review sees rendered content and cannot bless an altered expression."""
from copy import deepcopy

import pytest

from nm.brain.continuation_verification import verify_continuation
from nm.brain.evidence_rendering import rendered_block
from nm.shared.model_port import SchemaViolation
from tests.test_brain_continuation import ContinuationModel, unit, verdict

pytestmark = pytest.mark.class_a


def fixture():
    source = {"id": "L1", "text": "I did not confirm that date.", "role": "advocate"}
    payload = {"latest_message_spans": [{"id": "L1", "text": source["text"]}],
               "earlier_conversation": [], "record_catalogue": {}, "legal_sources": {},
               "progress": {"state": "ok", "rows": []}}
    proposed = unit()
    proposed["blocks"] = [rendered_block({
        "id": "account-0", "kind": "account", "uncertainty": "reported",
        "evidence_expression": {"operator": "source_account", "source_ids": ["L1"],
                                "record_ids": [], "focus": "none"}},
        spans={"L1": source}, records={}, sources={})]
    proposed["questions"] = []
    proposed["sufficiency"]["block_id"] = "account-0"
    return payload, proposed


@pytest.mark.parametrize("fault", ["text", "source", "version", "extra_literal"])
def test_wrong_accepting_judge_is_never_called_for_altered_rendering(fault):
    payload, proposed = fixture()
    block = proposed["blocks"][0]
    if fault == "text":
        block["text"] = "The date was confirmed and saved."
    elif fault == "source":
        block["evidence_expression"]["source_ids"] = ["foreign"]
    elif fault == "version":
        block["expression_contract"] = "unknown"
    else:
        block["evidence_expression"]["text"] = "The date was saved."
    model = ContinuationModel([verdict(0)])
    with pytest.raises(SchemaViolation):
        verify_continuation(model, input_payload=payload, units=(proposed,))
    assert model.calls == []


def test_independent_review_judges_original_selection_without_an_extra_stage():
    payload, proposed = fixture()
    original = deepcopy(proposed)
    model = ContinuationModel([verdict(0)])
    result = verify_continuation(model, input_payload=payload, units=(proposed,))
    assert result.decisions[0][0]
    assert len(model.calls) == 1
    assert proposed == original
    assert "not their adoption as fact" in model.calls[0][0].system


def test_owned_passage_boundary_whitespace_does_not_reject_correct_rendering():
    payload, proposed = fixture()
    payload["latest_message_spans"][0]["text"] = "  I did not confirm that date.\n"
    result = verify_continuation(ContinuationModel([verdict(0)]),
                                 input_payload=payload, units=(proposed,))
    assert result.decisions[0][0]
