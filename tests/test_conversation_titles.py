"""Each conversation in the history under a short title the model writes (plan AN.43, D81-D82; owner, 5 Nov 2026: "put a small name to
the matters in the list instead of large text", "let the model put a appropriate title based on the matter details ... a crisp and
appropriate title"). Code checks only what is mechanical; the model writes it once the matter is understood, beside the answer.
Offline: scripted models; the names are invented."""
import pytest

from nm.core_engine import titles
from nm.core_engine.conversation import chat_matter_id, title_of
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture
from tests.test_core_turn import FileMatterStore, ScriptedModel, run


@pytest.fixture
def store(tmp_path):
    return FileMatterStore(tmp_path, key="synthetic-turn-fixture")


class Titler:
    """Gives the titles it is scripted with, one per call, and keeps what each call was given."""

    def __init__(self, *titles_):
        self.titles, self.asked = list(titles_), []

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        import json
        assert prompt.operation == titles.OPERATION and prompt.effort == "medium"
        self.asked.append(json.loads(prompt.user))
        title = self.titles.pop(0)
        if isinstance(title, Exception):
            raise title
        return ModelResult(None, {"title": title}, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def test_code_checks_only_what_is_mechanical():
    assert titles.admitted("  Asha Rao v.\nGreenfield Builders  ") == ("Asha Rao v. Greenfield Builders", None)
    assert titles.admitted("one two three four five six seven eight nine ten")[0] is not None
    assert titles.admitted("one two three four five six seven eight nine ten eleven") == (
        None, "the title has 11 words; at most 10 are shown")
    assert titles.admitted("   ")[1] == "the title is empty"
    assert titles.first_words("a b c d e f g h i j k l") == "a b c d e f g h i j…"
    assert titles.first_words("Analyse this") == "Analyse this"


def test_a_title_too_long_is_asked_for_once_more_with_why_and_a_failure_leaves_none():
    given = {"advocate_messages": ["Please see the lease."]}
    model = Titler("The long running dispute between the landlord and the tenant over the shop lease", "Lease dispute over the shop")
    assert titles.entitle(model, given) == "Lease dispute over the shop"
    assert model.asked[1]["why_it_cannot_be_shown"] == "the title has 14 words; at most 10 are shown"
    assert titles.entitle(Titler(ProviderUnavailable("outage")), given) is None
    assert titles.entitle(Titler("x " * 20, "y " * 20), given) is None


def test_the_title_is_written_from_the_messages_and_the_matter_as_understood_and_nothing_else():
    context = {"conversation": [{"record_role": "original_account", "text": "Earlier message."},
                                {"record_role": "nm_interpretation", "text": "NM's earlier answer."}],
               "latest": {"text": "Latest message."}, "documents": [{"text": "A page of the papers."}]}
    plan = {"proposal": {"understanding": {
        "parties": [{"who": "Asha Rao", "role": "tenant", "client": True}, {"who": "Greenfield Builders", "role": "landlord",
                                                                            "client": False}],
        "disputes": [{"name": "Eviction from the shop", "legal_questions": []}], "summary": "A tenant faces eviction."}}}
    given = titles.material(context, plan)
    assert given == {"advocate_messages": ["Earlier message.", "Latest message."], "matter": {
        "parties": [{"who": "Asha Rao", "role": "tenant", "our_client": True}, {"who": "Greenfield Builders", "role": "landlord"}],
        "disputes": ["Eviction from the shop"], "summary": "A tenant faces eviction."}}
    assert titles.understood(plan) and not titles.understood({"proposal": {"understanding": {"parties": [], "disputes": []}}})
    assert titles.material(context) == {"advocate_messages": ["Earlier message.", "Latest message."]}


def test_a_conversation_is_titled_once_its_matter_is_understood_and_not_again(store):
    model = ScriptedModel(legal=True)
    asked = []

    def entitle(given):
        asked.append(given)
        return "Reported account matter"
    first = run(store, model, entitle=entitle)
    matter = store.load(chat_matter_id("owner", first["chat_id"]))
    assert title_of(matter) == {"text": "Reported account matter", "from_matter": True}
    assert "matter" in asked[0]
    run(store, model, entitle=entitle, chat_id=first["chat_id"], turn_id="t2", message="And the next step?")
    assert len(asked) == 1, "a title written from the matter is not written again"
    assert title_of(store.load(matter.id))["text"] == "Reported account matter"


def test_once_nm_names_a_conversation_it_stays_as_named(store):
    """D84 (owner, 5 Nov 2026: "once NM names it, let it stay that way"): never written again, whatever the later messages bring."""
    titles_given = iter(["Greeting", "Reported account matter"])
    first = run(store, ScriptedModel(legal=False), entitle=lambda given: next(titles_given))
    matter_id = chat_matter_id("owner", first["chat_id"])
    assert title_of(store.load(matter_id)) == {"text": "Greeting", "from_matter": False}
    run(store, ScriptedModel(legal=True), entitle=lambda given: next(titles_given), chat_id=first["chat_id"], turn_id="t2",
        message="The account was reported.")
    assert title_of(store.load(matter_id)) == {"text": "Greeting", "from_matter": False}


def test_no_title_leaves_the_answer_as_it_was(store):
    def entitle(given):
        raise ProviderUnavailable("Synthetic outage")
    response = run(store, ScriptedModel(legal=True), entitle=entitle)
    assert response["committed"] == "committed"
    assert title_of(store.load(chat_matter_id("owner", response["chat_id"]))) is None


def test_the_history_lists_each_conversation_under_its_title(served):
    served.model.title = "Reported account of the client"
    reply = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"})
    assert reply.status_code == 200, reply.text
    chat, = served.client.get("/api/work").json()["chats"]
    assert chat["title"] == "Reported account of the client" and chat["preview"] == "Inspect this reported account."
    assert served.model.titled == 1


def test_the_conversation_says_its_title_and_a_small_route_gives_it_alone(served):
    """D84: the page shows the title at the conversation's beginning - read with the conversation, or alone after an answer."""
    served.model.title = "Reported account of the client"
    reply = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"}).json()
    assert served.client.get(f"/api/chats/{reply['chat_id']}").json()["title"] == "Reported account of the client"
    assert served.client.get(f"/api/chats/{reply['chat_id']}/title").json() == {
        "chat_id": reply["chat_id"], "title": "Reported account of the client"}
    assert served.client.get("/api/chats/new_nothing/title").status_code == 404
    other = served.login("core-other@example.test")
    assert other.get(f"/api/chats/{reply['chat_id']}/title").status_code == 404


def test_the_operator_titles_the_conversations_saved_before_and_leaves_a_titled_one_alone(store):
    """D83: the conversations saved before titles were written, titled once, by the operator's run; one with a title keeps it."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("title_conversations",
                                                  Path(__file__).resolve().parents[1] / "operations" / "title_conversations.py")
    command = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(command)
    untitled = run(store, ScriptedModel(legal=True))
    titled = run(store, ScriptedModel(legal=True), turn_id="t9", entitle=lambda given: "Already named")
    asked = []

    def entitle(given):
        asked.append(given)
        return "Reported account matter"
    assert command.title_all(store, "owner", entitle, dry=True)["untitled"] == 1 and not asked
    counts = command.title_all(store, "owner", entitle)
    assert counts == {"untitled": 1, "unreadable": 0, "titled": 1, "no_title_given": 0, "not_saved": 0, "words": [3]}
    assert asked[0]["advocate_messages"] == ["Hello."] and "parties" in asked[0]["matter"]
    assert title_of(store.load(chat_matter_id("owner", untitled["chat_id"])))["text"] == "Reported account matter"
    assert title_of(store.load(chat_matter_id("owner", titled["chat_id"])))["text"] == "Already named"
    assert command.title_all(store, "owner", entitle)["untitled"] == 0, "once named, it stays as named"
    assert command.title_all(store, "someone-else", entitle)["untitled"] == 0
