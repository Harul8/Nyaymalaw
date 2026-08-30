"""The product's OWN prose must not read as a citation.

WHY THIS FILE EXISTS — AND IT IS THE GENERALISATION OF A PATCH
---------------------------------------------------------------
The grounding gate withheld a correct turn because the answer "cited provision
141 which was not retrieved". The 141 was not the model's. It was OURS: the
binding explanation read

    "the Supreme Court binds every court in India (Constitution, Art. 141)"

and the Constitution is not in this corpus. The gate was right — the product
was citing law it had not retrieved, in its own explanatory text.

I fixed the sentence. That is a PATCH: it repairs the one string that happened
to be caught and leaves every other composed string free to do the same thing.
CLAUDE.md's test is whether the fix can be stated without naming the Act,
section or phrase that exposed it, and "remove Art. 141 from the binding
reason" fails that test outright.

THE RULE, STATED GENERALLY
--------------------------
Text the ENGINE composes — binding reasons, gate disclosures, refusal
explanations, blocking questions — explains what the product is doing. It is
never a legal proposition, so it must never carry a provision reference or a
case name in a form that reads as a citation. Principle H9: an inference is
marked as an inference, and no inference carries a citation as though it were
one.

Two things follow, and both are enforced here:

  * the gate cannot fire on our own words, so it stops crying wolf on correct
    turns;
  * an advocate can never mistake the product's reasoning for retrieved law,
    which is the substantive point and the reason H9 exists.

Rule ids like `art-141` and `bind-1` are deliberately fine. They name a rule,
they do not quote a provision, and `provisions_cited` does not match them —
which is itself the check that they are written in a form nobody reads as a
citation.
"""
from __future__ import annotations

import pytest

from nm.domain.citation import cases_named, provisions_cited
from nm.domain.gates import GATES
from nm.domain.traceability import refuses
from nm.knowledge.jurisdiction import Court, binding_status

pytestmark = pytest.mark.class_a


def _offences(label: str, text: str) -> list[str]:
    out = []
    for number in provisions_cited(text or ""):
        out.append(f"{label} cites provision {number!r}")
    for case in cases_named(text or ""):
        out.append(f"{label} names the case {case!r}")
    return out


@refuses("P1", 1)
def test_no_binding_reason_reads_as_a_citation():
    """Every rule the jurisdiction module can produce, over every court.

    This is the check the Art. 141 patch should have been. It enumerates the
    RULES rather than the strings, so a new court, a new jurisdiction or a
    reworded reason is covered without anyone remembering to come back here.
    """
    offences: list[str] = []
    courts = ["Supreme Court of India", "Supreme Court",
              "High Court of Telangana", "High Court of Andhra Pradesh",
              "High Court of Judicature at Hyderabad", "High Court of Kerala",
              "District Court", "Some Body Nobody Names", "", None]
    years = [None, 1954, 2018, 2019, 2025]
    places = ["Telangana", "Union of India", "Kerala", ""]

    for court in courts:
        for year in years:
            for place in places:
                ruling = binding_status(court, year, place)
                offences += _offences(
                    f"binding_reason[{ruling.rule}]", ruling.reason)

    assert not offences, (
        "the product's own explanation of a binding rule reads as a legal "
        "citation:\n  " + "\n  ".join(sorted(set(offences)))
        + "\n\nComposed text explains what the product is DOING. It is not a "
          "proposition, so it must not carry a provision reference — the "
          "grounding gate cannot tell the difference, and neither can an "
          "advocate.")


def test_no_gate_disclosure_reads_as_a_citation():
    """The same rule for every gate's advocate-visible line.

    These are shown on turns that succeed, so a citation form here would both
    trip the gate and put an uncited provision in front of the advocate.
    """
    offences: list[str] = []
    for g in GATES:
        offences += _offences(f"{g.id}.visible", g.visible)
        offences += _offences(f"{g.id}.condition", g.condition)
    assert not offences, (
        "a gate's visible text reads as a citation:\n  "
        + "\n  ".join(sorted(set(offences))))


def test_a_rule_id_is_not_a_citation_form():
    """`art-141` and `bind-1` name rules. They must stay unparseable as
    provision references, which is what makes them safe to print."""
    assert not provisions_cited("art-141")
    assert not provisions_cited("bind-1 hc-own scope-1 court-unknown")
    # And the check is not vacuous: a real citation form still matches.
    assert provisions_cited("Article 141") == {"141"}


def test_every_court_still_gets_a_reason():
    """The generalisation must not be satisfied by emptying the field.

    Deleting the explanation would pass every assertion above and destroy the
    thing binding status is for — an advocate seeing WHY an authority was
    called binding.
    """
    for court in ("Supreme Court of India", "High Court of Andhra Pradesh",
                  "High Court of Kerala", "Nothing Recognisable"):
        ruling = binding_status(court, 2015, "Telangana")
        assert len(ruling.reason.strip()) > 25, f"{court}: reason is too thin"
        assert ruling.rule.strip()
        assert ruling.court in Court
