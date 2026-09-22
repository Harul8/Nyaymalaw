"""DG-11: live party-read disclosures must not crash a valid answer."""

import json
from types import SimpleNamespace

import pytest
from nm.adapters.model.scripted import SCRIPTED_READS
from nm.core.turn import _with_screens
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("kind", [ElementKind.ACTION, ElementKind.QUESTION])
@pytest.mark.parametrize("prefix_count", [0, 1, 3])
def test_real_operative_element_leads_without_erasing_or_retyping_support(kind, prefix_count):
    prefix = [
        Element(kind=ElementKind.GROUND, text=f"Unresolved evidence {i}", disclosure=True)
        for i in range(prefix_count)
    ]
    lead = Element(
        kind=kind,
        text="Obtain the original record",
        no_deadline_reason="No dated step is established",
    )
    rest = Element(kind=ElementKind.GROUND, text="Retrieved support")
    incoming = [*prefix, lead, rest]
    original = list(incoming)
    assembled = _with_screens(incoming, SimpleNamespace(rows=()))
    answer = Answer(
        route=Route.MATTER, mode=Mode.FULL_BRIEF, mode_statement="Assessment", elements=assembled
    )
    assert answer.elements[0] is lead
    assert answer.elements[1:] == (*prefix, rest)
    assert incoming == original
    assert all(e.kind is ElementKind.GROUND and e.disclosure for e in prefix)


def test_background_alone_is_still_refused_not_relabelled_as_a_step():
    support = Element(kind=ElementKind.GROUND, text="Only background")
    with pytest.raises(ValueError, match="first content element"):
        Answer(
            route=Route.MATTER,
            mode=Mode.FULL_BRIEF,
            mode_statement="Assessment",
            elements=_with_screens([support], SimpleNamespace(rows=())),
        )


@pytest.mark.parametrize("party", ["Unquoted Person", "Nova Surety"])
def test_served_party_disclosure_survives_answer_assembly_and_history(client, monkeypatch, party):
    monkeypatch.setitem(
        SCRIPTED_READS,
        "parties",
        lambda _: json.dumps(
            {
                "parties": [{"name": party, "side": "adverse", "why": "Named in the brief"}],
                "why": "Party read for the file",
            }
        ),
    )
    response = client.post(
        "/api/turn",
        json={
            "message": ("We act for the plaintiff supplier at Hyderabad. "
                        "Nova Surety guaranteed the unpaid goods."),
            "today": "2026-09-22",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["elements"][0]["kind"] in {"action", "question"}
    text = "did not record every name" if party == "Unquoted Person" else "did not cover"
    notices = [e for e in body["elements"] if text in e["text"]]
    assert len(notices) == 1, body["elements"]
    assert notices[0]["kind"] == "ground"
    history = client.get(f"/api/matters/{body['matter_id']}/transcript")
    assert history.status_code == 200
    assert text in history.text
