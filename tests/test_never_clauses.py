"""The NEVER half of the contract, for the features in S0-S3.

WHY THIS FILE EXISTS
--------------------
`tools/trace.py` T7 reports every NEVER clause with no test declaring
`@refuses`. It stood at seventeen across six features, and five of those
features are in slices already marked DONE. So "DONE" was claiming more than it
could support — a feature is not built because its DOES clauses work; the NEVER
clauses are the half that gets skipped, which is exactly why they are tracked
separately.

WHAT THIS FILE IS NOT
---------------------
It is not a place to park a decorator on the nearest passing test. Four of the
seventeen already had a real test and only lacked the declaration — those got
the decorator where they live, not a copy here. The rest needed a test written,
and one (C4.2) names a capability that IS NOT BUILT, where the honest form is a
tripwire that fails the day it appears rather than an assertion about behaviour
that cannot happen.

A2 is deliberately absent: it is a slice-6 feature, outside this pass.
"""
from __future__ import annotations

import json

import pytest

from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route
from nm.domain.matter import Matter, Provenance
from nm.domain.traceability import refuses
from tests.test_turn_contract import KEY, _Evidence, build

pytestmark = pytest.mark.class_a


# ======================================================= A1: identity =========


@refuses("A1", 1)
@pytest.mark.eval_id("E-010")
def test_a_failed_credential_discloses_nothing_about_which_matters_exist(client):
    """A1: the error must be IDENTICAL whether the advocate has one matter or
    forty.

    A 404 that differs by even a word between "no such matter" and "not yours"
    is an oracle: an attacker enumerates ids and learns which exist. The
    property is byte equality of the response, not merely the same status code.
    """
    made = client.post("/api/turn", json={
        "message": "we act for the plaintiff in O.S. 442/2023 over the land"})
    assert made.status_code == 200
    real_id = made.json()["matter_id"]

    # SOMEONE ELSE, WITH A SESSION OF THEIR OWN.
    #
    # This was a query parameter naming a different advocate, which asked
    # the question at the wrong level entirely: anybody could be anybody, so
    # "the stranger sees the same 404" was true and proved nothing about
    # access. The stranger now has to authenticate before they can ask.
    stranger = client.sign_in("stranger", fresh=True)

    exists = stranger.get(f"/api/matters/{real_id}")
    absent = stranger.get("/api/matters/mat_000000000000")

    assert exists.status_code == absent.status_code == 404
    assert exists.json() == absent.json(), (
        "the response differs between a matter that exists and one that does "
        "not. That difference is an oracle: it discloses WHICH MATTERS EXIST "
        "to someone who cannot read any of them.")


@refuses("A1", 2)
@pytest.mark.eval_id("E-010")
def test_an_anonymous_session_cannot_create_a_matter(client):
    """A1: tenet 4 requires the file to know who may instruct, and tenet 20
    requires a decision to record who decided. An anonymous session satisfies
    neither, so it may not open a file at all — refusing later, at the point of
    advice, would leave client material on an unattributable record."""
    # ANONYMOUS NOW MEANS UNAUTHENTICATED, which is what A1 always said and
    # not what this test used to check.
    #
    # It asserted that a BLANK STRING could not open a matter. True, and far
    # narrower than the clause: `advocate_id` was a query parameter, so every
    # NON-blank string was an accepted identity and this eval passed green
    # while the product had no authentication at all (B-082). The identity
    # now comes from a session, and there is no field left to assert it with.
    client.cookies.clear()

    r = client.post("/api/turn", json={
        "message": "we act for the plaintiff in a possession suit"})
    assert r.status_code == 401, (
        "an unauthenticated session was allowed to open a matter. Nothing "
        "downstream can attribute the instruction or the decision, and "
        "client material is now on an unattributable file.")

    assert client.get("/api/matters").status_code == 401, (
        "an unauthenticated session read a matter list")

    # AND THE CORE REFUSES IT TOO, not only the wire.
    #
    # A mutation proved this half was needed: disabling the domain guard left
    # the served path green, because the wire caught it first. A check that is
    # right at the edge and absent from the engine is one adapter away from
    # being bypassed, and every defect the first external review found lived in
    # exactly that gap.
    for blank in ("", "   ", "\t\n"):
        with pytest.raises(ValueError) as exc:
            Matter.create(advocate_id=blank, title="a matter")
        assert "named advocate" in str(exc.value)

    # A real identity is accepted, and stored stripped, so two spellings of one
    # advocate cannot become two advocates.
    assert Matter.create(advocate_id="  adv_1  ", title="t").advocate_id == "adv_1"


# ======================================================== C1: the account =====

#: Constructions that PRESUPPOSE THEIR ANSWER. A closed list is right here and
#: wrong for reading an advocate's words, and the difference is who wrote the
#: text: this lints prose THIS PRODUCT COMPOSES, where the vocabulary is ours
#: and finite. It is not trying to classify what someone else might say.
LEADING = (
    "i take it", "i assume", "presumably", "so there is no", "so there was no",
    "you didn't", "you did not", "there is no proof", "isn't it", "is it not",
    "surely", "obviously", "of course you", "no doubt",
)


@refuses("C1", 1)
@pytest.mark.eval_id("E-012")
def test_no_question_this_product_asks_is_a_leading_one(tmp_path):
    """C1: *"Is there anything evidencing repayment?"* — not *"I take it there
    is no proof of repayment?"*

    A leading question shapes what comes back and can MANUFACTURE THE GAP IT
    ASSUMED. The advocate then acts on a fact the product invented by asking
    badly, and nothing downstream distinguishes it from one they volunteered.

    Checked over every question the engine can put, gathered by driving it into
    each blocking state rather than by reading the source for string literals —
    a question assembled from parts would pass a source scan and still lead.
    """
    asked: list[str] = []
    for message in (
            "the landlord has issued a quit notice on the shop",
            "a cheque was dishonoured on 3 March",
            "talaq was pronounced and there is a maintenance claim",
    ):
        engine, _ = build(tmp_path / str(abs(hash(message))))
        out = engine.run(TurnInput(advocate_id="adv", message=message))
        asked += [e.text for e in out.answer.elements
                  if e.kind is ElementKind.QUESTION]
        if out.matter is not None:
            follow = engine.run(TurnInput(
                advocate_id="adv", matter_id=out.matter.id,
                message="what is the position"))
            asked += [e.text for e in follow.answer.elements
                      if e.kind is ElementKind.QUESTION]

    assert asked, "the engine was never driven into asking anything"
    for text in asked:
        low = text.lower()
        for lead in LEADING:
            assert lead not in low, (
                f"a question this product asks presupposes its answer "
                f"({lead!r}): {text[:120]!r}. A leading question can "
                f"manufacture the gap it assumed, and the advocate cannot tell "
                f"that fact apart from one they volunteered.")


# ==================================================== C4: thread identity =====


@refuses("C4", 2)
@pytest.mark.eval_id("E-033")
def test_no_path_admits_a_document_fact_without_binding_it_to_a_thread():
    """C4: *never let an unattached document contribute facts, and never
    default it to the first or largest thread.*

    DOCUMENT INGESTION IS NOT BUILT, and this is written as a TRIPWIRE rather
    than as an assertion about behaviour that cannot happen — the same shape as
    `bind-1`, which guards a future corpus rather than a present one.

    Claiming this clause is refused today would be inflation: nothing can
    violate it because nothing can reach it. What this asserts is that the
    condition still holds — no production path constructs a document-sourced
    fact — so the day one appears, this fails and demands the binding be
    written with it, rather than the clause being quietly skipped in the slice
    that finally builds uploads.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "nm"
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name != "Provenance":
                continue
            for kw in node.keywords:
                if kw.arg == "kind" and isinstance(kw.value, ast.Constant) \
                        and kw.value.value == "document":
                    offenders.append(
                        f"{path.relative_to(root.parent)}:{node.lineno}")

    assert not offenders, (
        f"a document-sourced fact is now constructed at {', '.join(offenders)}. "
        f"C4 requires every document to be BOUND to a thread and the binding "
        f"shown so it can be corrected, and it forbids defaulting an unattached "
        f"document to the first or largest thread. Write that binding, then "
        f"replace this tripwire with a test of it.")

    # THE POSITIVE CONTROL. A tripwire that has never been tripped is not
    # known to be connected: the scan above must actually FIND a document
    # fact when one is put in front of it.
    planted = ast.parse(
        'Provenance(kind="document", turn="t", document="x.pdf", page=1)')
    seen = [n for n in ast.walk(planted)
            if isinstance(n, ast.Call)
            and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
            == "Provenance"
            and any(k.arg == "kind" and isinstance(k.value, ast.Constant)
                    and k.value.value == "document" for k in n.keywords)]
    assert seen, (
        "the scan does not recognise a document-sourced fact even when one "
        "is put in front of it, so the tripwire is not connected")

    # And the type still refuses a document fact that cannot be located, which
    # is what makes the binding checkable when it arrives.
    with pytest.raises(ValueError):
        Provenance(kind="document", turn="t1")


# ================================================== E2: the recommendation ====


def _answer(*elements: Element) -> Answer:
    return Answer(route=Route.MATTER, mode=Mode.SHORT_QUESTION,
                  mode_statement="", elements=tuple(elements))


@refuses("E2", 0)
@pytest.mark.eval_id("E-013")
def test_a_survey_of_options_without_a_view_is_not_an_answer(tmp_path):
    """E2: *"Option A and Option B, with pros and cons" is the junior's survey
    and is not advice.*

    The type makes it impossible rather than the prose discouraging it: there
    is no element kind that can hold a survey, and D2 requires a recommendation
    or a blocking question in every turn. Both halves are asserted, because the
    type alone would let an ACTION carry the survey in its text.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff in a possession suit. What are our "
                "options — should we go for a title suit or summary possession?"))

    kinds = {e.kind for e in out.answer.elements}
    assert kinds & {ElementKind.ACTION, ElementKind.QUESTION}, (
        "the turn produced neither a recommendation nor a blocking question")

    # An ACTION that is a menu is a survey wearing a recommendation's kind.
    for e in out.answer.elements:
        if e.kind is not ElementKind.ACTION:
            continue
        low = e.text.lower()
        assert not ("option a" in low and "option b" in low), (
            f"the recommendation is a menu: {e.text[:140]!r}")
        assert "pros and cons" not in low, (
            f"the recommendation surveys rather than advises: {e.text[:140]!r}")


@refuses("E2", 1)
@pytest.mark.eval_id("E-013")
def test_uncertainty_is_stated_and_is_never_a_reason_to_withhold_a_view(tmp_path):
    """E2: *never hedge into non-commitment.*

    The distinction that matters: a DISCLOSURE states what could not be
    established and is required; a hedge withholds the view itself and is
    forbidden. A turn that could not establish something must still say what to
    do, or say plainly what blocks it — never neither.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff in a possession suit over the "
                "Kukatpally land. What should we do?"))

    substantive = [e for e in out.answer.elements
                   if e.kind in (ElementKind.ACTION, ElementKind.QUESTION)]
    assert substantive, (
        "the turn produced only grounds and disclosures. Uncertainty is stated; "
        "it is not a reason to withhold a view.")

    # Disclosures are permitted and are NOT hedges -- they are the honest half.
    # What is refused is a turn whose every element is a caveat.
    assert not all(e.disclosure for e in out.answer.elements), (
        "every element of this turn is a disclosure. That is a hedge into "
        "non-commitment wearing the shape of candour.")


@refuses("E2", 2)
@pytest.mark.eval_id("E-064")
def test_the_first_content_element_is_an_action_or_a_blocking_question(tmp_path):
    """E2: *never lead with background.*

    An advocate reads the first line. A turn that opens with a recital of what
    they just told you has spent that line on them, and the invariant is
    asserted on the ASSEMBLED answer before the byte boundary rather than
    trusted to the composer.
    """
    engine, _ = build(tmp_path)
    for message in (
            "we act for the plaintiff in a possession suit over the land",
            "the landlord has issued a quit notice on the shop",
    ):
        out = engine.run(TurnInput(advocate_id="adv", message=message))
        first = out.answer.elements[0]
        assert first.kind in (ElementKind.ACTION, ElementKind.QUESTION), (
            f"the turn opens with a {first.kind.value}: {first.text[:120]!r}")

    # AND THE TYPE REFUSES IT, which is stronger than an invariant check.
    # An Answer that leads with background cannot be CONSTRUCTED, so no
    # composer -- present or future -- can produce one and no check can be
    # forgotten at a call site.
    with pytest.raises(ValueError) as exc:
        _answer(Element(kind=ElementKind.GROUND, text="Here is the background."),
                Element(kind=ElementKind.ACTION, text="File the suit.",
                        no_deadline_reason="none identified"))
    assert "ACTION" in str(exc.value) and "background" in str(exc.value)


# ====================================== I1: session end and confidentiality ===


@refuses("I1", 2)
@pytest.mark.eval_id("E-019")
def test_an_audit_trail_write_failure_is_never_swallowed(tmp_path):
    """I1: *never swallow an audit-trail write failure.*

    A turn whose metrics could not be written has no record of having happened.
    Swallowing that leaves the advocate advised and the file silent about it,
    which is the one asymmetry this product must never accept — and a broad
    `except` that logs a warning is exactly how a whole feature was once
    suppressed while looking like a model failure.
    """
    store = FileMatterStore(tmp_path, key=KEY)

    class _Unwritable(FileMatterStore):
        def record_metrics(self, metrics: dict) -> None:
            raise OSError("the audit volume is full")

    broken = _Unwritable(tmp_path, key=KEY)
    engine = TurnEngine(store=broken, evidence=_Evidence(),
                        model=build(tmp_path / "m")[0]._model)

    with pytest.raises(OSError):
        engine.run(TurnInput(advocate_id="adv",
                             message="we act for the plaintiff in a suit"))

    # And the ordinary path really does write one, so the test above is not
    # passing because nothing was ever attempted.
    ok = TurnEngine(store=store, evidence=_Evidence(),
                    model=build(tmp_path / "m2")[0]._model)
    out = ok.run(TurnInput(advocate_id="adv",
                           message="we act for the plaintiff in a suit"))
    written = (tmp_path / "metrics" / f"{out.turn_id}.json")
    assert written.exists(), "no audit record was written for a served turn"
    assert json.loads(written.read_text(encoding="utf8"))["turn_id"] == out.turn_id


# ============================ the release gate's own honesty ================


@pytest.mark.eval_id("E-008")
def test_a_recorded_run_cannot_vouch_for_code_it_never_saw(tmp_path, monkeypatch):
    """RG-11 scores "the suite bites" from a RECORDED mutation run, and a
    record with no identity would let a run from three commits ago certify
    today's code.

    That is defect shape S11 exactly, and it is the same argument
    `nm/knowledge/artefact.py` makes about the dense index: the ONLY reason
    that 437MB artefact was knowably unusable is that it shipped an
    `identity.json`. A run that cannot say what it ran against is the same
    artefact wearing a different hat.

    STALE MUST BE `NOT MEASURED`, never PASS and never FAIL. The suite may well
    still bite — nobody has checked against this code, and those are different
    statements.
    """
    import json as _json

    from tools import releasegate

    record = tmp_path / "eval_results.json"
    record.write_text(_json.dumps({
        "mutations": {"caught": 42, "total": 42, "survived": [],
                      "source_fingerprint": "deadbeefdeadbeef"}}), encoding="utf8")
    monkeypatch.setattr(releasegate, "ROOT", tmp_path.parent)
    monkeypatch.setattr(releasegate, "source_fingerprint", lambda *a, **k: "0000")
    (tmp_path.parent / ".nm").mkdir(exist_ok=True)
    (tmp_path.parent / ".nm" / "eval_results.json").write_text(
        record.read_text(encoding="utf8"), encoding="utf8")

    out = releasegate.measure_mutations()
    assert out["available"] is False, (
        "a mutation run recorded against different source was accepted as "
        "evidence about this one")
    assert "never saw" in out["why"] or "fingerprint" in out["why"]

    # And a record made against THIS source is accepted, so the guard is not a
    # blanket refusal that would make RG-11 permanently unmeasurable.
    monkeypatch.setattr(releasegate, "source_fingerprint",
                        lambda *a, **k: "deadbeefdeadbeef")
    ok = releasegate.measure_mutations()
    assert ok["available"] is True and ok["caught"] == 42


@refuses("A2", 3)
@pytest.mark.eval_id("E-063b")
def test_a_matter_that_cannot_be_read_does_not_vanish_from_the_list(tmp_path, client):
    """B-053. A2 forbids rendering an unbuildable board as an EMPTY one. This
    is the same rule for a board that is merely INCOMPLETE — the harder case,
    because it looks right.

    `list_for` skipped an unreadable matter with `continue`, under a comment
    saying "it must not vanish silently either. It is skipped here and reported
    by the caller's board state." The caller received a bare tuple and could
    not tell six matters from seven with one corrupt, so it reported six. The
    seventh, with its deadlines, was simply absent.

    Found by sweeping all 29 exception handlers for this shape, not by anyone
    hitting it.
    """
    from nm.adapters.store.file_store import FileMatterStore
    from nm.edge.projections import matter_list_projection

    store = FileMatterStore(tmp_path, key=KEY)
    good = Matter.create(advocate_id="adv", title="a readable matter")
    store.commit(good, expected_version=None)
    # A file that is on disk and cannot be decoded -- a truncated write, a
    # rotated key, a corrupted volume. All of them look like this.
    (tmp_path / "matters" / "mat_corrupted.nm").write_bytes(b"not decryptable")

    listed = FileMatterStore(tmp_path, key=KEY).list_for("adv")
    assert [m.id for m in listed] == [good.id], "the readable matter was lost"
    assert not listed.complete
    assert "mat_corrupted" in listed.unreadable, (
        "a matter that could not be read vanished from the list. The advocate "
        "is told they have one matter and they have two.")

    board = matter_list_projection(listed)
    assert board["state"] == "incomplete", (
        f"the board reports {board['state']!r} while a matter is missing from "
        f"it. `row_count` says one either way.")
    assert "mat_corrupted" in (board["unreadable_reason"] or "")


@refuses("A2", 0)
@pytest.mark.eval_id("E-012")
def test_the_invitation_to_brief_is_one_line_and_not_a_field_set(client):
    """A2: *Never a form. An invitation to brief is one line, not a field set.*

    An advocate opens with a sentence, not a schema. A product that answers
    "hello" with eight labelled inputs has told them it wants data entry, and
    the thing it most needs — the uninterrupted account — is the thing a form
    makes impossible to give.
    """
    r = client.post("/api/turn", json={"advocate_id": "adv", "message": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "non_matter", "a greeting is not a matter"

    text = " ".join(e["text"] for e in body["elements"])
    assert len(body["elements"]) == 1, (
        f"the invitation is {len(body['elements'])} elements. It is one line.")
    assert len(text.split(".")) <= 3, f"the invitation is a paragraph: {text!r}"
    for form in ("please enter", "field", "fill in", "select one",
                 "1.", "2.", "a)", "b)", "*"):
        assert form not in text.lower(), (
            f"the invitation reads as a form ({form!r}): {text!r}")


@refuses("A2", 1)
@pytest.mark.eval_id("E-063")
def test_neither_board_carries_analysis(client):
    """A2: *Never analysis on either board.* Not the theory, not proof gaps,
    not reasoning — those live in the case summary and the answer.

    The test for status-versus-analysis is whether the line is a CONCLUSION.
    A board is what the advocate scans to decide which file to open; a
    conclusion on it is one they will act on without the reasoning that
    produced it.
    """

    made = client.post("/api/turn", json={
        "advocate_id": "adv",
        "message": "we act for the plaintiff in a possession suit over the land"})
    assert made.status_code == 200
    matter_id = made.json()["matter_id"]

    board = client.get(f"/api/matters/{matter_id}",
                       params={"advocate_id": "adv"}).json()
    listing = client.get("/api/matters", params={"advocate_id": "adv"}).json()

    # STATUS FIELDS ONLY. A key outside this set is either analysis or a new
    # status field somebody must justify — and the failure names it either way.
    # STATUS FIELDS. `next_deadline_status` and `passed_deadlines` were added
    # by D3 and this test asked the right question about them: a date and its
    # status are STATUS -- what the advocate scans to choose a file -- while
    # theory, proof gaps and reasoning are the analysis A2 keeps off the board.
    # A passed deadline is on the board precisely because A2.5 requires it to
    # be, and it carries its consequence rather than an argument about it.
    thread_keys = {"thread_id", "thread", "our_client_is", "side", "against",
                   "forum", "stage", "next_deadline", "next_deadline_status",
                   "passed_deadlines", "loud", "conflict", "deferred_reason"}
    for row in board["threads"]:
        extra = set(row) - thread_keys
        assert not extra, (
            f"the thread board carries {sorted(extra)}. A board is what the "
            f"advocate scans to choose a file; analysis on it is a conclusion "
            f"they will act on without the reasoning behind it.")

    # `next_deadline_status` is a STATUS field and not analysis: it says which
    # of the three the null means -- nobody assessed a register, or one was
    # assessed and this matter has no dated deadline. A null alone reads as
    # the second while meaning the first, which is what it did.
    matter_keys = {"matter_id", "matter", "client", "threads", "next_deadline",
                   "next_deadline_status", "blocked", "last_touched"}
    for row in listing["matters"]:
        extra = set(row) - matter_keys
        assert not extra, f"the matter list carries {sorted(extra)}"

    # And no free text on either board reads as reasoning.
    blob = " ".join(str(v) for row in board["threads"] for v in row.values()
                    if isinstance(v, str))
    for reasoning in ("because", "therefore", "it follows", "the theory",
                      "we should argue", "likely to succeed"):
        assert reasoning not in blob.lower(), (
            f"the board reasons ({reasoning!r}): {blob[:140]!r}")


@refuses("A2", 5)
@pytest.mark.eval_id("E-046")
def test_a_passed_deadline_is_on_the_board_and_not_among_the_upcoming():
    """A2.5, which was DECLARED as awaiting D3 and is now owed.

    Two different mistakes, and A2 forbids both. Dropping a passed deadline
    tells the advocate there was never one. Filing it under what is still
    upcoming buries the thing they can no longer do among the things they
    still can — and they scan the second list for work.

    `_thread_row` carried `"next_deadline": None` hard-coded until D3, so this
    clause was a rule about a field that never held anything. That is why it
    was declared as awaiting rather than tested against an empty value.
    """
    from datetime import date, timedelta

    from nm.core.deadlines import Deadline, DeadlineKind, DeadlineStatus
    from nm.domain.matter import Thread
    from nm.edge.projections import board_projection

    today = date(2026, 8, 31)
    thread = Thread.create("the possession suit")
    matter = Matter.create(advocate_id="adv", title="m").with_thread(thread)

    def _d(days, action):
        return Deadline(thread=thread.id, kind=DeadlineKind.LIMITATION,
                        source="Limitation Act, 1963 Article 65",
                        action=action, owner="the advocate",
                        consequence="the claim is barred",
                        on=today + timedelta(days=days))

    gone = _d(-240, "apply under s.5 to condone the delay")
    soon = _d(12, "file the suit")

    board = board_projection(matter, (gone, soon), today)
    row = board["threads"][0]

    assert row["next_deadline"] == soon.on.isoformat(), (
        "the nearest UPCOMING deadline is not shown")
    assert row["next_deadline_status"] == DeadlineStatus.NEAR.value
    assert row["next_deadline"] != gone.on.isoformat(), (
        "a deadline eight months gone is being shown as what comes next")

    assert len(row["passed_deadlines"]) == 1, (
        "the passed deadline was dropped from the board. The advocate is told "
        "there was never one, and the relief-from-delay application with it.")
    passed_row = row["passed_deadlines"][0]
    assert passed_row["days_ago"] == 240
    assert passed_row["consequence"], (
        "a passed deadline with no consequence tells the advocate nothing they "
        "can act on")
    assert "condone" in passed_row["action"]
