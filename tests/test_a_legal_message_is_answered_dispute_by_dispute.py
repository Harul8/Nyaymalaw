"""A legal message is answered dispute by dispute, from the law actually retrieved.

Owner, 29 September 2026: *"When users send a message, the first thing is to
understand the message, classify the message, and if it is a legal matter, then
we should identify the dispute, then for each dispute, we retrieve the relevant
bare act and relevant judgments, retrieve those passages, then prepare a reply.
And the reply should be a summary of what the user has sent, what the model has
understood, then say okay these are the disputes as per your message and for
each of these disputes this is what the law says and this is what is required to
make the case stronger. While I don't want this to be a formula based, for legal
matters, this is how it should be."*

THE RULES:
1. With no provision-version register installed, a held provision is read as
   the library's CURRENT TEXT and says so on the passage; with a register, the
   strict rule stands. The served app, which has no register, reads current text.
2. EVERY dispute a legal message touches gets its law: its provisions, a
   judgment search once its side is settled, and what it needs -- not only the
   dispute in focus. Bounded, and the bound is said.
3. The answer says, once, that relied-on provisions are current text.
4. The reply may state a period only where a retrieved passage, the checked work
   or the advocate states it; a sentence the check names as unsupported law is
   written again once and otherwise not shown; a check that gives no verdict on
   support does not clear the reply.

Measured before this: on the Farah Begum matter every statute read was withheld,
only the focus dispute was worked, and the reply said "a three-year period for
property-related disputes" and "a six-month limitation" from the model's memory.
"""
from __future__ import annotations

import json

import pytest

from nm.advise.answer_contracts import (
    Answer,
    Element,
    ElementKind,
    Mode,
    ReplyParagraph,
    Route,
)
from nm.Archives.legal_brain.communicate import compose as compose_module
from nm.Archives.legal_brain.orchestrate import turn as turn_module
from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.Archives.legal_brain.retrieve.corpus_evidence import CorpusEvidenceAdapter, current_text_reason
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult, is_current_text
from nm.Archives.legal_brain.retrieve.provision_revision_sources import SelectionState
from nm.Archives.legal_brain.verify import grounding
from nm.shared.model_scripted import SCRIPTED_READS
from tests.test_a_disclosure_is_served_not_recorded import THREE_AT_ONCE, TODAY
from tests.test_provision_revisions_need_owned_interval_proof import (
    BEFORE,
    TITLE,
    adapter,
    population,
)
from tests.test_turn_contract import _Evidence, build, finding

pytestmark = pytest.mark.class_a


# ============================ 1. the current text ============================

def _current_text_adapter(tmp_path, pop=None):
    strict = adapter(tmp_path, pop)
    options = {}
    if pop:
        options = dict(source_registry=strict._source_registry,
                       revision_source_bytes=strict._revision_source_bytes,
                       revision_review_owner=strict._revision_review_owner,
                       revision_checked_at=strict._revision_checked_at)
    return CorpusEvidenceAdapter(tmp_path, strict._manifest,
                                 current_text_when_unversioned=True, **options)


def test_with_no_register_a_held_provision_is_read_as_current_text_and_says_so(tmp_path):
    read = _current_text_adapter(tmp_path).read_provision_at_date(TITLE, "7", BEFORE)
    assert read.evidence.coverage is Coverage.ANSWERED
    held = read.evidence.findings[0]
    assert "Held current rule." in held.span
    assert is_current_text(held), held.binding_reason
    assert BEFORE.isoformat() in held.binding_reason, (
        "the limit must name the date whose wording was not checked")
    # THE HISTORICAL QUESTION IS STILL UNANSWERED, and says so to a caller that asks.
    assert read.selection.state is SelectionState.NOT_ASSESSED


def test_the_strict_rule_is_unchanged_without_the_switch(tmp_path):
    """The negative control: the adapter's own default still withholds."""
    read = adapter(tmp_path).read_provision_at_date(TITLE, "7", BEFORE)
    assert read.evidence.coverage is Coverage.NOT_ASSESSED and not read.evidence.findings


def test_an_installed_register_is_never_bypassed_by_current_text(tmp_path):
    read = _current_text_adapter(tmp_path, population()).read_provision_at_date(
        TITLE, "7", BEFORE)
    assert read.selection.state is SelectionState.SELECTED
    assert read.evidence.findings and not any(is_current_text(f) for f in read.evidence.findings)


def test_the_served_app_reads_current_text_when_it_has_no_register(
        tmp_path, monkeypatch, scripted_application_environment):
    """On the composition root, not on a hand-built adapter (CLAUDE.md section 8)."""
    from pathlib import Path

    from nm.app.composition import Application
    from nm.arrive.store_directory import FileDirectory
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_immutable_corpus_publication import _scripted_model
    from tests.test_turn_contract import KEY

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    monkeypatch.setenv("NM_CORPUS_DIR", str(corpus))
    for name in ("NM_AUTHORITY_INDEX", "NM_IDENTITY_INDEX"):
        monkeypatch.delenv(name, raising=False)
    app = Application(root=Path(__file__).resolve().parents[1],
                      store=FileMatterStore(tmp_path / "matters", key=KEY),
                      directory=FileDirectory(tmp_path / "matters", key=KEY),
                      model=_scripted_model())
    assert app.evidence._source_registry is None
    assert app.evidence._current_text is True


# ======================= 2. every dispute gets its law =======================

class _Recording(_Evidence):
    def __init__(self, result=None):
        super().__init__(result)
        self.needs = []

    def fetch(self, need):
        self.needs.append(need)
        return super().fetch(need)


class _Judgments:
    """A judgment search port that records the words each dispute was searched with."""

    def __init__(self):
        self.words = []

    def search(self, words, *, similar=(), as_of, jurisdiction, limit=4):
        from nm.Archives.legal_brain.retrieve.section_search_port import SectionSearch

        self.words.append(words)
        return SectionSearch(True, (), note="searched")

    def readiness(self):
        return "ready"


def test_every_dispute_on_a_legal_message_gets_its_law(tmp_path):
    evidence = _Recording()
    engine, _ = build(tmp_path, evidence=evidence)
    judgments = _Judgments()
    engine.inner._judgments = judgments
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    threads = out.matter.threads
    assert len(threads) == 3, [t.label for t in threads]
    assert all("authorities" in t.assessed for t in threads), (
        "a dispute's law was never looked for: "
        + str({t.label: t.assessed for t in threads}))
    provisions = [n.question for n in evidence.needs if not n.want_authority]
    for t in threads:
        stem = t.label.rstrip("…").strip()
        assert any(stem in q for q in provisions), (
            f"no provision was looked up on {t.label!r}'s own words")
    # JUDGMENTS ARE SEARCHED THE WAY SECTIONS ARE (LB-106; owner, 30 September 2026),
    # through the judgment search on each dispute's own words -- not the older word
    # search through the evidence adapter.
    assert len(set(judgments.words)) == len(threads) == 3, (
        "each dispute gets its own judgment search")
    assert not [n for n in evidence.needs if n.want_authority], (
        "the older word-only judgment search still runs per message")
    shown = {e.thread for e in out.answer.elements if e.source is not None}
    assert {t.id for t in threads} <= shown, (
        "a dispute's retrieved passage never reached the answer")


def test_every_served_dispute_is_worked_the_same_way_and_nothing_else_is_computed(tmp_path):
    """EVERY DISPUTE BY ONE MECHANISM, AND ONLY WHAT THE PASSAGES GIVE (LB-76; owner, 30
    September 2026: "this analysis should come from retrieved passages only"). The focus
    and every other dispute record the same assessment -- the law looked for and the open
    questions -- and none computes a limitation deadline, an issue list, a proof table, an
    evidence list, a theory or the opposing case per message."""
    engine, _ = build(tmp_path, evidence=_Recording())
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    assert not out.answer.blocked
    assessed = [set(thread.assessed) for thread in out.matter.threads]
    for thread, keys in zip(out.matter.threads, assessed):
        assert {"authorities", "gaps"} <= keys, (
            f"{thread.label}: its law or its open questions were not recorded")
        assert not keys & {"deadlines", "issues", "proof", "evidence", "theory",
                           "recommendation", "premises"}, (
            f"{thread.label}: an analysis left the per-message path and still ran: "
            f"{sorted(keys & {'deadlines', 'issues', 'proof', 'evidence', 'theory'})}")
    assert out.metrics.llm_calls <= 4 + 4 * len(out.matter.threads) + 2, (
        "more model calls than the lean path makes: "
        f"{out.metrics.llm_calls} for {len(out.matter.threads)} disputes")


def test_the_bound_on_disputes_is_said_when_it_binds(tmp_path, monkeypatch):
    monkeypatch.setattr(turn_module, "MAX_DISPUTE_LAW", 1)
    engine, _ = build(tmp_path, evidence=_Recording())
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    unread = [t for t in out.matter.threads if "authorities" not in t.assessed]
    assert len(unread) == 1
    said = [e.text for e in out.answer.elements if "Not yet read" in e.text]
    assert len(said) == 1 and unread[0].label.rstrip("…")[:20] in said[0]


def test_a_dispute_whose_law_was_read_is_not_read_again_without_new_words(tmp_path):
    engine, store = build(tmp_path, evidence=_Recording())
    first = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    assert first.metrics.cause_reads == 3, "the control: one cause read per dispute"
    again = engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id,
                                 message="What should we do next on this?", today=TODAY,
                                 expected_version=first.matter.version))
    assert again.metrics.cause_reads <= 1, (
        "disputes whose law was already read were read again on a message that "
        "added nothing to them")


def test_a_stopped_turn_reads_no_dispute_law(tmp_path):
    engine, _ = build(tmp_path, evidence=_Recording())
    out = engine.run(TurnInput(advocate_id="adv", message="a cheque was dishonoured on 3 March"))
    assert out.answer.blocked
    assert not any("authorities" in t.assessed for t in out.matter.threads)


# ===================== 3. the current text is said once =======================

def test_relied_on_current_text_is_said_once_in_the_answer(tmp_path):
    current = finding(binding_reason=current_text_reason(TODAY))
    engine, _ = build(tmp_path, evidence=_Evidence(result=EvidenceResult(
        coverage=Coverage.ANSWERED, findings=(current,),
        searched_stores=("the_limitation_act_1963",))))
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    said = [e for e in out.answer.elements if "current text held in this library" in e.text]
    assert len(said) == 1 and said[0].disclosure


# ================== 4. the reply states no law from memory ====================

def test_periods_are_read_however_they_are_written():
    assert grounding.periods_stated("a three-year period") == {(3, "year")}
    assert grounding.periods_stated("Twelve years") == {(12, "year")}
    assert grounding.periods_stated("within 30 days and a 30-day notice") == {(30, "day")}
    assert grounding.periods_stated("thirty-five days") == {(35, "day")}
    assert grounding.periods_stated("a six-month limitation") == {(6, "month")}
    assert grounding.periods_stated("a three-foot strip since June 2019") == frozenset()


def _told(text, *elements):
    return Answer(route=Route.MATTER, mode=Mode.ASSESSMENT,
                  mode_statement="Taking this as a matter.", elements=elements,
                  composed=(ReplyParagraph(text),))


def test_a_period_nobody_stated_is_not_shown():
    step = Element(kind=ElementKind.FINDING, text="A suit for possession is available.")
    held = finding(span="For possession of immovable property... Twelve years.")
    bad = grounding.verify_reply(_told("The limitation is three years.", step), (held,), (held,))
    assert any("3 year" in v.detail for v in bad.violations), bad.violations
    good = grounding.verify_reply(_told("The period is twelve years.", step), (held,), (held,))
    assert not good.violations, good.violations
    own = grounding.verify_reply(_told("You gave notice 30 days ago.", step), (held,), (held,),
                                 own_words=("we gave notice 30 days ago",))
    assert not own.violations, own.violations


def _unsupported(sentence):
    def respond(user):
        return json.dumps({"items": [], "unsupported": [
            {"sentence": sentence, "why": "no passage states it"}]})
    return respond


UNSUPPORTED = "An unregistered agreement cannot be relied on for part performance."


def _composer(first, second=None):
    calls = []

    def respond(user):
        calls.append(user)
        text = second if (second is not None and len(calls) > 1) else first
        return json.dumps({"paragraphs": [{"text": text, "carries": ""}]})
    return respond, calls


def test_a_sentence_the_check_names_as_unsupported_is_written_again(tmp_path, monkeypatch):
    clean = "Here is where the file stands."
    compose, calls = _composer(UNSUPPORTED, clean)
    checks = []

    def check(user):
        checks.append(user)
        return (_unsupported(UNSUPPORTED)(user) if len(checks) == 1
                else json.dumps({"items": [], "unsupported": []}))
    monkeypatch.setitem(SCRIPTED_READS, "compose", compose)
    monkeypatch.setitem(SCRIPTED_READS, "compose_check", check)
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    assert len(calls) == 2 and "YOUR FIRST DRAFT FAILED THESE CHECKS" in calls[1]
    assert THREE_AT_ONCE in checks[0]
    assert "attributed allegations, not law" in checks[0]
    assert UNSUPPORTED in calls[1], "the repair round was not told what failed"
    assert out.answer.composed and out.answer.composed[0].text == clean
    assert all(UNSUPPORTED not in p.text for p in out.answer.composed)


def test_a_reply_still_unsupported_after_one_repair_is_not_shown(tmp_path, monkeypatch):
    compose, calls = _composer(UNSUPPORTED)
    monkeypatch.setitem(SCRIPTED_READS, "compose", compose)
    monkeypatch.setitem(SCRIPTED_READS, "compose_check", _unsupported(UNSUPPORTED))
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    assert len(calls) == 2, "one repair round, and only one"
    assert out.answer.composed == (), "a reply stating unsupported law was shown"
    assert any(v.rule == "E2" and "failed its own checks" in v.detail
               for v in out.metrics.violations)


def test_a_check_with_no_verdict_on_support_does_not_clear_the_reply(tmp_path, monkeypatch):
    """S1. Silence on support is not a pass. At the port the schema refuses the
    missing verdict; behind it, the reader refuses it again, so an adapter that
    does not validate cannot turn silence into clearance."""
    compose, _calls = _composer("Here is where the file stands.")
    monkeypatch.setitem(SCRIPTED_READS, "compose", compose)
    monkeypatch.setitem(SCRIPTED_READS, "compose_check",
                        lambda user: json.dumps({"items": []}))
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    assert out.answer.composed == ()
    assert any(v.rule == "E2" and ("no verdict" in v.detail or "could not be checked" in v.detail)
               for v in out.metrics.violations)
    shown = (ReplyParagraph("Here is where the file stands."),)
    assert compose_module.unsupported({"items": []}, shown) is None
    assert compose_module.unsupported({"items": [], "unsupported": []}, shown) == ()
    named = {"unsupported": [{"sentence": "A sentence the reply never wrote at all.",
                              "why": "x"}]}
    assert compose_module.unsupported(named, shown) == (), (
        "the check condemned words the reply does not contain")


def test_the_composer_is_given_each_dispute_with_its_law(tmp_path, monkeypatch):
    seen = []

    def compose(user):
        seen.append(user)
        return json.dumps({"paragraphs": []})
    monkeypatch.setitem(SCRIPTED_READS, "compose", compose)
    engine, _ = build(tmp_path, evidence=_Recording())
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    prompt = seen[0]
    block = prompt.split("THE DISPUTES ON THIS FILE", 1)[1].split(":\n", 1)[1]
    disputes = json.loads(block.split("\n\n", 1)[0])
    assert {d["dispute"] for d in disputes} == {t.label for t in out.matter.threads}
    assert all(d["law"] for d in disputes), "a dispute reached the composer with no law"
    assert all(d["their_words"] for d in disputes)
    assert "WHAT WAS TAKEN FROM THE MESSAGE" in prompt


def test_a_named_sentence_is_found_with_or_without_the_bold_marks():
    """The one mark a reply may carry cannot hide a sentence from the check."""
    shown = (ReplyParagraph("**Boundary dispute**: an owner may always remove a wall."),)
    named = {"unsupported": [{"sentence": "Boundary dispute: an owner may always remove a wall.",
                              "why": "no passage states it"}]}
    assert compose_module.unsupported(named, shown) == (
        "Boundary dispute: an owner may always remove a wall.",)


def test_reply_checker_sees_attributed_facts_without_treating_them_as_law():
    """A factual restatement is checked against the account, not model memory."""
    answer = _told("The advocate says a dated refusal occurred.",
                   Element(kind=ElementKind.FINDING,
                           text="The alleged refusal needs to be checked."))
    prompt = compose_module.check_prompt(
        answer.composed, answer, compose_module.material(answer),
        own_words=("The counterparty refused on 10 September 2026.",))
    assert "The counterparty refused on 10 September 2026." in prompt.user
    assert "attributed allegations, not law" in prompt.user
    assert "Applying a retrieved rule to attributed facts" in prompt.system
    # The factual account does not excuse an unsupported legal proposition.
    bad = "An unregistered instrument always defeats the claim."
    assert compose_module.unsupported(
        {"unsupported": [{"sentence": bad, "why": "no source"}]},
        (ReplyParagraph(bad),)) == (bad,)
