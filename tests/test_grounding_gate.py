"""Slice 2 — nothing reaches the advocate that is not traceable to retrieved text.

THE PROPERTY THESE TESTS EXIST FOR
-----------------------------------
The output an advocate would actually be harmed by is not a missing citation.
It is a PRESENT one that was never retrieved: fluent, correctly formatted,
pointing at a section that does not say what the sentence claims, or at a case
that does not exist. Nothing in the previous build's architecture could catch
that, and no amount of prompting prevents it.

So the gate does not ask the model to behave. It reads the assembled answer,
extracts every provision number and case name in it, and refuses to emit
anything it cannot trace to a Finding retrieved on this turn.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core import grounding
from nm.core.turn import TurnInput, TurnRefused
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route
from nm.domain.traceability import refuses
from nm.knowledge.jurisdiction import binding_status, normalise_court
from nm.ports.evidence import (
    Binding,
    Coverage,
    EvidenceResult,
    ParaKind,
    SourceKind,
    Treatment,
    TreatmentState,
)
from tests.test_turn_contract import _Evidence, build, finding

pytestmark = pytest.mark.class_a


def answer_of(*texts: str, disclosure: bool = False) -> Answer:
    return Answer(
        route=Route.MATTER, mode=Mode.SHORT_QUESTION, mode_statement="m",
        elements=tuple(
            Element(kind=ElementKind.ACTION, text=t,
                    no_deadline_reason="none identified", disclosure=disclosure)
            for t in texts))


# ============================================== citation coverage ==========

@refuses("P1", 0)
@pytest.mark.eval_id("E-020")
def test_a_provision_the_answer_cites_but_never_retrieved_withholds_the_turn():
    """THE COUNTEREXAMPLE THIS SLICE EXISTS FOR.

    "File under section 27 of the Limitation Act" — plausible, correctly
    formatted, and section 27 was never retrieved. An advocate reading that has
    no way to tell it apart from a citation that was.
    """
    retrieved = (finding(),)   # Article 65, and nothing else
    report = grounding.verify(
        answer_of("Apply under section 27 of the Limitation Act within 30 days."),
        retrieved, retrieved)
    assert not report.clear
    assert report.withholding, "an uncited provision must WITHHOLD, not warn"
    assert any("27" in v.detail for v in report.violations)


@pytest.mark.eval_id("E-020")
def test_a_provision_that_was_retrieved_passes():
    """The gate must not fire on a citation it CAN trace, or it will be
    switched off. A check that cries wolf is worse than no check."""
    retrieved = (finding(),)   # Limitation Act Article 65
    report = grounding.verify(
        answer_of("The governing period is under Article 65."), retrieved, retrieved)
    assert report.clear, [v.detail for v in report.violations]


@pytest.mark.eval_id("E-022")
def test_a_case_name_that_was_never_retrieved_withholds_the_turn():
    """An invented authority is the one an advocate carries into court."""
    retrieved = (finding(),)
    report = grounding.verify(
        answer_of("This is settled by Ramesh Kumar v State of Telangana."),
        retrieved, retrieved)
    assert report.withholding
    assert any("Ramesh Kumar" in v.detail for v in report.violations)


def test_naming_what_could_not_be_retrieved_is_not_citing_it():
    """The product must not be withheld FOR BEING HONEST.

    A gap disclosure names the provision it could not produce. That is the
    opposite of citing it, and the distinction is a field on the element —
    never a phrase the checker looks for, because a phrase can be produced by
    the model and a field cannot.
    """
    retrieved = ()
    honest = grounding.verify(
        answer_of("Not held in the corpus: Limitation Act section 27.",
                  disclosure=True), retrieved, retrieved)
    assert honest.clear

    dishonest = grounding.verify(
        answer_of("Rely on Limitation Act section 27."), retrieved, retrieved)
    assert dishonest.withholding


# ==================================================== quotations ===========

@pytest.mark.eval_id("E-020")
def test_a_quotation_not_verbatim_in_a_retrieved_span_withholds_the_turn():
    """A paraphrase inside quotation marks is a fabricated quotation whether or
    not it happens to be accurate."""
    retrieved = (finding(span="For possession of immovable property or any "
                              "interest therein based on title — twelve years."),)
    report = grounding.verify(
        answer_of('Article 65 provides "a limitation of twelve years running '
                  'from the date of adverse possession".'),
        retrieved, retrieved)
    assert report.withholding
    assert any(v.gate_id == "G-QUOTE" for v in report.violations)


def test_a_verbatim_quotation_survives_whitespace_and_case():
    """The corpus stores hard-wrapped text. A character-exact comparison would
    fail on formatting and teach everyone to disable the gate."""
    retrieved = (finding(span="For possession of immovable property\n  or any "
                              "interest   therein based on title."),)
    report = grounding.verify(
        answer_of('Article 65: "possession of immovable property or any interest '
                  'therein based on title".'),
        retrieved, retrieved)
    assert report.clear, [v.detail for v in report.violations]


# ============================================= the Finding contract ========

def test_an_authority_whose_treatment_was_never_checked_cannot_carry_a_proposition():
    """THE MOST DANGEROUS FALSE NEGATIVE IN THE PRODUCT.

    The citator holds 4,894 entries against 33,791 judgments. A miss means the
    index is silent, NOT that the judgment is undoubted. Reported as clean, an
    overruled authority is presented as good law — and that is the default
    behaviour if the third state is dropped.
    """
    f = finding(
        source_kind=SourceKind.AUTHORITY, ref="X v Y (Supreme Court, 1998)",
        span="the court held that...", locator="X::p1::ratio", store="idx",
        para_kind=ParaKind.RATIO,
        treatment=Treatment.not_checked("no citator entry for 'X v Y'"))
    assert not f.usable
    assert "not checked" in f.blocking_reason
    # It may still be QUOTED with its status disclosed. Unusable is not
    # unmentionable — that distinction is what stops the gate from silently
    # deleting most of the corpus.
    assert f.quotable


def test_an_authority_with_negative_treatment_cannot_carry_a_proposition():
    f = finding(
        source_kind=SourceKind.AUTHORITY, ref="X v Y (Supreme Court, 1998)",
        span="the court held that...", locator="X::p1::ratio", store="idx",
        para_kind=ParaKind.RATIO,
        treatment=Treatment(state=TreatmentState.NEGATIVE,
                            scope="overruled at large", verbs=("OVERRULED",)))
    assert not f.usable
    assert "OVERRULED" in f.blocking_reason


def test_treatment_cannot_claim_clean_without_saying_on_what():
    """A bare `clean` is a claim about the whole judgment. A case overruled on
    limitation is still good law on construction, and a treatment record with
    no scope cannot tell you which one you are holding."""
    with pytest.raises(ValueError, match="scope"):
        Treatment(state=TreatmentState.CLEAN, scope="   ")


def test_a_binding_status_without_its_rule_cannot_be_constructed():
    """Binding status is the field most likely to be wrong in a way that
    changes what an advocate files. It arrives with the rule that produced it
    or it does not arrive."""
    with pytest.raises(ValueError, match="binding status must arrive"):
        finding(binding_reason="  ")


def test_text_not_in_force_on_the_governing_date_cannot_carry_a_proposition():
    """The 2024 codes make this load-bearing. Serving the CrPC for a 2025
    offence is a wrong answer that reads exactly like a right one."""
    f = finding(ref="Indian Penal Code s.447",
                valid_to=date(2024, 6, 30), governing_date=date(2025, 6, 1))
    assert not f.usable
    assert "G-INFORCE" in f.blocking_reason
    assert not f.quotable


# ================================================ binding status ===========

def test_andhra_pradesh_before_the_bifurcation_binds_telangana():
    """The standing decision, and every judgment the corpus holds falls here:
    the Andhra range is 1954-2018 and the post-2018 count is exactly zero."""
    ruling = binding_status("High Court of Andhra Pradesh", 2015, "Telangana")
    assert ruling.status is Binding.BINDING
    assert ruling.rule == "bind-1"
    assert "predecessor" in ruling.reason


@refuses("P2", 0)
def test_andhra_pradesh_after_the_bifurcation_is_not_assessed_rather_than_assumed():
    """THE TRIPWIRE. The decision that AP binds Telangana was taken against a
    corpus holding NO post-2018 Andhra judgment. Extending it silently would
    tell an advocate that a 2022 Andhra judgment binds a Telangana court.

    The corpus holds none today, so this branch guards a FUTURE corpus — which
    is exactly when a rule taken on old measurements does its damage.
    """
    ruling = binding_status("High Court of Andhra Pradesh", 2022, "Telangana")
    assert ruling.status is Binding.NOT_ASSESSED
    assert "bind-1" in ruling.rule
    assert not ruling.assessed


def test_the_supreme_court_binds_regardless_of_date():
    assert binding_status("Supreme Court of India", 1954).status is Binding.BINDING
    assert binding_status("Supreme Court of India", 2025).status is Binding.BINDING


def test_the_unnormalised_court_label_is_not_silently_dropped():
    """One judgment in 33,791 carries `court = "Supreme Court"` where every
    other carries "Supreme Court of India". Code that groups on the stored
    string drops it — a one-row defect today, unbounded after the next ingest.
    """
    assert normalise_court("Supreme Court") is normalise_court("Supreme Court of India")


def test_an_unknown_court_is_not_assessed_rather_than_persuasive():
    """`persuasive` is a finding. "I could not tell" is not, and the difference
    matters because an advocate weighs the two differently."""
    ruling = binding_status("Some Body Nobody Has Heard Of", 2020, "Telangana")
    assert ruling.status is Binding.NOT_ASSESSED


def test_a_jurisdiction_outside_the_corpus_scope_is_refused():
    """The corpus is scoped to Telangana and the Union. An answer about Kerala
    law out of it is confidently wrong and nothing downstream catches that."""
    ruling = binding_status("High Court of Kerala", 2020, "Kerala")
    assert ruling.status is Binding.NOT_ASSESSED
    assert ruling.rule == "scope-1"


# ================================================ end to end ===============

@pytest.mark.eval_id("E-020")
def test_the_engine_withholds_a_turn_whose_answer_invents_a_citation(tmp_path):
    """ON THE ENGINE, not on the checker. A guard that is right in the module
    and wrong in the composition is not a guard."""
    engine, _ = build(
        tmp_path,
        evidence=_Evidence(EvidenceResult(
            coverage=Coverage.ANSWERED, findings=(finding(),),
            searched_stores=("the_limitation_act_1963",))),
        responses={"__default__":
                   "File the suit under section 27 of the Limitation Act."})
    with pytest.raises(TurnRefused) as exc:
        engine.run(TurnInput(
            advocate_id="adv",
            message="we act for the plaintiff in a possession suit"))
    assert "G-GROUND" in str(exc.value)


def test_a_withheld_turn_still_writes_its_metrics(tmp_path):
    """The most diagnostically valuable turns must not be the only ones with no
    record."""
    engine, store = build(
        tmp_path,
        responses={"__default__": "Rely on section 27 of the Limitation Act."})
    with pytest.raises(TurnRefused):
        engine.run(TurnInput(advocate_id="adv", turn_id="turn_withheld",
                             message="we act for the plaintiff in a possession suit"))
    import json
    written = json.loads((tmp_path / "metrics" / "turn_withheld.json").read_text())
    assert written["outcome"] == "gated"
    assert any(g["gate"] == "G-GROUND" for g in written["gates_fired"])
    assert any(g["response"] == "withhold" for g in written["gates_fired"])


# ================================================ coverage =================

class _StaleHighCourt:
    """A measured profile carrying the gap that is really there.

    IT USED TO SAY "No High Court output is held for this jurisdiction", and
    that was false: 4,280 Andhra Pradesh judgments are held and every one of
    them BINDS Telangana under the standing decision in BASELINE.md 1.1. The
    release gate reported zero because it counted the `hc_telangana` court
    LABEL, which no record carries, and a zero from the wrong index reads
    exactly like absence.

    What is true is a RECENCY gap, and the two call for different actions: "I
    have nothing for you" versus "check whether anything has moved since".
    """

    def position(self, jurisdiction):
        from nm.domain.coverage import CoveragePosition, CoverageState
        return CoveragePosition(
            CoverageState.UNMET, jurisdiction,
            "the most recent High Court judgment binding on this jurisdiction "
            "is from 2018, so there is no High Court authority here for the "
            "years since. Supreme Court output runs to 2026 and binds "
            "throughout.",
            "2026-08-30", "v1")


@pytest.mark.eval_id("E-023")
def test_the_corpus_gap_is_disclosed_before_the_authority_search_not_after(tmp_path):
    """THE RUNTIME HALF OF THE REVIEW'S STOP-SHIP #1.

    The corpus's High Court output stops in 2018. That was measured, written
    into docs/BASELINE.md, and inert — a fact in a document is not a gate. The
    advocate is now told before they rely on an answer.

    Told AFTERWARDS it reads as a footnote on a result they have already begun
    to trust. Told first it is a fact about what this corpus can answer.
    """
    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.store.file_store import FileMatterStore
    from nm.core.turn import TurnEngine
    from tests.test_turn_contract import KEY, _model_config

    engine = TurnEngine(
        store=FileMatterStore(tmp_path, key=KEY),
        evidence=_Evidence(EvidenceResult(coverage=Coverage.NOT_HELD,
                                          missing="nothing matched.",
                                          searched_stores=("authority_index",))),
        model=ScriptedModelAdapter(_model_config(), responses={
            "__default__": "Move for interim protection this week."}),
        coverage=_StaleHighCourt())

    out = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff — is there any judgment on adverse "
                "possession we can rely on?"))

    fired = [g for g in out.metrics.gates_fired if g.gate_id == "G-COVERAGE"]
    assert fired, "an authority need in an uncovered jurisdiction must fire G-COVERAGE"
    assert fired[0].state == "unmet"
    assert fired[0].response == "disclose"

    texts = [e.text for e in out.answer.elements]
    disclosure = next(t for t in texts if "Before you rely" in t)
    # The disclosure names the LATEST YEAR HELD, not an absence. Asserting
    # on that number is asserting the distinction the whole fix is about:
    # "I have nothing for you" and "nothing since 2018" are different
    # facts and lead an advocate to different next moves.
    assert "2018" in disclosure
    assert "no High Court output is held" not in disclosure, (
        "the disclosure states an absence. 4,280 High Court judgments bind "
        "this jurisdiction; what is missing is recent ones.")
    # It precedes the retrieval account, not follows it.
    assert texts.index(disclosure) < max(
        (i for i, t in enumerate(texts) if "Not held" in t), default=len(texts))


def test_an_unmeasured_installation_says_so_rather_than_implying_coverage(tmp_path):
    """No coverage port wired is NOT silence. `MET` would claim coverage nobody
    measured, and skipping the gate says the same thing more quietly."""
    engine, _ = build(tmp_path, evidence=_Evidence(EvidenceResult(
        coverage=Coverage.NOT_HELD, missing="nothing matched.",
        searched_stores=("authority_index",))))
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff — any judgment on adverse possession?"))
    fired = [g for g in out.metrics.gates_fired if g.gate_id == "G-COVERAGE"]
    assert fired and fired[0].state == "not_measured"


def test_a_withheld_turn_still_says_what_could_not_be_established(tmp_path):
    """WITHHOLDING THE ANSWER IS NOT WITHHOLDING THE REASON.

    A turn refused with only "the answer cites provision '447', which was not
    retrieved" is true and useless. The turn had already computed the sentence
    that helps — *the Indian Penal Code was not in force on this date* — and
    threw it away with everything else.

    A disclosure asserts no law. It states what could not be established, so it
    can mislead nobody, and it is exactly what an advocate who has been refused
    needs in order to decide what to do next.
    """
    engine, _ = build(
        tmp_path,
        evidence=_Evidence(EvidenceResult(
            coverage=Coverage.NOT_HELD,
            missing="the Indian Penal Code, 1860 matched this question but was "
                    "not in force on 2026-08-30.",
            searched_stores=("manifest",))),
        responses={"__default__": "Rely on section 447 of the Indian Penal Code."})

    with pytest.raises(TurnRefused) as exc:
        engine.run(TurnInput(advocate_id="adv",
                             message="we act for the accused on a criminal trespass"))

    assert exc.value.gates == ("G-GROUND",)
    assert exc.value.disclosures, "a refusal with no reason is a dead end"
    assert any("not in force" in d for d in exc.value.disclosures)


def test_a_year_that_arrives_as_text_does_not_crash_the_binding_rule():
    """The corpus keeps `year` as TEXT and it is sometimes empty.

    This surfaced only when one query happened to return an Andhra High Court
    result — every earlier query had been answered by the Supreme Court branch,
    which returns before the year is ever read. A defect reachable by 12.6% of
    the corpus and invisible to the other 87.4% is the kind that ships.
    """
    assert binding_status("High Court of Andhra Pradesh", "2015").status is Binding.BINDING
    assert binding_status("High Court of Andhra Pradesh", "2022").status is Binding.NOT_ASSESSED

    # Unparseable is NOT ASSESSED, never a guess.
    for bad in ("", "   ", "n.d.", None):
        assert binding_status("High Court of Andhra Pradesh", bad).status is Binding.NOT_ASSESSED
