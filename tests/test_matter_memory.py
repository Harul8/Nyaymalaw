"""The matter memory. E-035, E-036.

WHAT THESE REFUSE
-----------------
Six golden scenarios run end to end found the product asking *"whose side are
we on?"* on consecutive turns of GS-08 after the advocate had answered it. Two
separate causes: the posture read saw only the latest message, and six
persisted fields were being dropped on every read.

Both were fixed, and neither fix was general. The general defect is that EVERY
prompt in this product was built from `turn.message` alone, so the product
could only ever know what had been said in the last thirty seconds — and
nothing in a green suite could tell you that, because every unit test sends one
message.

So the invariants here are stated as RULES rather than as the scenario:

  E-036  Every model call a turn makes receives the file. Not the posture read
         — every one. This is written so that a prompt added in a later slice
         is caught the day it is added, which is the only kind of check that
         survives a codebase growing.

  E-035  A question that has been answered is never asked again, and one asked
         twice is not put a third time in the same words.

WHY THE FIRST ONE IS WRITTEN AGAINST A RECORDING ADAPTER
---------------------------------------------------------
A test that reads the source for `turn.message` would pass the day someone
assigns it to a local first. Recording what the model actually RECEIVED is the
property; everything else is a proxy for it.
"""
from __future__ import annotations

import pathlib
from datetime import date

import pytest

from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput
from nm.domain import summary as matter_memory
from nm.domain.answer import ElementKind
from nm.domain.matter import (
    AskedQuestion,
    Basis,
    Matter,
    Posture,
    Role,
    Side,
    Thread,
)
from nm.domain.traceability import refuses
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a


class _Recorder:
    """A model adapter that answers normally and keeps every prompt it saw.

    Wraps the scripted adapter rather than replacing it, so the turn still
    behaves — a double that returns nothing would make the engine take its
    failure path and the test would prove nothing about the ordinary one.
    """

    def __init__(self, responses=None):
        self._inner = ScriptedModelAdapter(
            _model_config(),
            responses=responses or {
                "__default__": "File the summary suit and diarise the window."})
        self.prompts: list = []

    def complete(self, prompt, tier, **kw):
        self.prompts.append(prompt)
        return self._inner.complete(prompt, tier, **kw)

    def structured(self, prompt, schema, tier, **kw):
        self.prompts.append(prompt)
        return self._inner.structured(prompt, schema, tier, **kw)

    def embed(self, texts, **kw):
        return self._inner.embed(texts, **kw)


class _RecordingEvidence(_Evidence):
    """Answers normally and keeps every EvidenceNeed it was handed.

    The account reaches retrieval through the NEED, not through a prompt,
    so a test that records only prompts checks two of the three paths and
    calls it "every model call". This is the third.
    """

    def __init__(self, result=None):
        super().__init__(result)
        self.needs: list = []

    def fetch(self, need):
        self.needs.append(need)
        return super().fetch(need)


def _engine(tmp_path, model=None, evidence=None):
    store = FileMatterStore(tmp_path, key=KEY)
    return TurnEngine(store=store, evidence=evidence or _Evidence(),
                      model=model or _Recorder()), store


# ============================================== E-036: the file reaches all ===


@refuses("C1", 0)
@pytest.mark.eval_id("E-036")
def test_every_model_call_in_a_turn_receives_the_file(tmp_path):
    """THE RULE: no prompt is built from the latest message alone.

    Stated over ALL prompts rather than over the two that exist today, so a
    third one added in a later slice fails this the day it is written. That is
    the difference between fixing the defect and fixing the class of defect.
    """
    recorder = _Recorder()
    evidence = _RecordingEvidence()
    engine, _ = _engine(tmp_path, model=recorder, evidence=evidence)

    first = engine.run(TurnInput(
        advocate_id="adv",
        message="We act for the plaintiff in O.S. 442/2023, a suit for "
                "possession of the Kukatpally land against the builder."))
    assert first.matter is not None

    recorder.prompts.clear()
    evidence.needs.clear()
    second = engine.run(TurnInput(
        advocate_id="adv", matter_id=first.matter.id,
        message="And what is the limitation on that?"))
    assert second.matter is not None
    assert recorder.prompts, "the turn made no model call at all"

    # A marker the SECOND message does not contain. If a prompt carries it, it
    # was built from the file; if none does, the product has forgotten the
    # matter between turns.
    for prompt in recorder.prompts:
        blob = f"{prompt.system}\n{prompt.user}"
        assert "Kukatpally" in blob or "plaintiff" in blob, (
            "a model call was built without the matter file. Every prompt in a "
            "turn must carry what the advocate has already said, or the product "
            "re-asks what it was told and re-derives what it already knew.\n\n"
            f"prompt was:\n{prompt.user[:400]}")

    # AND RETRIEVAL. The account reaches it through the EvidenceNeed rather
    # than through a prompt, so checking prompts alone would leave the one
    # path that produced the measured defect unchecked: an advocate names
    # the Act on turn 1, asks "and the limitation?" on turn 4, and is told
    # there is a corpus gap for a provision already retrieved for them.
    assert evidence.needs, "the turn retrieved nothing at all"
    for need in evidence.needs:
        assert "Kukatpally" in need.account, (
            "a retrieval was built from the latest message alone. The need "
            "must carry the account, or the product reports corpus gaps for "
            "provisions the advocate named on an earlier turn.")


@pytest.mark.eval_id("E-036")
def test_the_summary_holds_nothing_the_matter_does_not(tmp_path):
    """A PROJECTION, not a second store.

    A summary that can disagree with the file is worse than no summary: the
    advocate cannot tell which one is stale. The check is that rebuilding it
    from the matter is deterministic and that every established line traces to
    something the matter holds.
    """
    matter = Matter.create(advocate_id="adv", title="Kukatpally")
    thread = Thread.create(
        "Kukatpally possession",
        identifiers={"case_number": "OS442/2023"},
        posture=Posture(role=Role.PLAINTIFF, basis=Basis.STATED,
                        opponent="the builder"))
    matter = matter.with_thread(thread)

    one = matter_memory.build(matter)
    two = matter_memory.build(matter)
    assert one == two, "the summary is not a pure function of the matter"

    haystack = (matter.title + " " + thread.label + " "
                + " ".join(matter.threads[0].identifiers.values())
                + " plaintiff moving stated the builder")
    for line in one.established:
        for token in ("OS442/2023", "plaintiff", "Kukatpally", "builder"):
            if token in line:
                assert token in haystack, (
                    f"the summary asserts {token!r}, which the matter does not "
                    f"hold. A projection that can invent is a second store.")


@pytest.mark.eval_id("E-036")
def test_a_summary_that_cannot_be_built_is_an_explicit_failure():
    """An empty summary would make the product re-ask EVERYTHING it was told.

    Defect shape S1 with the whole conversation as the blast radius, so the
    unbuildable case is a named state rather than an empty one.
    """
    out = matter_memory.unbuildable("the store could not be read")
    assert out["state"] == "unbuildable"
    assert "could not be read" in out["reason"]
    assert out["established"] == []


@pytest.mark.eval_id("E-036")
def test_a_long_account_is_trimmed_from_the_front_never_the_back():
    """The advocate's LATEST instruction is the one that decides this turn.

    Trimming the tail would silently discard the thing they just said, which is
    the failure mode that looks most like the product ignoring them.
    """
    matter = Matter.create(advocate_id="adv", title="long")
    thread = Thread.create("t")
    matter = matter.with_thread(thread)
    for i in range(400):
        f = _fact(f"turn {i}: something happened, filler filler filler")
        matter = matter.with_fact(f)
        thread = matter.threads[0]
        matter = matter.with_thread(
            thread.__class__(**{**thread.__dict__,
                                "chronology": thread.chronology + (f.id,)}))
    matter = matter.with_fact(_fact("turn LAST: the notice was served today"))

    built = matter_memory.build(matter)
    assert len(built.account) <= matter_memory.ACCOUNT_BUDGET + 40
    assert "turn LAST" in built.account, (
        "the most recent instruction was trimmed away. The account is trimmed "
        "from the FRONT: what the advocate just said decides this turn.")
    assert "trimmed" in built.account.split("\n")[0]


def _fact(statement: str):
    from nm.domain.matter import Fact, Provenance
    return Fact.create(statement=statement,
                       provenance=Provenance(kind="advocate_statement",
                                             turn="t"))


# ========================================== E-035: never ask twice ============


@refuses("C3", 0)
@pytest.mark.eval_id("E-035")
def test_a_question_the_advocate_answered_is_never_asked_again(tmp_path):
    """THE RULE, over the ledger rather than over one gate.

    The closing test is general: a gate stops firing exactly when the condition
    it names has cleared, and that is what "answered" means. Closing questions
    one by one at each call site is how a question survives its own answer.
    """
    engine, _ = _engine(tmp_path)

    one = engine.run(TurnInput(
        advocate_id="adv",
        message="A quit notice was issued on the Kukatpally shop last month."))
    assert one.matter is not None
    assert one.answer.blocked, "posture is unresolved, so the turn must block"
    standing = one.matter.open_question("G-POSTURE", one.matter.threads[0].id)
    assert standing is not None, "the blocking question was not recorded"
    assert standing.times_asked == 1

    two = engine.run(TurnInput(
        advocate_id="adv", matter_id=one.matter.id,
        message="We act for the respondent."))
    assert two.matter is not None
    assert two.matter.open_question("G-POSTURE", two.matter.threads[0].id) is None, (
        "the posture question is still open after the advocate answered it. "
        "It will be asked again, and being asked something you have already "
        "answered tells you your instructions were not recorded.")
    assert [q.answered_by for q in two.matter.asked if q.gate == "G-POSTURE"] \
        == [two.turn_id]
    assert not any(e.kind is ElementKind.QUESTION and e.gate == "G-POSTURE"
                   for e in two.answer.elements)


@pytest.mark.eval_id("E-035")
def test_a_question_asked_twice_is_not_put_a_third_time_in_the_same_words(tmp_path):
    """An advocate who has passed over a question twice is telling you something.

    Usually that they read it as rhetorical. Repeating it identically is the
    product failing to listen, so it stops being a question and becomes a
    stated blocker with the answer spelled out.
    """
    engine, _ = _engine(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="A quit notice was issued on the Kukatpally shop."))
    asks = []
    for _ in range(3):
        assert out.matter is not None
        asks.append(next(e.text for e in out.answer.elements
                         if e.kind is ElementKind.QUESTION))
        out = engine.run(TurnInput(
            advocate_id="adv", matter_id=out.matter.id,
            message="What is the position on the shop?"))

    assert asks[0] == asks[1], "the second ask may legitimately repeat"
    assert asks[2] != asks[1], (
        "the same question was put a third time in the same words. Two "
        "unanswered asks is the advocate telling you the question is not "
        "landing.")
    assert "asked twice" in asks[2]
    q = out.matter.open_question("G-POSTURE", out.matter.threads[0].id)
    assert q is not None and q.times_asked >= 3 and q.ignored


@pytest.mark.eval_id("E-035")
def test_the_ask_ledger_survives_a_restart(tmp_path):
    """E-011's property, applied to the ledger.

    A question that does not survive a restart is a question the advocate gets
    asked again in the next session — which is the same defect wearing a
    different hat, and it is exactly how `client_described_as` was lost.
    """
    engine, _ = _engine(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="A quit notice was issued on the Kukatpally shop."))
    assert out.matter is not None

    # A NEW store object over the same directory: the restart.
    reloaded = FileMatterStore(tmp_path, key=KEY).load(out.matter.id)
    assert reloaded is not None
    q = reloaded.open_question("G-POSTURE", reloaded.threads[0].id)
    assert q is not None and q.text and q.asked_on == out.turn_id


@pytest.mark.eval_id("E-035")
def test_the_same_question_bumps_its_count_rather_than_adding_a_row():
    """The file shows a thing was asked three times, not three identical rows.

    The count is what makes "asked and ignored" a state the product can act on.
    """
    m = Matter.create(advocate_id="adv", title="t")
    m = m.asking("G-POSTURE", "whose side?", "turn_1", "thr_1")
    m = m.asking("G-POSTURE", "whose side?", "turn_2", "thr_1")
    assert len(m.asked) == 1
    assert m.asked[0].times_asked == 2
    assert m.asked[0].asked_on == "turn_2"
    assert m.asked[0].ignored

    # A DIFFERENT THREAD IS A DIFFERENT QUESTION. Threads are separate
    # disputes; answering one says nothing about the other.
    m = m.asking("G-POSTURE", "whose side?", "turn_2", "thr_2")
    assert len(m.asked) == 2


@pytest.mark.eval_id("E-035")
def test_only_the_gates_that_stopped_firing_are_marked_answered():
    """A gate still firing has NOT been answered, whatever else cleared."""
    m = Matter.create(advocate_id="adv", title="t")
    m = m.asking("G-POSTURE", "whose side?", "turn_1", "thr_1")
    m = m.asking("G-THREAD", "same dispute?", "turn_1", "thr_1")

    m = m.answered(frozenset({"G-POSTURE"}), "turn_2")
    assert m.open_question("G-POSTURE", "thr_1") is not None, (
        "a gate that fired again was marked answered")
    assert m.open_question("G-THREAD", "thr_1") is None


@pytest.mark.eval_id("E-035")
def test_an_asked_question_carries_three_states_not_two():
    """open / answered / asked-and-ignored.

    Two states would make "we never asked" and "we asked and were ignored"
    indistinguishable, and those call for different next moves.
    """
    fresh = AskedQuestion(gate="G-POSTURE", text="?", asked_on="t1")
    twice = AskedQuestion(gate="G-POSTURE", text="?", asked_on="t2",
                          times_asked=2)
    done = AskedQuestion(gate="G-POSTURE", text="?", asked_on="t1",
                         answered_by="t2", times_asked=2)
    assert (fresh.open, fresh.ignored) == (True, False)
    assert (twice.open, twice.ignored) == (True, True)
    assert (done.open, done.ignored) == (False, False)


# ================================= the Act named on an earlier turn ==========


@pytest.mark.eval_id("E-036")
def test_an_act_named_earlier_is_carried_by_exact_title_only(tmp_path):
    """CARRIED, NOT INFERRED — and the distinction is the safety argument.

    Keyword-scoring the accumulated account would be the outvoting defect at
    scale: scoring reads the whole text, so the more the advocate says the more
    likely the wrong Act wins, and an account is every sentence they have ever
    said. An exact title is their instruction. A keyword hit across four turns
    is a guess with more evidence behind it than any single turn could supply.
    """
    from nm.knowledge.manifest import ActBasis, Manifest

    manifest = Manifest.load(
        pathlib.Path(__file__).resolve().parents[1] / "spec" / "manifest.yaml")
    on = date(2025, 1, 1)

    # An Act NAMED on an earlier turn is carried, and disclosed.
    carried = manifest.resolve("what is the limitation on that?", on=on,
                               account="a suit under the Specific Relief Act")
    assert carried.entry is not None
    assert carried.basis is ActBasis.NAMED
    assert carried.carried is True
    assert carried.must_disclose, "a carried Act is stated, never assumed"
    assert "earlier" in carried.note()

    # KEYWORDS IN THE ACCOUNT CARRY NOTHING. The account below is full of
    # possession vocabulary and names no Act; nothing may be resolved from it.
    from_keywords = manifest.resolve(
        "what now?", on=on,
        account=("the client was dispossessed of the land, possession was "
                 "taken, there is a dispute over possession of the property"))
    assert from_keywords.entry is None, (
        "an Act was carried forward on KEYWORDS. Only an exact title may "
        "carry: common words run through every Indian statute, so overlap "
        "across a whole account is a wrong signal, not a weak one.")

    # THIS TURN ALWAYS WINS. An Act named now is not overridden by one named
    # before, or the advocate could never change subject.
    now = manifest.resolve("section 65 of the Limitation Act", on=on,
                           account="a suit under the Specific Relief Act")
    assert now.basis is ActBasis.NAMED and not now.carried
    assert "Limitation" in now.entry.act_name


@pytest.mark.eval_id("E-036")
def test_a_narrative_takes_the_latest_provision_and_a_question_the_first():
    """IN A NARRATIVE, THE OPERATIVE REFERENCE IS THE LATEST ONE.

    A thread that opened on one provision and moved to another would otherwise
    keep answering about the first, forever — and be correct about a provision
    nobody asked about.
    """
    from nm.domain.citation import last_wanted_section, wanted_section

    account = ("turn 1: this is about section 6 of the Specific Relief Act\n"
               "turn 4: now I am asking about section 53A")
    assert wanted_section(account) == "6"
    assert last_wanted_section(account) == "53A"

    # The guards travel with it: a case number is not a section, in either.
    assert wanted_section("we act in O.S. 442/2023") is None
    assert last_wanted_section("we act in O.S. 442/2023") is None

    # A Schedule Article named after a section outranks it, and vice versa.
    assert last_wanted_section("section 6 ... later, Article 65") == "Article_65"
    assert last_wanted_section("Article 65 ... later, section 6") == "6"


# ============ the product may not read its own output back as instruction ====


@refuses("C3", 1)
@pytest.mark.eval_id("E-030", "E-036")
def test_our_own_question_can_never_settle_a_posture():
    """THE DEFECT THE MEMORY ITSELF INTRODUCED, and the rule that refuses it.

    The blocking question contains the words "do we act for the party moving,
    or the party answering?" The memory rightly puts outstanding questions in
    the prompt — a model that cannot see what is already asked will ask it
    again. But the verbatim guard was checking the span against everything the
    model had been SHOWN, so the extractor quoted our own question back and the
    product settled a posture nobody had stated. Every other guard passed.

    The rule, stated without naming the question or the field: A VERBATIM GUARD
    CHECKS AGAINST WHAT THE PERSON WROTE, NEVER AGAINST WHAT WE COMPOSED. It is
    the same rule as `test_composed_text_is_not_a_citation`, one layer up.
    """
    from nm.core.posture import interpret

    ours = ("Whose side are we on in this matter — do we act for the party "
            "moving, or the party answering?")
    # SLICED OUT OF OUR OWN QUESTION rather than retyped, so this test cannot
    # drift into checking a span the product never actually emits.
    lifted = ours[ours.index("we act for the party moving"):][:27]
    model_said = {
        "states_client": True,
        "role": "plaintiff",
        "role_basis": "stated",
        "client_described_as": "",
        "quoted": lifted,
    }

    # The advocate said nothing about sides on this turn or any earlier one.
    settled = interpret("What is the position on the shop?", model_said,
                        advocate_words="A quit notice was issued last month.")
    assert not settled.settles_role, (
        "a posture was settled from THIS PRODUCT'S OWN words. Widening a prompt "
        "must never widen the guard: the span has to appear in something the "
        "advocate wrote.")
    assert settled.refused and "advocate wrote" in settled.refused

    # And the same span, actually written by the advocate, IS accepted -- the
    # guard must not have become a blanket refusal.
    real = interpret(lifted, model_said)
    assert real.settles_role and real.role is Role.PLAINTIFF


# ============================== the file is auditable on the wire ============


@pytest.mark.eval_id("E-036")
def test_the_file_is_served_so_the_advocate_can_audit_it(client):
    """E-014: every guard is reached by a test that drives the SERVED PATH.

    A memory only a prompt can read is a memory nobody can audit, and the
    advocate finds out it was wrong by being advised from it.
    """
    turn = client.post("/api/turn", json={
        "advocate_id": "adv",
        "message": "We act for the plaintiff in O.S. 442/2023 over the "
                   "Kukatpally land.",
    })
    assert turn.status_code == 200, turn.text
    matter_id = turn.json()["matter_id"]

    got = client.get(f"/api/matters/{matter_id}/summary",
                     params={"advocate_id": "adv"})
    assert got.status_code == 200
    body = got.json()
    assert body["state"] == "ok"
    blob = " ".join(body["established"])
    assert "OS442/2023" in blob or "case number" in blob
    assert "plaintiff" in blob

    # ANOTHER ADVOCATE'S MATTER DISCLOSES NOTHING -- the same 404 whether it
    # does not exist or is not theirs.
    # A SECOND ADVOCATE, WITH A SESSION.
    #
    # This named a different `advocate_id` in the query string and
    # asserted a 404. True, and empty: naming one was all it took to be
    # one, so the test passed while any caller could read any matter
    # (B-082). The other advocate now has to authenticate.
    other = client.sign_in("other", fresh=True)
    assert other.get(
        f"/api/matters/{matter_id}/summary").status_code == 404


# ========== what the six-scenario run found, stated as rules =================


@refuses("C3", 2)
@pytest.mark.eval_id("E-030")
def test_a_descriptor_that_names_nobody_is_not_recorded():
    """B-037. `our client` identifies no one, so recording it is worse than
    recording nothing: the narrowed question became "You act for the our
    client. Did they file...?" -- gibberish, and unanswerable.

    The rule is GRAMMAR, not a vocabulary list. A phrase whose only content
    word is a noun of representation names nobody, however it is inflected.
    """
    from nm.core.posture import interpret, names_nobody

    for junk in ("our client", "my client", "the client", "client",
                 "the party", "his client", "them"):
        assert names_nobody(junk), f"{junk!r} identifies nobody and was accepted"
    for real in ("the workman", "the payee", "the second respondent",
                 "the wife", "the corporate debtor"):
        assert not names_nobody(real), f"{real!r} identifies someone and was rejected"

    out = interpret("we act for our client in this", {
        "states_client": True, "role": "not_stated", "role_basis": "stated",
        "client_described_as": "our client", "quoted": "we act for our client"})
    assert out.client_described_as is None, (
        "a descriptor naming nobody was recorded. It then blocks the real one, "
        "because a descriptor used to be write-once.")


@pytest.mark.eval_id("E-030")
def test_a_better_descriptor_replaces_a_weaker_one(tmp_path):
    """B-038. Write-once meant the FIRST descriptor won forever.

    Monotonic enrichment is right for the ROLE -- a stated posture silently
    flipping is the turn-5 reversal, and by then the advocate has acted on it.
    A descriptor is not a decision anyone acts on; it is a label, and a later
    more specific one is better information.
    """
    engine, _ = _engine(tmp_path)
    one = engine.run(TurnInput(
        advocate_id="adv",
        message="there is a dispute at the shop and it concerns our client"))
    assert one.matter is not None

    two = engine.run(TurnInput(
        advocate_id="adv", matter_id=one.matter.id,
        message="we act for the tenant"))
    assert two.matter is not None
    described = two.matter.threads[0].posture.client_described_as
    assert described != "our client", (
        "a descriptor naming nobody survived and blocked the real one")


@refuses("C3", 3)
@pytest.mark.eval_id("E-030", "E-036")
def test_the_role_read_never_fires_without_first_person_representation():
    """B-039's trigger, and the guard that keeps it inside C3.

    The role read runs once the advocate has spoken about their OWN side. C3's
    counterexample -- *the landlord has issued a quit notice to the tenant* --
    names two parties and speaks of neither in the first person, so it does not
    fire, and the reinstatement defect stays impossible.
    """
    from nm.core.posture import speaks_of_the_representation

    assert not speaks_of_the_representation(
        "the landlord has issued a quit notice to the tenant")
    assert not speaks_of_the_representation("a fitter was dismissed last month")
    assert not speaks_of_the_representation(
        "a cheque was dishonoured on 3 March")

    for stated in ("we act for the workman",
                   "we want to file a title suit over the strip",
                   "a neighbour grabbed my client's land",
                   "appearing on behalf of the second respondent"):
        assert speaks_of_the_representation(stated), (
            f"{stated!r} states the advocate's own side and did not trigger the "
            f"role read, so the gate would block every later turn")


@pytest.mark.eval_id("E-030")
def test_an_out_of_vocabulary_role_is_blanked_not_coerced():
    """B-040's third guard. The enum is in the schema AND named in the prompt,
    and this is the last line because the first two are advisory on at least
    one provider: `strict` is off, and `claimant` -- outside an eleven-value
    enum -- reached the core once already.
    """
    from nm.core.posture import interpret_role

    role, why = interpret_role({"role": "claimant", "why": "the workman"})
    assert role is None, "an invented role was accepted"
    assert "not a role this product knows" in why

    role, why = interpret_role({"role": "cannot_tell", "why": "no proceeding named"})
    assert role is None and "no proceeding" in why

    role, _ = interpret_role({"role": "petitioner", "why": "she filed"})
    assert role is Role.PETITIONER


@pytest.mark.eval_id("E-030", "E-034")
def test_nothing_is_computed_behind_a_closed_posture_gate(tmp_path):
    """The gate's whole economic argument, and it now holds on the wire.

    A blocked turn legitimately spends the cheap extraction calls that SETTLE
    the gate and must spend nothing else. Before the fixes a blocked turn was
    also paying for a recommendation it then discarded.
    """
    recorder = _Recorder()
    evidence = _RecordingEvidence()
    engine, _ = _engine(tmp_path, model=recorder, evidence=evidence)

    out = engine.run(TurnInput(
        advocate_id="adv", message="a cheque was dishonoured on 3 March"))
    assert out.answer.blocked, "posture is unresolved, so the step must be refused"
    # E-034 as sharpened: nothing SIDE-DEPENDENT. A provision lookup is the
    # legislature's words and the same for either party, so it runs. The
    # AUTHORITY set does not, because which judgments come back is a function
    # of how the question was framed.
    assert not any(n.want_authority for n in evidence.needs), (
        "an authority set was assembled behind a closed posture gate")
    assert not any(e.kind is ElementKind.ACTION for e in out.answer.elements), (
        "a directive step was produced behind a closed gate")
    # Only the reads that settle the gate. Counted separately from derivation
    # for exactly this reason.
    assert out.metrics.llm_calls == out.metrics.settling_reads, (
        f"a blocked turn made {out.metrics.llm_calls} model call(s) of which "
        f"only {out.metrics.settling_reads} were ADMIT-phase reads. The rest "
        f"were derivation behind a closed gate, and were paid for. "
        f"`settling_reads` is what establishes the FILE and is not "
        f"side-dependent: the posture, the thread binding, the date chart. "
        f"Asserting against `posture_reads` alone had to be widened the moment "
        f"a second such read existed, which is why the property is on the "
        f"metrics rather than spelled out at each call site.")


@pytest.mark.eval_id("E-030", "E-036")
def test_every_declared_schema_is_satisfiable_when_nothing_was_established():
    """B-042, stated as the rule rather than as the field that broke.

    `role` could be `not_stated` — the ordinary case — and `role_basis` was a
    required enum of `[stated, inferred]` with no member meaning "there is no
    role, so there is no basis". A model reporting the ordinary case had NO
    legal value to return.

    Nobody noticed because the enum was not enforced on the path that ships.
    The moment it was, the posture read started failing validation on most
    messages, and it fails open to "nothing was stated" — indistinguishable
    from the advocate having said nothing. Defect shape S1, in a schema.

    THE RULE: NOTHING-ESTABLISHED IS A STATE EVERY SCHEMA MUST BE ABLE TO
    EXPRESS. A schema that can only describe success makes the failure look
    like success, which is the most repeated defect in this project.

    Derived from the declared schemas rather than a list of them, so a schema
    added in a later slice is covered the day it is written.
    """
    from nm.core import posture as reader
    from nm.ports.model import SchemaViolation, require_schema

    schemas = {n: getattr(reader, n) for n in dir(reader)
               if n.endswith("_SCHEMA")
               and isinstance(getattr(reader, n), dict)}
    assert schemas, "no schemas were discovered — this test would pass vacuously"

    for name, schema in schemas.items():
        empty = {}
        for field, spec in schema.get("properties", {}).items():
            if field not in schema.get("required", []):
                continue
            if "enum" in spec:
                # The "nothing established" member, whatever it is called.
                escape = next((v for v in spec["enum"]
                               if v in ("not_stated", "cannot_tell", "unknown",
                                        "not_assessed", "not_checked")), None)
                assert escape is not None, (
                    f"{name}.{field} is a required enum {spec['enum']} with no "
                    f"member for 'nothing was established'. A model reporting "
                    f"the ordinary case has no legal value to return, and what "
                    f"it does return fails validation — which fails open, and "
                    f"then a check that could not run is indistinguishable from "
                    f"one that passed.")
                empty[field] = escape
            elif spec.get("type") == "string":
                empty[field] = ""
            elif spec.get("type") == "boolean":
                empty[field] = False
            elif spec.get("type") in ("integer", "number"):
                empty[field] = 0
            elif spec.get("type") == "array":
                empty[field] = []
            else:
                empty[field] = {}

        try:
            require_schema(empty, schema)
        except SchemaViolation as exc:
            raise AssertionError(
                f"{name} cannot express 'nothing was established': {exc}") from exc


@refuses("C3", 4)
@pytest.mark.eval_id("E-030")
def test_an_account_of_events_never_settles_a_posture_on_the_engine(tmp_path):
    """C3'S COUNTEREXAMPLE, DRIVEN THROUGH THE ENGINE rather than the reader.

    The unit test of `interpret()` cannot see this: the decision of WHEN to ask
    the role question lives in the engine, and widening that trigger would
    defeat C3 without touching the reader at all. A mutation proved exactly
    that — it flipped the trigger to always-fire and every reader test stayed
    green.

    *The landlord has issued a quit notice to the tenant* names two parties and
    says which side is ours about neither. The measured defect there told an
    employer he could claim reinstatement from himself, with every citation
    correct and the whole analysis on the wrong side.
    """
    engine, _ = _engine(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="the landlord has issued a quit notice to the tenant"))

    assert out.matter is not None
    assert out.answer.blocked, (
        "a posture was settled from an account of events. The advocate said "
        "nothing about which side is theirs, and naming two parties is not "
        "naming a client.")
    assert out.answer.blocked_reason.startswith("G-POSTURE")
    assert out.matter.threads[0].posture.role is Role.UNKNOWN
    assert out.matter.threads[0].posture.side is Side.UNKNOWN


@pytest.mark.eval_id("E-023")
def test_an_inferred_act_is_disclosed_even_when_it_finds_nothing():
    """B-043. THE GUESS MATTERS MOST WHEN IT PRODUCED NOTHING.

    The note naming what was inferred from — and what else matched — was
    attached to the one return that produced findings. Every NOT_HELD and
    HELD_NOT_FOUND return dropped it, so a WRONG inference that found nothing
    was reported as a flat fact about the Act it had guessed:

        Not held in the corpus: Specific Relief Act, 1963 is held, but no
        specific provision was identified in the question.

    on `what is the limitation for a suit for possession of immovable
    property`. Every word true; the whole misleading. The advocate reads a
    fact about the Specific Relief Act and is never told the product picked it
    off the word `possession`, in a question about limitation, or that the
    Limitation Act also matched.

    That is backwards: an unverifiable guess is exactly the case where the
    advocate has no other signal that the wrong Act was read.
    """
    from nm.knowledge.manifest import ActBasis, Manifest

    manifest = Manifest.load(
        pathlib.Path(__file__).resolve().parents[1] / "spec" / "manifest.yaml")
    resolved = manifest.resolve(
        "what is the limitation for a suit for possession of immovable property",
        on=date(2025, 1, 1))

    assert resolved.basis is ActBasis.INFERRED, (
        "the question names no Act, so nothing may be resolved as NAMED")
    assert resolved.must_disclose
    note = resolved.note()
    assert note and "inference" in note

    # And the note reaches the disclosure on every outcome, not only success.
    import inspect

    from nm.adapters.evidence import corpus

    body = inspect.getsource(corpus.CorpusEvidenceAdapter.fetch)
    returns = body.count("return EvidenceResult(")
    carried = body.count("assumption=note")
    assert carried >= returns - 1, (
        f"{returns} EvidenceResult returns and only {carried} carry the "
        f"inference note. A guess that is disclosed only when it worked is a "
        f"guess the advocate learns about from the answer being right.")
