"""What the advocate adds while a matter waits is read by every step that reads their messages (plan AN.48, owner decision D159:
"on par with my messages"; its register of exceptions, item 6). 48h made an added message citable; these are the places that list
the advocate's messages themselves - the reading of the matter the understanding and the time limits are given, where a time
limit's date may be quoted from, the checks of a fact's words and figures, what the steps reading the papers are shown, NM's
questions, a title, the check behind a fact's note. Each reads the earlier messages, the latest, then those added after it; a context
without additions gives exactly what it gave before. Offline: invented words, scripted models."""
import json

from nm.core_engine import calculation, questions, research, response_rendering, titles
from nm.core_engine.conversation import added_messages
from nm.core_engine.understanding import advocate_messages, context_aliases
from nm.shared.model_port import Completion, ModelResult, Usage
from tests.test_core_calculation import Calculating, Held, step
from tests.test_core_understanding import context

EARLIER = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate", "record_role": "original_account",
           "text": "My client lent money to a friend."}
NOTE = {"source_id": "t1:nm", "turn_id": "t1", "speaker": "nm", "record_role": "nm_interpretation", "text": "An earlier note."}
LATEST = "The bank's return memo reached my client on 18 August 2026. Was the complaint in time?"
ADDED = "The notice was delivered on 29 August 2026, and Rs. 4,75,000 is still unpaid."


def with_added(ctx, *texts):
    return {**ctx, "added": added_messages(ctx["latest"]["turn_id"], [{"text": text} for text in texts])}


def test_the_advocates_messages_are_the_earlier_ones_the_latest_then_those_added():
    before = context(LATEST, [EARLIER, NOTE])
    assert [row["text"] for row in advocate_messages(before)] == [EARLIER["text"], LATEST], "as before: no note of ours"
    after = with_added(before, ADDED, "And a second thing.")
    assert [row["text"] for row in advocate_messages(after)] == [EARLIER["text"], LATEST, ADDED, "And a second thing."]
    assert [row["text"] for row in advocate_messages(context(""))] == [], "a latest message without words, as before"
    assert context_aliases(after)["M4"] == "t2:added1", "numbered after the latest one (48h): M1, M2 earlier, M3 latest"


def test_the_reading_of_the_matter_shows_what_was_added_after_the_latest_message():
    before = context(LATEST, [EARLIER])
    text = research.conversation_text(with_added(before, ADDED))
    assert text.index(LATEST) < text.index("Added by the advocate after that message") < text.index(ADDED)
    assert research.conversation_text(before) == research.conversation_text({**before, "added": []})
    assert "Added by the advocate" not in research.conversation_text(before)


def test_a_time_limit_can_run_from_a_date_the_advocate_added():
    proposal = {"needed": True, "why": "Whether the complaint was in time.", "not_assessed": [], "calculations": [
        step("c1", "Last day for the drawer to pay", "within fifteen days of the receipt of the said notice", "fifteen days",
             {"after": "", "event": "", "date": "2026-08-29", "quote": "notice was delivered on 29 August 2026"})]}
    added = with_added(context(LATEST), ADDED)
    model = Calculating(proposal)
    record = calculation.work_out(model, added, Held())
    (entry,) = record["calculations"]
    assert entry["start"]["date"] == "2026-08-29" and entry["start"]["source_id"] == "t2:added1"
    assert ADDED in model.seen["calculation"].user, "the step reads the added message"
    assert calculation.validate(record, added) == record
    alone = calculation.work_out(Calculating(proposal), context(LATEST), Held())
    assert not alone["calculations"] and alone["not_assessed"], "without it, the date's words are nowhere"
    assert calculation._facts_in(with_added(context(LATEST, [EARLIER]), "a", "b"), {
        identity: {"record_role": "original_account"} for identity in ("t2:advocate", "t2:added1", "t2:added2", "t1:advocate")}) == [
        "t2:advocate", "t2:added2", "t2:added1", "t1:advocate"], "right after the latest message, latest first"


def test_the_steps_that_read_the_papers_and_the_figure_check_read_what_was_added():
    added = with_added(context(LATEST, [EARLIER]), ADDED)
    for shown in (research._file_context(added, [], False), research._papers_text(added, [])):
        assert shown.index(LATEST) < shown.index(ADDED)
    understanding = {"summary": "Rs. 4,75,000 is unpaid."}
    assert research._figure_problems(understanding, added) == [], "the advocate's own figure"
    assert research._figure_problems(understanding, context(LATEST, [EARLIER])), "a figure no message gives, as before"
    assert response_rendering._given_words('"delivered on 29 August 2026"', added)
    assert not response_rendering._given_words('"delivered on 29 August 2026"', context(LATEST))


class Proposing:
    def __init__(self):
        self.users = []

    def structured(self, prompt, schema, tier, **kwargs):
        self.users.append(json.loads(prompt.user))
        return ModelResult(None, {"questions": []}, tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def test_nms_questions_and_the_title_read_what_was_added():
    plan = {"proposal": {"understanding": {"disputes": [{"id": "D1", "name": "The loan"}]}}}
    calls = Proposing()
    questions.propose(calls, with_added(context(LATEST, [EARLIER]), ADDED), {}, plan, [])
    assert calls.users[0]["advocate_messages"] == [EARLIER["text"], LATEST, ADDED], "NM does not ask for what was just added"
    questions.propose(calls, context(LATEST, [EARLIER]), {}, plan, [])
    assert calls.users[1]["advocate_messages"] == [EARLIER["text"], LATEST], "as before"
    assert titles.material(with_added(context(LATEST), ADDED))["advocate_messages"] == [LATEST, ADDED]
    assert titles.material(None) == {"advocate_messages": []}
