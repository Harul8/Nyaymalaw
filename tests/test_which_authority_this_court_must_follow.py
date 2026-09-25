"""LB-122. WHICH OF THE RETRIEVED AUTHORITIES THIS COURT MUST FOLLOW.

WHAT WAS ALREADY BUILT, MEASURED BEFORE ANYTHING WAS WRITTEN. The plan row was
drafted from a count of mentions in the plan, not from the code, and the code
already had four of the five pieces:

    binding by court      `nm.knowledge.jurisdiction.binding_status`   BUILT
    subsequent treatment  `nm.knowledge.citator`                       BUILT
    ratio versus obiter   `Finding` / G-ATTRIB                         BUILT
    bench strength        `nm.knowledge.identity.supersedes`           BUILT
    any of it reaching the advocate when two authorities disagree      NOT

`supersedes` had no production caller -- its only callers were tests. Every
authority was rendered with its own bench inside its `ref` and nothing compared
them, so an advocate reading two decisions on one point was left to work out
which binds them. That is what this closes, and these tests hold the line that
the RULE is not restated: it is applied where it already lives.
"""
from __future__ import annotations

import pytest
from nm.core.turn import TurnInput
from nm.knowledge import authority_weight as curated
from nm.knowledge.identity import CaseIdentity
from nm.ports.authority_weight import Standing, Weighing

from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a


class _Index:
    """An identity index holding exactly the cases a test names.

    Not a subclass of `IdentityIndex`: the real one reads sqlite and its
    `available` is a file check. What the port needs is `case`, and a double
    that answered through the real reader would be testing sqlite.
    """

    def __init__(self, cases: dict[str, CaseIdentity]) -> None:
        self._cases = cases
        self.available = True

    def case(self, case_id: str) -> CaseIdentity | None:
        return self._cases.get(case_id)


def _case(case_id: str, court: str, bench: int | None, title: str,
          source: str = "bench_header") -> CaseIdentity:
    return CaseIdentity(case_id=case_id, court=court, title=title,
                        bench_size=bench, bench_source=source)


SC3 = _case("sc3", "Supreme Court of India", 3, "Anand v State")
HC2 = _case("hc2", "High Court for the State of Telangana", 2, "Rao v Reddy")
HC2B = _case("hc2b", "High Court for the State of Telangana", 2, "Naidu v Kumar")
HC1 = _case("hc1", "High Court for the State of Telangana", 1, "Iqbal v Sharma")
HCX = _case("hcx", "High Court for the State of Telangana", None, "Das v Bose")


def _weigh(*cases: CaseIdentity) -> tuple[Weighing, ...]:
    index = _Index({c.case_id: c for c in cases})
    return curated.weigh(tuple(f"{c.case_id}::ch::ratio" for c in cases), index)


# ================================================== the rule is not restated ==

def test_this_module_states_no_hierarchy_rule_of_its_own():
    """CLAUDE.md section 4. `identity.supersedes` owns "a larger bench
    supersedes a smaller one within the same court"; a second statement here
    would be two owners for one rule, one of them hardened and the other not.

    Read off the source, because a comment promising not to restate it is not
    a mechanism.
    """
    import inspect

    source = inspect.getsource(curated)
    for own_rule in ("bench_size >", "bench_size <", "tier >", "tier <",
                     "Tier.", "supreme", "Supreme"):
        assert own_rule not in source, (
            f"{own_rule!r} appears in nm.knowledge.authority_weight, which "
            f"means the hierarchy rule has a second home")
    assert "supersedes(" in source, "the one owner is not consulted at all"


# ============================================================== the findings ==

def test_a_senior_court_is_named_as_superseding_the_junior_one():
    (weighing,) = _weigh(SC3, HC2)
    assert weighing.standing is Standing.SUPERSEDES
    assert weighing.higher == "Anand v State"
    assert weighing.lower == "Rao v Reddy"
    assert weighing.reason.strip()


def test_a_larger_bench_supersedes_a_smaller_one_in_the_same_court():
    (weighing,) = _weigh(HC2, HC1)
    assert weighing.standing is Standing.SUPERSEDES
    assert weighing.higher == "Rao v Reddy"
    assert weighing.lower == "Iqbal v Sharma"


def test_co_ordinate_benches_are_a_finding_and_not_a_silence():
    """THE DISTINCTION THE WHOLE MODULE TURNS ON. Two equal benches that
    disagree is something an advocate ACTS on -- the conflict is resolved by
    reference to a larger bench. Reporting it as "could not be ranked" would
    hide a finding inside a gap."""
    (weighing,) = _weigh(HC2, HC2B)
    assert weighing.standing is Standing.CO_ORDINATE
    assert weighing.standing is not Standing.NOT_RECORDED
    assert not weighing.higher and not weighing.lower, (
        "a higher authority was named between co-ordinate benches")


def test_an_unrecorded_bench_is_a_gap_and_never_co_ordinate():
    """THE OTHER DIRECTION. A bench nobody recorded is a gap in what is held.
    Calling it co-ordinate would assert that two authorities are of equal
    weight on the strength of not knowing."""
    (weighing,) = _weigh(HC2, HCX)
    assert weighing.standing is Standing.NOT_RECORDED
    assert weighing.standing is not Standing.CO_ORDINATE
    assert not weighing.higher


def test_a_case_the_index_does_not_hold_produces_nothing_at_all():
    """NOT every pair deserves a row. An unindexed judgment has no identity to
    compare, and a line for each would bury the pairs that matter under the
    corpus's coverage."""
    index = _Index({HC2.case_id: HC2})
    assert curated.weigh(("hc2::ch::ratio", "unknown::ch::ratio"), index) == ()


def test_one_authority_is_never_weighed_against_itself():
    index = _Index({HC2.case_id: HC2})
    assert curated.weigh(("hc2::ch::ratio", "hc2::ch2::ratio"), index) == ()


def test_the_comparison_is_bounded_and_says_so_rather_than_truncating():
    """A ranking that stopped early without saying so would look like a
    ranking that found nothing."""
    many = [_case(f"c{i}", "High Court for the State of Telangana", 2,
                  f"Case {i}") for i in range(curated.MOST_AUTHORITIES + 3)]
    weighed = _weigh(*many)
    bounded = [w for w in weighed
               if "were not" in w.reason and "ranked" in w.reason]
    assert bounded, "the bound was reached and nothing said so"
    assert str(len(many)) in bounded[0].reason


# ===================================================== on the served turn ====

BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for.")


class _Weigher:
    """The port, answering from cases a test names, whatever was retrieved."""

    def __init__(self, weighings: tuple[Weighing, ...]) -> None:
        self._weighings = weighings
        self.asked: list[tuple[str, ...]] = []

    def weigh(self, locators: tuple[str, ...]) -> tuple[Weighing, ...]:
        self.asked.append(locators)
        return self._weighings


def _authority(case_id: str, title: str) -> object:
    """A usable AUTHORITY finding, so the turn has two to compare.

    The shared double returns one PROVISION, which has no bench and is
    correctly never weighed -- so a served test built on it would exercise the
    early return and prove nothing about the ranking.
    """
    from nm.ports.evidence import (
        Binding,
        ParaKind,
        SourceKind,
        Treatment,
        TreatmentState,
    )

    from tests.test_turn_contract import finding

    return finding(
        proposition="whether possession follows title",
        source_kind=SourceKind.AUTHORITY,
        ref=f"{title} (High Court for the State of Telangana, 2019)",
        span="Possession follows title unless the defendant shows a better one.",
        locator=f"{case_id}::ch1::ratio",
        store="authority_index",
        binding=Binding.BINDING,
        binding_reason="the High Court for the State of Telangana",
        para_kind=ParaKind.ATTRIBUTABLE,
        treatment=Treatment(state=TreatmentState.CLEAN,
                            scope="nothing in the judgments held "
                                  "treats this one adversely"),
        valid_from=None, valid_to=None)


def _run(tmp_path, weigher):
    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.store.file_store import FileMatterStore
    from nm.core.turn import TurnEngine
    from nm.ports.evidence import Coverage, EvidenceResult

    from tests.test_turn_contract import (
        KEY,
        _Evidence,
        _model_config,
        briefed,
        finding,
    )

    evidence = _Evidence(EvidenceResult(
        coverage=Coverage.ANSWERED,
        findings=(finding(),
                  _authority("sc3", "Anand v State"),
                  _authority("hc2", "Rao v Reddy")),
        searched_stores=("the_limitation_act_1963", "authority_index")))
    engine = briefed(TurnEngine(
        store=FileMatterStore(tmp_path, key=KEY), evidence=evidence,
        model=ScriptedModelAdapter(_model_config(),
                                   responses={"__default__": "File the suit."}),
        authority_weight=weigher))
    return engine.run(TurnInput(advocate_id="adv_1", message=BRIEF))


def test_an_unwired_installation_ranks_nothing_and_claims_nothing(tmp_path):
    """AN ABSENT PORT IS NOT A FINDING (CLAUDE.md section 9). With no identity
    index this must not report that two authorities could not be compared --
    that reads as a fact about the judgments rather than about the
    installation, and the coverage disclosure owns that statement."""
    engine, _ = build(tmp_path)
    assert engine._authority_weight is None
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF))
    said = " ".join(e.text for e in out.answer.elements)
    assert "could not be ranked" not in said
    assert "supersedes" not in said


def test_the_advocate_is_told_which_authority_supersedes_which(tmp_path):
    """A guard that is right in the knowledge plane and never reaches the
    answer is not a guard (CLAUDE.md section 8)."""
    weigher = _Weigher((Weighing(
        standing=Standing.SUPERSEDES, reason="Full Bench (5) supersedes "
        "Division Bench (2) in the same court",
        higher="Anand v State", lower="Rao v Reddy"),))
    out = _run(tmp_path, weigher)
    said = " ".join(e.text for e in out.answer.elements)
    assert "Anand v State supersedes Rao v Reddy" in said, said[-900:]
    assert "Full Bench (5)" in said


def test_a_co_ordinate_conflict_is_served_loudly_and_disposes_of_nothing(tmp_path):
    weigher = _Weigher((Weighing(
        standing=Standing.CO_ORDINATE,
        reason="co-ordinate benches (Division Bench (2))"),))
    out = _run(tmp_path, weigher)
    conflict = [e for e in out.answer.elements
                if "equal weight" in e.text]
    assert conflict, " ".join(e.text for e in out.answer.elements)[-900:]
    assert "Neither disposes of the other" in conflict[0].text


def test_only_authorities_are_weighed_not_provisions(tmp_path):
    """A provision has no bench. Handing the ranker a statutory locator would
    ask a question that cannot arise and would spend the bound on it."""
    weigher = _Weigher(())
    _run(tmp_path, weigher)
    for asked in weigher.asked:
        for locator in asked:
            assert "schedule_article" not in locator, locator
            assert "the_limitation_act" not in locator, locator
