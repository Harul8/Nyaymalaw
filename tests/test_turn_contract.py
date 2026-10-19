"""The turn contract. PRD §7.3.

Every test here is a COUNTEREXAMPLE from the previous build made runnable. The
tests are written against the SERVED PATH wherever the property is about the
wire, because a guard that is right in the core and wrong at the edge is not a
guard -- and every defect the first external review found lived in that gap.
"""
from __future__ import annotations

import ast
import pathlib
from datetime import date

import pytest

from nm.advise.answer_contracts import Element, ElementKind, Signal
from nm.Archives.legal_brain.retrieve.evidence_port import (
    Binding,
    Finding,
    ParaKind,
    SourceKind,
    Treatment,
)
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import Tier
from nm.shared.store_file_store import EncryptionNotConfigured, FileMatterStore
from nm.shared.store_port import StaleWrite
from nm.shared.traceability_contracts import refuses
from nm.work_the_file.matter_contracts import Basis, Matter, Posture, Role, Side, Thread

ROOT = pathlib.Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.class_a

KEY = "test-key-not-a-secret"


def _model_config() -> ModelConfig:
    return ModelConfig(tiers={
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, "scripted", "scripted-1", None, None),
        # THE HARD TIER IS CONFIGURED HERE BECAUSE IT IS CONFIGURED IN
        # PRODUCTION, as of 5 September 2026. A fixture without it tests a
        # deployment that no longer ships, and the six decisive reads would
        # raise TierUnavailable on every turn of every test -- which is what
        # happened the moment the escalation landed.
        #
        # Its ABSENCE is exercised deliberately instead, in
        # tests/test_reads_registry.py::test_an_absent_hard_tier_degrades_out_loud,
        # by an adapter that refuses the tier. That is the right shape: the
        # ordinary fixture matches production, and the degraded path is driven
        # rather than left as the default nobody chose.
        Tier.HARD: TierConfig(Tier.HARD, "scripted", "scripted-hard", None, None),
        Tier.EMBED: TierConfig(Tier.EMBED, "scripted", "text-embedding-3-large", None, None),
    })


def finding(**kw) -> Finding:
    """A Finding with every required field filled.

    A helper, not a default. The slice-2 contract removed the defaults from
    `binding`, `para_kind` and `treatment` precisely because a default is a
    decision taken on behalf of every call site that forgets -- so this fills
    them EXPLICITLY and each test overrides what it is actually testing.
    """
    base = dict(
        proposition="Limitation Act, 1963 Article 65",
        source_kind=SourceKind.PROVISION,
        ref="Limitation Act, 1963 Article 65",
        span="For possession of immovable property... twelve years.",
        locator="the_limitation_act_1963::Article_65::schedule_article",
        store="the_limitation_act_1963",
        binding=Binding.BINDING,
        binding_for="Telangana",
        binding_reason="an Act of Parliament in force, applying of its own force",
        supports=True,
        para_kind=ParaKind.UNKNOWN,
        treatment=Treatment.statutory(),
        # A PROVISION must carry its validity window [E-021]. Without it
        # `in_force` cannot refuse superseded text, and the 2024 codes make
        # that the difference between right and confidently wrong.
        valid_from=date(1964, 1, 1),
    )
    base.update(kw)
    return Finding(**base)


#: What a matter that has been through intake holds. BK-34.
#:
#: THE FIXTURE SUPPLIES IT BECAUSE MOST TESTS ARE NOT ABOUT INTAKE. A matter
#: whose conflict, scope and capacity screens have not been answered is
#: blocked before any substance is admitted -- which is the row working -- and
#: a suite in which every test therefore becomes a test of the intake block is
#: a suite that has stopped testing limitation, proof, theory and the rest.
#:
#: IT IS THE REAL PATH AND NOT A BACK DOOR: these are the same fields the
#: browser sends from the intake form, written to the matter before the
#: screens read it. `build(..., intake=False)` opts out, and the tests that
#: are about the screens use it.
INTAKE_PARTIES = {"Ramesh Traders": "client", "Kiran Steels": "adverse"}
INTAKE_ANSWERS = {"scope": "the recovery work described in this brief"}
INTAKE_CAPACITY = {"state": "not_in_doubt",
                   "basis": "the fixture advocate explicitly assessed capacity to instruct"}


# ======================================================= routing ==========


# ======================================================= posture ==========


@pytest.mark.eval_id("E-031")
def test_side_is_derived_from_role_and_never_stored():
    assert Posture(role=Role.PLAINTIFF).side is Side.MOVING
    assert Posture(role=Role.ACCUSED).side is Side.DEFENDING
    assert Posture().side is Side.UNKNOWN
    assert not hasattr(Posture(), "_side")


@refuses("C3", 2)
def test_a_stated_posture_is_never_silently_flipped():
    """COUNTEREXAMPLE: a turn-5 reversal is worse than a turn-1 error, because
    by then the advocate has acted on it."""
    p = Posture().enrich(Role.ACCUSED, Basis.STATED)
    flipped = p.enrich(Role.COMPLAINANT, Basis.STATED)
    assert flipped.role is Role.ACCUSED, "the posture on record must not change"
    assert flipped.conflicts, "the contradiction must surface as a conflict"


# ================================================== the Answer type =======

@pytest.mark.eval_id("E-012")
def test_no_element_kind_can_hold_a_recital():
    assert {k.value for k in ElementKind} == {"action", "finding", "question", "ground"}


def test_an_action_without_a_by_when_cannot_be_constructed():
    with pytest.raises(ValueError):
        Element(kind=ElementKind.ACTION, text="File the suit")


@refuses("A2", 4)
@pytest.mark.eval_id("E-065")
def test_a_loud_signal_cannot_be_marked_collapsible():
    """COUNTEREXAMPLE: 'concise' becoming the mechanism that suppresses exactly
    the signals we fought to raise."""
    with pytest.raises(ValueError):
        Element(kind=ElementKind.FINDING, text="Time-barred.",
                signal=Signal.LIMITATION_BAR, collapsible=True)


# =================================================== store discipline =====

@pytest.mark.eval_id("E-011")
@refuses("I1", 1)
def test_an_unconfigured_key_is_a_hard_failure(tmp_path):
    """COUNTEREXAMPLE: making matters durable once wrote them to disk in
    PLAINTEXT, because encryption was a silent no-op when unconfigured."""
    with pytest.raises(EncryptionNotConfigured):
        FileMatterStore(tmp_path, key="")


@pytest.mark.eval_id("E-021b")
def test_a_stale_commit_is_refused_rather_than_overwriting(tmp_path):
    store = FileMatterStore(tmp_path, key=KEY)
    m = Matter.create(advocate_id="adv", title="t")
    store.commit(m, expected_version=0)
    moved = store.commit(m.with_thread(Thread.create("later")), expected_version=0)
    with pytest.raises(StaleWrite):
        store.commit(m.with_thread(Thread.create("racing")), expected_version=0)
    assert moved.version > m.version


# ================================================ idempotency & metrics ===


@pytest.mark.eval_id("E-022")
def test_a_judgment_proposition_cannot_come_from_counsels_submission():
    """COUNTEREXAMPLE: 14.8% of retrievable paragraphs are counsel's
    submission, and quoting one as the holding is a live risk."""
    with pytest.raises(ValueError):
        finding(source_kind=SourceKind.AUTHORITY, ref="X v Y",
                span="counsel submitted that...", locator="l", store="s",
                para_kind=ParaKind.NOT_ATTRIBUTABLE,
                treatment=Treatment.not_checked("no citator entry"))


# ================================================ THE SERVED PATH =========


# ============================== THE SCREEN BOUNDARY =======================


# ============ BK-2 — the screens reach the advocate =========================


def test_the_answer_coverage_check_can_see_an_uncovered_site():
    """POSITIVE CONTROL. S11 -- a check that cannot fail proves nothing,
    and this one spent a slice passing over two uncovered sites.
    """
    planted = ast.parse(
        "Answer(route=r, elements=tuple([*head, *derived]))")
    node = next(n for n in ast.walk(planted)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "Answer")
    text = ast.unparse([k for k in node.keywords if k.arg == "elements"][0].value)
    assert "_with_screens" not in text, (
        "the check would not notice an Answer built without the assembler")

