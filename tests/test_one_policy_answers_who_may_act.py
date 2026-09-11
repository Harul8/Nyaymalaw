"""WHO MAY DO WHAT, ASKED ONCE. BK-63-AC1, BK-62-AC1. P13.

THE RULE, stated without the operation that exposed it
--------------------------------------------------------
**A recommendation is not an authority to act on it, and the record of who may
act is a fact about the matter rather than about the account that signed in.**

An advocate advises. A solicitor instructs. A client decides. The same human
may hold two of those on two different files, so the capacity is recorded per
matter and read from the commission -- never taken from the request, because a
caller that could name its own capacity could name `deciding` and concede the
client's case, which would make the whole policy decorative.

WHAT IS ASSERTED
------------------
    one module answers the question, and a second implementation fails the build
    an unrecorded capacity is NOT_ESTABLISHED and never a refusal
    advising may not decide, concede or act externally
    instructing may not concede -- the case is not the solicitor's to give up
    a refusal carries WHO attempted WHAT and WHY, not merely a false
    a commission names what it does not establish, item by item
    a material change reopens work and an immaterial one does not
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from nm.domain.authority import (
    PERMITTED,
    Act,
    ActingAs,
    Standing,
    permits,
)
from nm.domain.commission import (
    MATERIAL,
    Commission,
    Deadline,
    Party,
    WorkProduct,
    material_changes,
)

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
OWNER = "nm/domain/authority.py"


# =========================== the third state ================================

def test_an_unrecorded_capacity_is_not_established_and_not_a_refusal():
    """THE DISTINCTION THAT MATTERS MOST HERE. Refusing an advocate whose own
    capacity was simply never written down sends them looking for a permission
    problem; the actual fix is to record the capacity."""
    ruling = permits("adv-1", ActingAs.UNKNOWN, Act.ADVISE)
    assert ruling.standing is Standing.NOT_ESTABLISHED
    assert not ruling.authorises()
    assert "not established" in ruling.why
    assert "this is not a refusal" in ruling.why


def test_an_unnamed_actor_is_not_established_either():
    """An attempt with no actor has no recorded capacity to check."""
    for blank in ("", "   "):
        assert permits(blank, ActingAs.DECIDING,
                       Act.CONCEDE).standing is Standing.NOT_ESTABLISHED


def test_the_third_state_is_a_value_and_only_one_state_authorises():
    assert Standing.not_established() is Standing.NOT_ESTABLISHED
    assert ActingAs.not_established() is ActingAs.UNKNOWN
    authorising = [s for s in Standing if s.authorises()]
    assert authorising == [Standing.PERMITTED]


# ====================== a recommendation is not an authority ================

@pytest.mark.parametrize("act", [Act.DECIDE, Act.CONCEDE, Act.INSTRUCT,
                                 Act.ACT_EXTERNALLY])
def test_advising_may_not_decide_concede_instruct_or_act(act):
    """THE POINT OF THE PACKET. The advocate is the one person certain to have
    an opinion about the concession, and the one with no authority to make it."""
    ruling = permits("adv-1", ActingAs.ADVISING, act)
    assert ruling.standing is Standing.REFUSED
    assert not ruling.authorises()


def test_advising_may_advise_and_read():
    """The negative control: a policy that refused everything would satisfy
    every refusal test above and the product would do nothing."""
    for act in (Act.ADVISE, Act.READ):
        assert permits("adv-1", ActingAs.ADVISING, act).authorises()


def test_instructing_is_not_deciding():
    """An instructing solicitor relays what the client wants. The case is not
    theirs to give up, and collapsing the two fields is how it gets given."""
    assert permits("sol-1", ActingAs.INSTRUCTING, Act.INSTRUCT).authorises()
    assert not permits("sol-1", ActingAs.INSTRUCTING, Act.CONCEDE).authorises()
    assert not permits("sol-1", ActingAs.INSTRUCTING, Act.DECIDE).authorises()


def test_deciding_may_concede_because_the_case_is_theirs():
    assert permits("client-1", ActingAs.DECIDING, Act.CONCEDE).authorises()
    assert permits("client-1", ActingAs.DECIDING, Act.DECIDE).authorises()


def test_assisting_may_only_read():
    allowed = {a for a in Act if permits("clerk", ActingAs.ASSISTING, a).authorises()}
    assert allowed == {Act.READ}


def test_every_capacity_except_unknown_has_a_declared_permission_set():
    """A capacity missing from the table answers NOT_ESTABLISHED, which is
    right for UNKNOWN and wrong for anything somebody has actually recorded."""
    declared = set(PERMITTED)
    assert declared == {c for c in ActingAs if c is not ActingAs.UNKNOWN}


# ===================== a refusal is a record, not a boolean =================

def test_a_refusal_says_who_attempted_what_and_why():
    """BK-63-AC1 requires unauthorised operations refused AND RECORDED. A
    boolean the caller drops satisfies the first half and none of the second."""
    ruling = permits("clerk-7", ActingAs.ASSISTING, Act.CONCEDE)
    assert ruling.actor_id == "clerk-7"
    assert ruling.act is Act.CONCEDE
    assert ruling.capacity is ActingAs.ASSISTING
    line = ruling.as_line()
    assert "clerk-7" in line and "concede" in line and "refused" in line
    assert ruling.as_dict()["standing"] == "refused"


def test_a_ruling_carries_no_client_material():
    """An authority decision is about WHO, not about what the matter says."""
    ruling = permits("adv-1", ActingAs.ADVISING, Act.CONCEDE)
    assert "possession" not in ruling.as_line()
    assert set(ruling.as_dict()) == {
        "standing", "actor_id", "act", "capacity", "why"}


# ======================= one owner, over the product ========================

def _deciders_in(name: str, source: str) -> list[str]:
    """Modules that decide authority for themselves.

    ONE PROBE, read by the sweep and by its control. A module is an offender
    when it maps a capacity to a permitted set of its own -- a `PERMITTED`-
    shaped dict or a chain of comparisons against `ActingAs` members -- rather
    than calling `permits`.
    """
    found: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            names = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            if {"CONCEDE", "DECIDE", "ACT_EXTERNALLY"} & names:
                found.append(f"{name}:{node.lineno} compares an Act directly")
        # BOTH ASSIGNMENT FORMS. The owner writes `PERMITTED: dict[...] = {...}`,
        # which is an AnnAssign, and the first draft of this probe looked only
        # at Assign -- so it could not see the very table it exempts, and
        # `test_the_owner_is_the_only_module_that_needs_the_exemption` caught
        # it. A scan blind to the real shape passes every module vacuously.
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        for target in targets:
            if target.id.isupper() and node.value is not None:
                # ACTUAL ENUM REFERENCES, not a substring of the AST dump. The
                # first draft matched `"Act" in ast.dump(...)` and flagged the
                # gate matrix, whose condition strings contain the word "fact".
                # A scan that fires on prose is one somebody silences.
                referenced = {
                    child.value.id
                    for child in ast.walk(node.value)
                    if isinstance(child, ast.Attribute)
                    and isinstance(child.value, ast.Name)
                }
                if {"ActingAs", "Act"} <= referenced:
                    found.append(
                        f"{name}:{node.lineno} declares a second "
                        f"capacity-to-act table")
    return found


def test_only_one_module_decides_who_may_act():
    """CLAUDE.md section 4 -- the question is not where the other copy is, but
    what makes a second copy impossible. Four callers ask this question and the
    moment two of them answer it there are two answers."""
    offenders: list[str] = []
    for path in sorted((ROOT / "nm").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative == OWNER:
            continue
        offenders.extend(
            _deciders_in(relative, path.read_text(encoding="utf8")))
    assert not offenders, (
        f"these decide authority instead of calling `permits` in {OWNER}: "
        f"{offenders}")


def test_the_sweep_can_see_a_second_decider():
    """A sweep that only ever finds nothing has not been shown to find
    anything. B-049."""
    planted = "\n".join((
        "SECOND = {ActingAs.ADVISING: {Act.CONCEDE}}",
        "THIRD: dict[ActingAs, set[Act]] = {ActingAs.ASSISTING: {Act.DECIDE}}",
        "def allowed(act):",
        "    return act == Act.CONCEDE",
    ))
    seen = _deciders_in("planted.py", planted)
    # BOTH ASSIGNMENT FORMS ARE PLANTED, because the probe was blind to one of
    # them and a control that plants only the form it already sees proves
    # nothing about the form it does not.
    assert len(seen) == 3, seen
    assert any("second capacity-to-act table" in s for s in seen)
    assert any("compares an Act directly" in s for s in seen)
    assert not _deciders_in("clean.py", "def ok(a):\n    return permits(a)\n")


def test_the_owner_is_the_only_module_that_needs_the_exemption():
    """If the owner stopped holding the table, the exemption above would be
    hiding an empty policy rather than the real one."""
    source = (ROOT / OWNER).read_text(encoding="utf8")
    assert "PERMITTED" in source and "def permits(" in source
    assert _deciders_in(OWNER, source), (
        "the owner no longer declares the table, so the sweep's exemption "
        "covers nothing and every other module would pass vacuously")


# ============================ the commission ================================

def _full() -> Commission:
    return Commission(
        objective="recover the price of goods sold",
        work_product=WorkProduct.ADVICE,
        scope="the unpaid invoice of 3 March 2024",
        instructing=Party("sol-1", "the instructing solicitor",
                          ActingAs.INSTRUCTING),
        deciding=Party("client-1", "the client", ActingAs.DECIDING),
        forum="City Civil Court, Hyderabad",
        deadline=Deadline.on_date("2027-03-03", "Limitation Act art 14"))


def test_a_commission_names_each_thing_it_does_not_establish():
    """A LIST AND NOT A FLAG. `complete: false` tells an advocate something is
    missing and not which, so the one they chase is whichever they think of."""
    unknowns = Commission().unknowns()
    assert len(unknowns) >= 7
    assert any("who instructs" in u for u in unknowns)
    assert any("who decides" in u for u in unknowns)
    assert any("the forum" in u for u in unknowns)
    assert not Commission().established


def test_a_full_commission_establishes_itself():
    """The negative control for the unknowns list."""
    assert _full().unknowns() == ()
    assert _full().established


def test_a_decision_maker_recorded_as_something_else_is_named_as_a_gap():
    """Naming a person as the decision maker does not make them one; the
    capacity is the record, and a mismatch is a gap rather than a silent
    promotion."""
    wrong = Commission(
        objective="o", work_product=WorkProduct.ADVICE, scope="s",
        instructing=Party("sol-1", "the solicitor", ActingAs.INSTRUCTING),
        deciding=Party("clerk-1", "a clerk", ActingAs.ASSISTING),
        forum="f", deadline=Deadline.none_applies("advisory only"))
    assert any("recorded as assisting" in u for u in wrong.unknowns())


# ============================== the deadline ================================

def test_an_unknown_deadline_carries_its_reason():
    """A file saying `deadline: unknown` with no reason is a field nobody
    filled in; one with a reason is a piece of work with a next step."""
    with pytest.raises(ValueError):
        Deadline(kind=Deadline.unknown("x").kind, reason="")
    assert "not established" in Deadline.unknown("service is unconfirmed").said()


def test_no_deadline_and_an_unassessed_deadline_are_different_sentences():
    """The single most repeated defect in this codebase, at the one place an
    advocate acts on the answer."""
    none_applies = Deadline.none_applies("this is an advisory opinion")
    unknown = Deadline.unknown("nobody has computed it")
    assert none_applies.assessed and not unknown.assessed
    assert none_applies.said() != unknown.said()
    assert "no deadline applies" in none_applies.said()


def test_a_dated_deadline_must_say_what_produced_it():
    """A date with no basis cannot be checked and cannot be corrected."""
    with pytest.raises(ValueError):
        Deadline.on_date("2027-03-03", "")
    with pytest.raises(ValueError):
        Deadline.on_date("", "Limitation Act art 14")
    assert "Limitation Act" in Deadline.on_date(
        "2027-03-03", "Limitation Act art 14").said()


def test_an_unreviewed_date_says_so_on_the_cover():
    assert "(unreviewed)" in Deadline.on_date("2027-03-03", "art 14").said()


# ========================== material change reopens =========================

def test_changing_the_work_product_reopens_work():
    first = _full()
    second = first.next_version(work_product=WorkProduct.NEGOTIATION)
    assert "work_product" in material_changes(first, second)
    assert second.version == first.version + 1


def test_changing_the_deadline_or_the_scope_reopens_work():
    first = _full()
    assert "deadline" in material_changes(
        first, first.next_version(deadline=Deadline.unknown("reopened")))
    assert "scope" in material_changes(
        first, first.next_version(scope="the whole account"))


def test_an_immaterial_change_reopens_nothing():
    """Not every edit invalidates work. A reopen on every save would train an
    advocate to ignore the signal."""
    first = _full()
    assert material_changes(
        first, first.next_version(because="tidied the wording")) == ()


def test_the_first_commission_reopens_nothing():
    """There was no earlier work to invalidate."""
    assert material_changes(None, _full()) == ()


def test_the_material_set_is_read_from_one_declaration():
    """A field added to `Commission` is immaterial until somebody puts it in
    `MATERIAL` deliberately -- and `material_changes` reads that tuple rather
    than restating it, so the two cannot disagree."""
    source = inspect.getsource(material_changes)
    assert "MATERIAL" in source
    assert "instructing" in MATERIAL and "deciding" in MATERIAL


# ============================== round trip ==================================

def test_a_commission_survives_the_store_encoding():
    """Persisted as a dict and typed back, the convention `engagement`
    already sets."""
    back = Commission.from_stored(_full().as_dict())
    assert back is not None
    assert back.deciding.capacity is ActingAs.DECIDING
    assert back.instructing.capacity is ActingAs.INSTRUCTING
    assert back.deadline.assessed and back.established


def test_an_unreadable_stored_commission_is_none_rather_than_empty():
    """`None` says nobody recorded one; a blank Commission says one was taken
    and said nothing."""
    assert Commission.from_stored(None) is None
    assert Commission.from_stored("not a record") is None


def test_a_stored_deadline_that_cannot_be_read_says_so():
    broken = Deadline.from_stored({"kind": "nonsense"})
    assert not broken.assessed
    assert "could not be read" in broken.said() or "nothing was recorded" in broken.said()
