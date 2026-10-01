"""A closed list built from real words must never make the provider refuse the call.

Strict structured output refuses a double quotation mark inside an enum value. On
the Farah Begum turn (30 September 2026) the step-dependency read put the step's
own words -- which quoted a provision -- into its schema, and the call could not
run at all. Two more reads build lists from text: the posture read's correction
sentences (an advocate's sentence quoting a letter) and the checklist read's
passage names.

THE RULES:
1. `on_the_wire` sends such a list open -- one boundary, every schema -- so the
   provider can produce an answer at all.
2. The local adapter validates the original closed schema after the call, and
   the read's own source check retains the same boundary.
3. Lists without the mark are sent closed, exactly as before.
"""
from __future__ import annotations

import json

import pytest

from nm.Archives.legal_brain.common.quotable_contracts import Quotable
from nm.Archives.legal_brain.understand import posture
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Prompt, SchemaViolation, Tier, on_the_wire, require_schema
from tests.test_model_port_contract import _FakeOpenAI, _config

pytestmark = pytest.mark.class_a

QUOTING = 'We act for A. The landlord wrote "vacate by Friday". Our opponent is B, not C.'


def test_a_list_holding_a_quotation_mark_goes_open_and_others_stay_closed():
    schema = posture.schema_for(Quotable(turn=QUOTING))
    closed = schema["properties"]["opponent_correction_quote"]["enum"]
    assert any('"' in v for v in closed), "this control needs a quoted sentence"
    wire = on_the_wire(schema)
    assert "enum" not in wire["properties"]["opponent_correction_quote"]
    assert wire["properties"]["role"]["enum"] == schema["properties"]["role"]["enum"]
    plain = posture.schema_for(Quotable(turn="We act for A. Our opponent is B, not C."))
    assert on_the_wire(plain)["properties"]["opponent_correction_quote"]["enum"] == \
        plain["properties"]["opponent_correction_quote"]["enum"]


def test_the_read_still_refuses_a_value_outside_the_list():
    answer = dict(states_client=True, role="prospective_claimant", role_basis="stated",
                  client_described_as="A", opponent="B", quoted="We act for A.",
                  role_quote="", opponent_correction_quote="Our opponent is really B.")
    schema = posture.schema_for(Quotable(turn=QUOTING))
    require_schema(answer, on_the_wire(schema))
    with pytest.raises(SchemaViolation):
        require_schema(answer, schema)
    read = posture.interpret(Quotable(turn=QUOTING), answer)
    assert read.opponent_correction_quote == "", "a correction nobody wrote was taken"
    kept = posture.interpret(Quotable(turn=QUOTING), {
        **answer, "opponent_correction_quote": "Our opponent is B, not C."})
    assert kept.opponent_correction_quote == "Our opponent is B, not C."

    client = _FakeOpenAI(json.dumps(answer))
    adapter = OpenAIModelAdapter(_config(), client=client)
    with pytest.raises(SchemaViolation):
        adapter.structured(Prompt(user=QUOTING), schema, Tier.ROUTINE)
    sent = client.calls[0]["response_format"]["json_schema"]["schema"]
    assert "enum" not in sent["properties"]["opponent_correction_quote"]
