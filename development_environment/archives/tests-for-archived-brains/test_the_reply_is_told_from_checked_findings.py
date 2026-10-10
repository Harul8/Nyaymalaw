"""LB-76 / PRD E2: the reply is told from the checked findings, then checked again.

Owner, 28 September 2026: *"Let us give guiding principles to the model, however,
lets not put hard restrictions that would push the model to come up with
formalic, templated responses everytime."* Adopted with a reviewer's
corrections the same day.

THE RULES THIS FILE STATES
--------------------------
1. How the reply is written is GUIDANCE: no prompt tells the model how many
   words or sentences to write.
2. The words shown are checked on their own -- quotations, citations and linked
   passages. A reply whose failure no sentence can be dropped to cure shows the
   checked findings instead (a rewrite that still fails otherwise loses only the
   failing sentences: `test_a_reply_that_still_fails_loses_only_what_fails`).
3. A model's paragraph label certifies nothing: a carried item is its checked
   words, and a claimed conveyance stands only on a sentence found in the reply
   with every date the item states.
4. What must reach the advocate is narrow -- a loud signal and a dated step are
   confirmed in the prose or carried in their checked words, and a blocked turn is
   led by its blocker; everything else is the composer's material (owner, 30
   September 2026: the Farah Begum reply carried 74 appended items).
6. A citation is a tag the code renders: the composer writes [[E4]], the reply
   shows that source's own label where the tag stood, linked to the passage, and
   a tag naming no saved source is dropped (the previous build's mechanism).
5. Composing is presentation: a blocked turn still derives nothing behind its
   gate, and the reply is served, saved and read back as it was shown.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from nm.advise.answer_contracts import (
    Answer,
    Element,
    ElementKind,
    Mode,
    ReplyParagraph,
    Route,
    Signal,
)
from nm.Archives.legal_brain.communicate import compose
from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.Archives.legal_brain.retrieve.source_excerpt import capture as capture_source
from nm.Archives.legal_brain.verify import grounding
from nm.shared.model_scripted import SCRIPTED_READS, ScriptedModelAdapter
from tests.test_turn_contract import _model_config, build, finding

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
FOUND = finding()


def _answer(*elements: Element, blocked: bool = False, composed=()) -> Answer:
    return Answer(route=Route.MATTER, mode=Mode.FULL_BRIEF, mode_statement="Assessment",
                  elements=tuple(elements), blocked=blocked, composed=tuple(composed))


QUESTION = Element(kind=ElementKind.QUESTION, text="Is the client seeking or resisting possession?")
STEP = Element(kind=ElementKind.ACTION, text="Serve the notice on the tenant.",
               by_when=date(2026, 10, 12))
LIMIT = Element(kind=ElementKind.GROUND, disclosure=True,
                text="Not held: section 106 of the Transfer of Property Act was not retrieved.")
SUPPORT = Element(kind=ElementKind.GROUND, text="Article 65 governs possession suits.",
                  refs=(FOUND.locator,), source=capture_source(FOUND))


# ============================ 1. guidance, not counts =========================

#: A LIMIT on how much to write. "In four words" -- how much a correction
#: costs the advocate, said in comments across the product -- is not one.
_COUNT = re.compile(r"\b(?:at most|within|no more than|not more than|fewer than|less than|"
                    r"under|up to|maximum of)\s+(?:\d+|one|two|three|four|five|ten)\s+"
                    r"(?:words|sentences)\b", re.I)


def _prompt_sources() -> dict[Path, str]:
    """Every Python source in the product and the principles every read carries."""
    sources = {path: path.read_text(encoding="utf8") for path in (ROOT / "nm").rglob("*.py")}
    principles = ROOT / "docs" / "blueprint" / "LEGAL_BRAIN_PRINCIPLES.md"
    sources[principles] = principles.read_text(encoding="utf8")
    return sources


def test_no_prompt_tells_the_model_how_many_words_to_write():
    sources = _prompt_sources()
    assert len(sources) > 100, "the population is too small to mean anything"
    counted = [f"{path.relative_to(ROOT)}: {m.group(0)!r}"
               for path, text in sources.items() for m in _COUNT.finditer(text)]
    assert not counted, (
        "a prompt still sets a word or sentence count, which is a template, not "
        f"guidance (owner, 28 September 2026): {counted}")


def test_the_count_scan_can_see_a_count():
    """THE POSITIVE CONTROL: a scan over sources that happen to be clean proves
    nothing about the scan."""
    assert _COUNT.search("Recommend one focused next step in at most 40 words")
    assert _COUNT.search("Keep the answer within 240 words.")
    assert not _COUNT.search("two words and a case fact")


# ======================== 2. the words shown are checked ======================

def test_the_words_shown_are_checked_quotes_citations_and_passages():
    misquote = _answer(STEP, SUPPORT, composed=(
        ReplyParagraph('The Article says "twelve years from the date of dispossession" here.'),))
    report = grounding.verify_reply(misquote, (FOUND,), (FOUND,))
    assert [v.gate_id for v in report.violations] == ["G-QUOTE"]

    remembered = _answer(STEP, SUPPORT, composed=(
        ReplyParagraph("Section 27 of the Limitation Act decides this."),))
    report = grounding.verify_reply(remembered, (FOUND,), (FOUND,))
    assert [v.gate_id for v in report.violations] == ["G-GROUND"]

    text, cites = compose.cited('Article 65 gives the suit "twelve years." -- "For '
                                'possession of immovable property" is the entry [[E1]].',
                                _answer(STEP, SUPPORT))
    faithful = _answer(STEP, SUPPORT, composed=(ReplyParagraph(text, cites=cites),))
    assert grounding.verify_reply(faithful, (FOUND,), (FOUND,)).violations == []


def test_the_advocate_s_own_words_may_be_quoted_back():
    reply = _answer(STEP, SUPPORT, composed=(
        ReplyParagraph('You told me "the tenant stopped paying in March" and that is on file.'),))
    assert grounding.verify_reply(reply, (FOUND,), (FOUND,)).violations
    own = ("We act for the landlord; the tenant stopped paying in March.",)
    assert grounding.verify_reply(reply, (FOUND,), (FOUND,), own_words=own).violations == []


def test_a_carried_limit_keeps_its_licence_to_name_what_was_not_retrieved():
    """A limit names what could not be retrieved. Carried verbatim it is the
    element the gate already passed as a disclosure; retold in the composer's
    own words it is an assertion, and must not cite what nobody retrieved."""
    carried = _answer(STEP, LIMIT, composed=(ReplyParagraph(LIMIT.text, carries=1),))
    assert grounding.verify_reply(carried, (FOUND,), (FOUND,)).violations == []
    retold = _answer(STEP, LIMIT, composed=(
        ReplyParagraph("Section 106 of the Transfer of Property Act was not available."),))
    assert grounding.verify_reply(retold, (FOUND,), (FOUND,)).violations


# ===================== 3. a label certifies nothing ===========================

def test_a_carried_item_is_its_checked_words_whatever_the_composer_wrote():
    answer = _answer(STEP, LIMIT)
    paragraphs = compose.paragraphs_from({"paragraphs": [
        {"text": "Something softer about the notice.", "carries": "E1"},
        {"text": "First part [[E1]].\n\nSecond part.", "carries": ""},
        {"text": "Unknown item [[E9]].", "carries": "E7"},
    ]}, answer)
    assert paragraphs[0] == ReplyParagraph(LIMIT.text, carries=1)
    # A tag on an item with no saved source is dropped, not guessed; a paragraph
    # written with a blank line in it is two paragraphs.
    assert paragraphs[1:3] == (ReplyParagraph("First part."), ReplyParagraph("Second part."))
    assert paragraphs[3] == ReplyParagraph("Unknown item.")
    with pytest.raises(ValueError, match="verbatim"):
        _answer(STEP, LIMIT, composed=(ReplyParagraph("Softer words", carries=1),))


def test_a_claimed_conveyance_stands_only_on_a_sentence_in_the_reply():
    answer = _answer(STEP, LIMIT)
    paragraphs = (ReplyParagraph("Serve the notice on the tenant by 12 October 2026."),)
    items = compose.material(answer)
    claimed = {"items": [
        {"id": "E0", "conveyed": True, "paragraph": 0,
         "sentence": "Serve the notice on the tenant by 12 October 2026."},
        {"id": "E1", "conveyed": True, "paragraph": 0,
         "sentence": "The limit about section 106 is stated here."},
    ]}
    found = compose.confirmed(claimed, paragraphs, answer, items)
    assert found.where == {0: 0}, "a sentence the reply does not contain confirmed an item"


def test_a_conveyance_is_void_when_a_date_the_item_states_is_missing():
    answer = _answer(STEP, LIMIT)
    paragraphs = (ReplyParagraph("Serve the notice on the tenant soon, before it lapses."),)
    claimed = {"items": [{"id": "E0", "conveyed": True, "paragraph": 0,
                          "sentence": "Serve the notice on the tenant soon, before it lapses."}]}
    assert compose.confirmed(claimed, paragraphs, answer, compose.material(answer)).where == {}


def test_dates_are_read_however_they_are_written():
    want = {date(2026, 10, 12)}
    for written in ("by 2026-10-12", "by 12 October 2026", "by 12th Oct 2026",
                    "by October 12, 2026", "by 12.10.2026", "by 12/10/2026"):
        assert compose.dates_mentioned(written) == want, written
    assert compose.dates_mentioned("within twelve years") == frozenset()


# ======================= 4. nothing material is dropped =======================

def test_only_a_dated_step_or_a_loud_signal_must_reach_the_advocate():
    """THE OWNER'S RULE, 30 September 2026: the reply is what the composer writes.
    A limit, a question or a finding is its material, told where it serves the
    request and otherwise kept in the saved record -- never appended after it."""
    answer = _answer(STEP, LIMIT, SUPPORT, QUESTION)
    assert compose.material(answer) == (0,)
    told = (ReplyParagraph("Serve the notice on the tenant by 12 October 2026."),)
    assert compose.settle(told, answer, (0,), compose.Confirmed({0: 0})) == told
    silent = (ReplyParagraph("The position is broadly favourable."),)
    assert compose.settle(silent, answer, (0,), compose.Confirmed({})) == (
        silent[0], ReplyParagraph(STEP.text, carries=0)), "a dated step was dropped"


def test_a_blocked_reply_is_led_by_its_blocker_unless_the_lead_is_confirmed():
    answer = _answer(QUESTION, LIMIT, blocked=True)
    prose = (ReplyParagraph("There is a dishonoured cheque on the file."),)
    settled = compose.settle(prose, answer, compose.material(answer), compose.Confirmed({}))
    assert settled[0] == ReplyParagraph(QUESTION.text, carries=0)
    assert [p.carries for p in settled] == [0, None]

    led = (ReplyParagraph("Before anything else: is the client seeking or resisting "
                          "possession? Everything turns on it."),)
    kept = compose.settle(led, answer, compose.material(answer), compose.Confirmed({0: 0, 1: 0}))
    assert kept == led, "a confirmed lead was overridden"


def test_a_loud_signal_is_material_even_on_a_ground():
    loud = Element(kind=ElementKind.GROUND, text="An adverse treatment flag on the authority.",
                   signal=Signal.ADVERSE_TREATMENT)
    assert compose.material(_answer(STEP, loud)) == (0, 1)


# ===================== 6. citations are tags the code renders ==================

def test_a_tag_becomes_the_sources_own_label_linked_where_it_stands():
    answer = _answer(STEP, SUPPORT, LIMIT)
    label = SUPPORT.source.label
    text, cites = compose.cited("Possession suits run twelve years [[E1]]. Serve notice "
                                "first [[E2]], as the rule requires [[ E1 ]].", answer)
    assert text == (f"Possession suits run twelve years ({label}). Serve notice first, as "
                    f"the rule requires ({label}).")
    assert [text[a:b] for a, b, _ in cites] == [label, label]
    assert [i for _, _, i in cites] == [1, 1], "a tag on an item with no passage was kept"
    Answer(route=Route.MATTER, mode=Mode.FULL_BRIEF, mode_statement="Assessment",
           elements=answer.elements, composed=(ReplyParagraph(text, cites=cites),))


def test_a_label_the_composer_typed_is_linked_not_repeated():
    answer = _answer(STEP, SUPPORT)
    label = SUPPORT.source.label
    text, cites = compose.cited(f"This is governed by {label.lower()} [[E1]].", answer)
    assert text == f"This is governed by {label}." and text.count(label) == 1
    assert [text[a:b] for a, b, _ in cites] == [label]


def test_a_run_of_item_ids_is_read_as_citations_and_no_id_reaches_the_advocate():
    """MEASURED ON THE FARAH BEGUM TURN: GPT-4.1 mini wrote "[[E2],[E8],[E13]-[E15]]"
    after a paragraph. Every bracketed run of ids is read the same way: each id with
    a passage becomes its citation, the rest are dropped, and nothing of the run is
    left in the words."""
    answer = _answer(STEP, SUPPORT, LIMIT)
    label = SUPPORT.source.label
    for written in ("The burden lies on him [[E1],[E0],[E2]-[E1]].",
                    "The burden lies on him [E0, E1].", "The burden lies on him [[E0]][[E1]]."):
        text, cites = compose.cited(written, answer)
        assert text == f"The burden lies on him ({label}).", written
        assert [i for _, _, i in cites] == [1]
    assert compose.cited("Nothing here [[E0],[E2]].", answer) == ("Nothing here.", ())


def test_the_matters_own_dispute_titles_are_not_authorities():
    """A REPLY TOLD DISPUTE BY DISPUTE NAMES EACH BY ITS TITLE -- "Farah Begum v.
    Raghav Reddy -- the strip" -- and the citation check read that as a case nobody
    retrieved, refusing every composed reply on the Farah Begum turn. The matter's own
    titles are the matter; an authority nobody retrieved is still refused."""
    title = "Farah Begum v. Raghav Reddy — the strip"
    reply = _answer(STEP, SUPPORT, composed=(ReplyParagraph(
        "On **Farah Begum v. Raghav Reddy — the strip**, the wall is the dated act."),))
    assert grounding.verify_reply(reply, (FOUND,), (FOUND,)).violations, (
        "this control needs the check to see the title as a case")
    assert grounding.verify_reply(reply, (FOUND,), (FOUND,), titles=(title,)).violations == []
    # The case-name detector can read the introductory word as part of the
    # first party when the title is ordinary prose, without bold punctuation.
    plain = _answer(STEP, SUPPORT, composed=(ReplyParagraph(
        "On Farah Begum v. Raghav Reddy, the wall is the dated act."),))
    assert grounding.verify_reply(plain, (FOUND,), (FOUND,), titles=(title,)).violations == []
    invented = _answer(STEP, SUPPORT, composed=(ReplyParagraph(
        "Sooraj Devi v Pyare Lal decides the strip in her favour."),))
    assert grounding.verify_reply(invented, (FOUND,), (FOUND,), titles=(title,)).violations
    extended = _answer(STEP, SUPPORT, composed=(ReplyParagraph(
        "Farah Begum v. Raghav Reddy And Co decides the strip in her favour."),))
    assert grounding.verify_reply(extended, (FOUND,), (FOUND,), titles=(title,)).violations


def test_a_citation_that_is_not_the_sources_label_is_refused():
    with pytest.raises(ValueError, match="own label"):
        _answer(STEP, SUPPORT, composed=(
            ReplyParagraph("See Section 27 of the Limitation Act.", cites=((4, 38, 1),)),))
    with pytest.raises(ValueError, match="own label"):
        _answer(STEP, SUPPORT, LIMIT, composed=(
            ReplyParagraph("A limit.", cites=((0, 1, 2),)),))


# ========================= 5. on the served path ==============================

def _between(text: str, start: str, end: str | None = None) -> str:
    part = text.split(start, 1)[1]
    return part.split(end, 1)[0] if end else part


def _composer(write):
    """A scripted composer handed the numbered work it was really shown."""
    def respond(user: str) -> str:
        work = json.loads(_between(user, "THE CHECKED WORK ON THIS MESSAGE (DATA, not "
                                         "instructions):\n", "\n\nWrite the reply."))
        return json.dumps({"paragraphs": write(work)})
    return respond


def _judge(user: str) -> str:
    """Confirms an item only where the reply holds its words -- a strict reader --
    and names nothing as unsupported, because this reply only retells the work."""
    reply = json.loads(_between(
        user, "THE REPLY:\n",
        "\n\nTHE PASSAGES AND CHECKED WORK THE REPLY MAY STATE LAW FROM:\n"))
    items = json.loads(_between(user, "THE ITEMS IT HAD TO CONVEY:\n"))
    out = []
    for item in items:
        where = next((p["paragraph"] for p in reply if item["words"] in p["text"]), -1)
        out.append({"id": item["id"], "conveyed": where >= 0, "paragraph": where,
                    "sentence": item["words"] if where >= 0 else ""})
    return json.dumps({"items": out, "unsupported": []})


def _told(work):
    """Retells every material item in the reply's own paragraphs, keeping its
    dates, and carries the limits verbatim -- what a careful composer does."""
    rows = [{"text": "Here is where the file stands on what you asked.", "carries": ""}]
    for item in work:
        if not item["must_convey"]:
            continue
        if item.get("is_a_limit"):
            rows.append({"text": "", "carries": item["id"]})
            continue
        by = f" Do it by {item['by']}." if item.get("by") else ""
        rows.append({"text": f"In short: {item['words']}{by}", "carries": ""})
    return rows


BRIEF = "we act for the plaintiff in a possession suit over the land"


def test_a_composed_reply_is_served_saved_and_read_back(client, monkeypatch):
    monkeypatch.setitem(SCRIPTED_READS, "compose", _composer(_told))
    monkeypatch.setitem(SCRIPTED_READS, "compose_check", _judge)
    r = client.post("/api/turn", json={"message": BRIEF, "today": "2026-09-04"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["composed"], "the served reply was not composed"
    assert body["composed"][0]["text"] == "Here is where the file stands on what you asked."
    assert body["elements"], "the checked findings must stay on the answer"
    material = {i for i, e in enumerate(body["elements"])
                if e["by_when"] or Signal(e["signal"]).is_loud}
    conveyed = {p["carries"] for p in body["composed"] if p["carries"] is not None}
    told = " ".join(p["text"] for p in body["composed"])
    assert all(i in conveyed or body["elements"][i]["text"] in told for i in material), (
        "a material finding reached neither the prose nor a carried paragraph")
    assert body["metrics"]["presentation_reads"] == 2

    history = client.get(f"/api/matters/{body['matter_id']}/transcript").json()
    assert history["turns"][-1]["composed"] == body["composed"], (
        "the reply read back is not the reply that was shown")


def test_a_reply_that_fails_its_checks_shows_the_checked_findings(tmp_path):
    model = ScriptedModelAdapter(
        _model_config(),
        responses={"__default__": "File the summary possession suit within six months."},
        structured_responses={"compose": {"paragraphs": [
            {"text": "Section 27 of the Limitation Act decides this suit.",
             "carries": ""}]}})
    engine, _ = build(tmp_path, model=model)
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    assert len(out.answer.elements) > 1
    assert out.answer.composed == (), "a reply citing what was never retrieved was shown"
    assert any(v.rule == "E2" and "failed its own checks" in v.detail
               for v in out.metrics.violations), "the fall-back was not recorded for review"


def test_a_reply_that_drops_what_matters_is_qualified_not_trimmed(tmp_path):
    model = ScriptedModelAdapter(
        _model_config(),
        responses={"__default__": "File the summary possession suit within six months."},
        structured_responses={
            "compose": {"paragraphs": [{"text": "The position is broadly favourable.",
                                        "carries": ""}]},
            "compose_check": {"items": [], "unsupported": []}})
    engine, _ = build(tmp_path, model=model)
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    answer = out.answer
    assert answer.composed[0].text == "The position is broadly favourable."
    carried = [p.carries for p in answer.composed[1:]]
    assert carried == list(compose.material(answer)), (
        "every material finding the prose did not convey must follow it, in its "
        "checked words and in the order the work holds them")


def test_a_stopped_turn_is_not_retold_and_derives_nothing(tmp_path):
    """A STOPPED TURN IS NOT RETOLD (owner, 29 September 2026). Measured on the
    Farah Begum matter: a turn stopped because the disputes could not be
    separated was retold as "I have corrected and confirmed the four separate
    disputes", with limitation periods nobody retrieved. A blocked answer is its
    blocker and its limits, shown as they are, and nothing is spent behind it."""
    model = ScriptedModelAdapter(
        _model_config(),
        responses={"__default__": "File the summary possession suit within six months."},
        structured_responses={
            "compose": {"paragraphs": [{"text": "There is a dishonoured cheque on the file.",
                                        "carries": ""}]},
            "compose_check": {"items": [], "unsupported": []}})
    engine, _ = build(tmp_path, model=model)
    out = engine.run(TurnInput(advocate_id="adv", message="a cheque was dishonoured on 3 March"))
    assert out.answer.blocked
    assert len(out.answer.elements) > 1, "this control needs more than the blocker"
    assert out.answer.composed == (), "a stopped turn was retold"
    assert out.metrics.presentation_reads == 0
    assert (out.metrics.llm_calls - out.metrics.settling_reads) == 0, (
        "something was derived or composed behind the gate")


def test_a_question_of_law_is_told_not_merely_quoted(tmp_path):
    """A provision read back is a quotation, not yet an answer to the question.
    Told from the retrieved row and checked against the same retrieval."""
    told = "Article 65 gives a suit for possession of immovable property twelve years"
    model = ScriptedModelAdapter(
        _model_config(),
        responses={"__default__": "File the summary possession suit within six months."},
        structured_responses={
            "compose": {"paragraphs": [{"text": f"{told} [[E0]].", "carries": ""}]},
            "compose_check": {"items": [{"id": "E0", "conveyed": True, "paragraph": 0,
                                         "sentence": told}], "unsupported": []}})
    engine, _ = build(tmp_path, model=model)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="what is the limitation for a suit for possession of immovable property"))
    assert out.answer.route is Route.NON_MATTER and out.matter is None
    label = out.answer.elements[0].source.label
    assert out.answer.composed[0].text == f"{told} ({label})."
    assert [(out.answer.composed[0].text[a:b], i)
            for a, b, i in out.answer.composed[0].cites] == [(label, 0)]
    assert [p.carries for p in out.answer.composed[1:]] == [
        i for i in compose.material(out.answer) if i != 0]


def test_the_offline_double_composes_nothing_so_the_findings_are_shown(tmp_path):
    """The default: no fixture, no reply -- the answer is exactly what it was
    before composition existed."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    assert out.answer.composed == ()
    assert out.metrics.presentation_reads == 1
