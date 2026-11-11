"""Plan AN.48, D176 (pieces 48f7-48f8; the owner's decisions of 11 Nov 2026): on the hosted installation NM's reranker runs on a
graphics machine of its own, woken when needed; where that machine cannot be had, research pauses.

What is proved here, offline and with stand-ins (no graphics card, no AWS account, no paid call):
- the graphics machine's service scores each batch exactly as the search made it, through a real local connection, and takes
  nothing but a batch from a sender who holds the shared secret; it keeps and logs nothing of what it scores;
- a machine that sleeps is woken and waited for; one the budget has stopped pauses research for the budget; one that does not wake
  in ten minutes pauses research; a machine that reads with another model is not used;
- AWS's own client (with stubbed answers) starts a stopped machine, leaves a running one alone, and says when starting it is refused;
- every request passes the reranker's own gate, which admits the owner's two exceptions and nothing else;
- the search lets a pause through rather than ranking without the reranker, and the turn stops there, keeping what it finished, in
  the owner's words, for Continue;
- with no reranker address the installation reranks in its own process, as before.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import math
import os
import threading
import time
from pathlib import Path

import httpx
import pytest

from nm.app.composition import build_reranker, reranker_policy, search_may_run
from nm.core_engine import steps as stepwise
from nm.core_engine.conversation import ConversationRefused, shown_of
from nm.core_engine.retrieval import (RERANK_BATCH_CHARACTERS, RERANK_BATCH_PAIRS, RERANK_MODEL, RERANK_TOKENS, HybridSearcher,
                                      SearchUnavailable, _batched_scores, _Models)
from nm.core_engine.turn import STOP_NEEDS, STOPS
from nm.shared.egress_contracts import DataClass, EgressRefused, Gatekeeper, Sink
from nm.shared.egress_policy import egress_policy
from nm.shared.rerank_port import BUDGET_PAUSED, GRAPHICS_UNAVAILABLE, ResearchPaused
from nm.shared.rerank_remote import (AWAKE, DENIED, MACHINE_CONTROL_PROCESSOR, RERANKER_PROCESSOR, UNAVAILABLE, MachineWaker,
                                     RemoteReranker)
from tests import test_core_turn as core_turn
from tests.test_core_answer_sources import AdjacentJudgment
from tests.test_core_turn import ScriptedModel, store  # noqa: F401 - the store fixture
from tests.test_current_brain_retrieval import QUERIES, Collection
from tests.test_search_failures_are_diagnosable import Failing

ROOT = Path(__file__).resolve().parents[1]
SECRET = "nm-test-secret-0123456789"
WORDS_OF_A_MATTER = "the tenant's landlord changed the locks on 3 March"


def service_module():
    spec = importlib.util.spec_from_file_location("reranker_service", ROOT / "operations" / "aws" / "reranker_service.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score(question, passage):
    """A stand-in model: a fixed score from the pair's lengths (floats survive the JSON round trip exactly)."""
    return round(math.sin(len(question) * 0.37 + len(passage) * 0.11) * 10, 6)


class Here:
    """The reranker in this process, as the search sees a model: predict(batch, batch_size, show_progress_bar)."""

    def __init__(self):
        self.batches = []

    def predict(self, pairs, batch_size=None, show_progress_bar=False):
        self.batches.append([tuple(pair) for pair in pairs])
        return [score(question, passage) for question, passage in pairs]


def windows():
    """Pairs of many lengths - short, middling and a few long - so that batches close both at 16 pairs and at 32,000 characters."""
    pairs = []
    for index in range(41):
        question = f"Is an unregistered sale agreement admissible {index}?"
        length = 33000 if index % 13 == 5 else 300 + 97 * index
        pairs.append((question, ("Section 49 of the Registration Act. " * 1000)[:length]))
    return pairs


@pytest.fixture
def secret_file(tmp_path):
    path = tmp_path / "reranker.secret"
    path.write_text(SECRET + "\n", encoding="utf-8")
    return path


@pytest.fixture
def machine(tmp_path, secret_file):
    """The graphics machine's real service on a free local port, scoring with the stand-in model."""
    seen, last_use = [], tmp_path / "last-use"
    last_use.write_text("", encoding="utf-8")
    os.utime(last_use, (0, 0))

    def scorer(pairs):
        seen.append(list(pairs))
        return [score(question, passage) for question, passage in pairs]
    server = service_module().make_server("127.0.0.1", 0, scorer, secret_file, device="cpu", dtype="float32", last_use=last_use)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield {"url": f"http://127.0.0.1:{server.server_address[1]}", "seen": seen, "last_use": last_use, "server": server}
    finally:
        server.shutdown()
        server.server_close()


def gate(lines=None):
    return Gatekeeper(policy=reranker_policy(), audit=(lines.append if lines is not None else None))


def remote(url, secret_file, **changes):
    return RemoteReranker(url, secret_file, changes.pop("gate", gate()), ROOT / "absent-tokenizer", model=RERANK_MODEL,
                          max_length=RERANK_TOKENS, **changes)


# --- the graphics machine's service, through a real local connection --------------------------------------------------------

def test_the_graphics_machine_scores_each_batch_exactly_as_the_search_made_it(machine, secret_file):
    lines, here = [], Here()
    pairs = windows()
    expected = _batched_scores(here, pairs)
    got = _batched_scores(remote(machine["url"], secret_file, gate=gate(lines)), pairs)
    assert got == expected, "the same scores, in the pairs' own order"
    assert machine["seen"] == here.batches, "the machine scored the very batches the search makes here"
    assert len(here.batches) > 2 and max(len(batch) for batch in here.batches) == RERANK_BATCH_PAIRS
    assert any(sum(len(q) + len(p) for q, p in batch) > RERANK_BATCH_CHARACTERS for batch in here.batches if len(batch) == 1)
    sent = [line for line in lines if "processor=nm-own-reranker" in line]
    assert len(sent) == len(here.batches) and all("permitted" in line and "sink=index" in line for line in sent)


def test_a_sender_without_the_shared_secret_is_refused_and_research_pauses(machine, tmp_path, caplog):
    wrong = tmp_path / "wrong.secret"
    wrong.write_text("another-secret", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="nm.shared.rerank_remote"), pytest.raises(ResearchPaused) as paused:
        remote(machine["url"], wrong).predict([("a question", "a passage")])
    assert paused.value.code == GRAPHICS_UNAVAILABLE and machine["seen"] == []
    assert any("secret" in record.getMessage() for record in caplog.records)


def test_the_service_takes_nothing_but_a_batch_of_pairs(machine, tmp_path):
    headers = {"Authorization": f"Bearer {SECRET}"}
    with httpx.Client(base_url=machine["url"], trust_env=False) as client:
        health = client.get("/health").json()
        assert health == {"ok": True, "model": RERANK_MODEL, "max_length": RERANK_TOKENS, "device": "cpu", "dtype": "float32"}
        assert client.post("/score", content=b"not json", headers=headers).status_code == 400
        too_many = {"pairs": [["q", "p"]] * (RERANK_BATCH_PAIRS + 1)}
        assert client.post("/score", json=too_many, headers=headers).status_code == 400
        assert client.post("/score", json={"pairs": [["q", 1]]}, headers=headers).status_code == 400
        assert client.post("/score", json={"pairs": [["q", "p"]]}).status_code == 401
        assert client.post("/elsewhere", json={"pairs": [["q", "p"]]}, headers=headers).status_code == 404
    assert machine["seen"] == []
    unusable = tmp_path / "empty.secret"
    unusable.write_text("  \n", encoding="utf-8")
    with pytest.raises(ValueError):
        service_module().make_server("127.0.0.1", 0, lambda pairs: [], unusable, device="cpu", dtype="float32")


def test_the_service_keeps_nothing_of_what_it_scores_and_marks_its_last_use(machine, secret_file, caplog):
    with caplog.at_level(logging.DEBUG):
        remote(machine["url"], secret_file).predict([(WORDS_OF_A_MATTER, "Section 106 of the Transfer of Property Act")])
    assert machine["last_use"].stat().st_mtime > 1_000_000, "the idle watch sees the machine was used"
    assert not any(WORDS_OF_A_MATTER in record.getMessage() for record in caplog.records)
    assert any("Scored 1 pairs" in record.getMessage() for record in caplog.records)


def test_a_machine_reading_with_another_model_or_length_is_not_used(tmp_path, secret_file):
    seen = []
    server = service_module().make_server("127.0.0.1", 0, lambda pairs: seen.append(pairs) or [0.0] * len(pairs), secret_file,
                                          device="cuda", dtype="float16", max_length=512)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(ResearchPaused) as paused:
            remote(f"http://127.0.0.1:{server.server_address[1]}", secret_file).predict([("q", "p")])
    finally:
        server.shutdown()
        server.server_close()
    assert paused.value.code == GRAPHICS_UNAVAILABLE and "another model" in paused.value.detail and seen == []


def test_the_service_reads_as_the_search_reads():
    module = service_module()
    assert (module.RERANK_MODEL, module.RERANK_TOKENS, module.RERANK_BATCH_PAIRS) == (RERANK_MODEL, RERANK_TOKENS,
                                                                                     RERANK_BATCH_PAIRS)


# --- waking the machine (a stand-in machine and clock) -----------------------------------------------------------------------

class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Asleep:
    """A graphics machine behind a stand-in connection: not answering until woken and `boots` seconds have passed."""

    def __init__(self, clock, boots=90.0, wakes=AWAKE, model=RERANK_MODEL, drops=0):
        self.clock, self.boots, self.wakes, self.model, self.drops = clock, boots, wakes, model, drops
        self.up_at, self.asked, self.scored = None, [], []

    def wake(self):
        self.asked.append(self.clock())
        if self.wakes == AWAKE and self.up_at is None:
            self.up_at = self.clock() + self.boots
        return self.wakes

    def handle(self, request):
        if self.up_at is None or self.clock() < self.up_at:
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "model": self.model, "max_length": RERANK_TOKENS})
        if self.drops:
            self.drops -= 1
            self.up_at = None  # gone part-way, as when the budget's stop takes it
            raise httpx.ReadError("connection reset", request=request)
        pairs = json.loads(request.content)["pairs"]
        self.scored.append(pairs)
        return httpx.Response(200, json={"scores": [score(q, p) for q, p in pairs]})


def asleep_reranker(secret_file, machine, clock, **changes):
    return remote("http://10.0.1.20:8081", secret_file, waker=machine, transport=httpx.MockTransport(machine.handle), clock=clock,
                  sleep=clock.sleep, **changes)


def test_a_sleeping_machine_is_woken_and_waited_for_then_scores(secret_file):
    clock = Clock()
    machine = Asleep(clock, boots=95.0)
    scores = asleep_reranker(secret_file, machine, clock).predict([("q", "a passage")])
    assert scores == [score("q", "a passage")] and len(machine.scored) == 1
    assert 95.0 <= clock.now - 1000.0 < 95.0 + 10, "waited for it to boot, looking every few seconds"
    assert len(machine.asked) <= 4, "AWS is asked again only every 30 seconds while the machine boots"


def test_a_machine_the_budget_has_stopped_pauses_research_for_the_budget(secret_file):
    clock = Clock()
    machine = Asleep(clock, wakes=DENIED)
    with pytest.raises(ResearchPaused) as paused:
        asleep_reranker(secret_file, machine, clock).predict([("q", "p")])
    assert paused.value.code == BUDGET_PAUSED and machine.scored == [] and clock.now - 1000.0 < 10


def test_a_machine_that_does_not_wake_in_ten_minutes_pauses_research(secret_file):
    clock = Clock()
    machine = Asleep(clock, wakes=UNAVAILABLE)
    with pytest.raises(ResearchPaused) as paused:
        asleep_reranker(secret_file, machine, clock).predict([("q", "p")])
    assert paused.value.code == GRAPHICS_UNAVAILABLE and machine.scored == []
    assert 600.0 <= clock.now - 1000.0 <= 610.0, "ten minutes, the owner's limit (D176 (2))"
    assert 15 <= len(machine.asked) <= 21, "asked again every 30 seconds"


def test_once_paused_the_turns_other_searches_pause_at_once(secret_file):
    clock = Clock()
    machine = Asleep(clock, wakes=DENIED)
    reranker = asleep_reranker(secret_file, machine, clock)
    with pytest.raises(ResearchPaused):
        reranker.predict([("q", "p")])
    asked, now = len(machine.asked), clock.now
    with pytest.raises(ResearchPaused) as again:
        reranker.predict([("another question", "p")])
    assert again.value.code == BUDGET_PAUSED and len(machine.asked) == asked and clock.now == now
    clock.sleep(61)
    machine.wakes = AWAKE
    assert reranker.predict([("q", "p")]) == [score("q", "p")], "a minute on, it is tried afresh"


def test_a_machine_lost_part_way_is_woken_again_and_the_batch_sent_again(secret_file):
    clock = Clock()
    machine = Asleep(clock, boots=30.0, drops=1)
    assert asleep_reranker(secret_file, machine, clock).predict([("q", "p")]) == [score("q", "p")]
    assert len(machine.scored) == 1 and len(machine.asked) >= 2


# --- AWS's own client, with stubbed answers ------------------------------------------------------------------------------------

INSTANCE = "i-0123456789abcdef0"


def stubbed(lines):
    import boto3
    from botocore.config import Config
    from botocore.stub import Stubber
    client = boto3.client("ec2", region_name="ap-south-1", aws_access_key_id="stand-in", aws_secret_access_key="stand-in",
                          config=Config(retries={"max_attempts": 1, "mode": "standard"}))
    return MachineWaker(INSTANCE, "ap-south-1", gate(lines), client=client), Stubber(client)


def described(state):
    return {"Reservations": [{"Instances": [{"InstanceId": INSTANCE, "State": {"Name": state, "Code": 80}}]}]}


def test_a_stopped_machine_is_started_and_a_running_one_left_alone():
    lines = []
    waker, stub = stubbed(lines)
    stub.add_response("describe_instances", described("stopped"), {"InstanceIds": [INSTANCE]})
    stub.add_response("start_instances", {"StartingInstances": [{"InstanceId": INSTANCE, "CurrentState": {"Name": "pending",
                      "Code": 0}, "PreviousState": {"Name": "stopped", "Code": 80}}]}, {"InstanceIds": [INSTANCE]})
    stub.add_response("describe_instances", described("running"), {"InstanceIds": [INSTANCE]})
    with stub:
        assert waker.wake() == AWAKE
        assert waker.wake() == AWAKE
    stub.assert_no_pending_responses()
    assert len(lines) == 3 and all("sink=compute" in line and "processor=aws-machine-control" in line and "permitted" in line
                                   for line in lines)


def test_starting_refused_by_its_permissions_is_the_budgets_stop():
    waker, stub = stubbed([])
    stub.add_response("describe_instances", described("stopped"), {"InstanceIds": [INSTANCE]})
    stub.add_client_error("start_instances", service_error_code="UnauthorizedOperation", http_status_code=403,
                          expected_params={"InstanceIds": [INSTANCE]})
    with stub:
        assert waker.wake() == DENIED


def test_a_stopping_machine_or_short_capacity_is_asked_again_later():
    waker, stub = stubbed([])
    stub.add_response("describe_instances", described("stopping"), {"InstanceIds": [INSTANCE]})
    stub.add_response("describe_instances", described("stopped"), {"InstanceIds": [INSTANCE]})
    stub.add_client_error("start_instances", service_error_code="InsufficientInstanceCapacity", http_status_code=500,
                          expected_params={"InstanceIds": [INSTANCE]})
    stub.add_client_error("describe_instances", service_error_code="RequestLimitExceeded", http_status_code=503,
                          expected_params={"InstanceIds": [INSTANCE]})
    with stub:
        assert [waker.wake(), waker.wake(), waker.wake()] == [UNAVAILABLE] * 3
    stub.assert_no_pending_responses()


def test_a_machine_still_stopping_is_never_asked_to_start():
    class Recording:
        def __init__(self):
            self.calls = []

        def describe_instances(self, **asked):
            self.calls.append(("describe", asked))
            return described("stopping")

        def start_instances(self, **asked):
            self.calls.append(("start", asked))
            raise AssertionError("a stopping machine was asked to start")
    client = Recording()
    assert MachineWaker(INSTANCE, "ap-south-1", gate(), client=client).wake() == UNAVAILABLE
    assert [name for name, _ in client.calls] == ["describe"], "it is started once it has stopped, on a later look"


# --- the gate: the owner's two exceptions and nothing else ---------------------------------------------------------------------

def test_the_rerankers_gate_admits_the_owners_two_exceptions_and_nothing_else():
    own = gate()
    own.permit(Sink.INDEX, RERANKER_PROCESSOR, (DataClass.CLIENT_MATTER,), size_bytes=10)
    own.permit(Sink.COMPUTE, MACHINE_CONTROL_PROCESSOR, (DataClass.OPERATIONAL,))
    refused = [
        (Sink.COMPUTE, MACHINE_CONTROL_PROCESSOR, (DataClass.CLIENT_MATTER,)),  # a matter may never reach a machine's start
        (Sink.MODEL, RERANKER_PROCESSOR, (DataClass.CLIENT_MATTER,)),  # the reranker for reranking only
        (Sink.INDEX, RERANKER_PROCESSOR, (DataClass.RESTRICTED,)),
        (Sink.INDEX, "another-processor", (DataClass.CLIENT_MATTER,)),
    ]
    for sink, processor, classes in refused:
        with pytest.raises(EgressRefused):
            own.permit(sink, processor, classes)
    main = Gatekeeper(policy=egress_policy(ROOT))
    for sink, processor, classes in ((Sink.INDEX, RERANKER_PROCESSOR, (DataClass.CLIENT_MATTER,)),
                                     (Sink.COMPUTE, MACHINE_CONTROL_PROCESSOR, (DataClass.OPERATIONAL,))):
        with pytest.raises(EgressRefused):
            main.permit(sink, processor, classes)  # only the reranker's own gate admits them


def test_a_reranker_refused_by_the_policy_pauses_research_and_sends_nothing(machine, secret_file):
    closed = Gatekeeper(policy=egress_policy(ROOT))
    with pytest.raises(ResearchPaused) as paused:
        remote(machine["url"], secret_file, gate=closed).predict([("q", "p")])
    assert paused.value.code == GRAPHICS_UNAVAILABLE and machine["seen"] == []


# --- the search and the turn ---------------------------------------------------------------------------------------------------

def test_a_paused_reranker_pauses_the_search_instead_of_ranking_without_it():
    paused = {"provision": Failing("rerank", ResearchPaused(BUDGET_PAUSED)), "judgment": Collection("judgment")}
    with pytest.raises(ResearchPaused) as raised:
        HybridSearcher(paused).search(QUERIES)
    assert raised.value.code == BUDGET_PAUSED
    future, = HybridSearcher(paused).search_many([(QUERIES, None)])
    with pytest.raises(ResearchPaused):
        future.result()
    failing = {"provision": Failing("rerank", SearchUnavailable("provision reranking failed")), "judgment": Collection("judgment")}
    record = HybridSearcher(failing).search(QUERIES)  # any other failure costs only the order, recorded, as before
    assert any(issue["stage"] == "rerank" for issue in record["issues"])


@pytest.mark.parametrize("code", [GRAPHICS_UNAVAILABLE, BUDGET_PAUSED])
def test_research_paused_stops_the_turn_keeping_what_it_finished_and_continue_takes_it_up(store, monkeypatch, code):  # noqa: F811
    paused = HybridSearcher({"provision": Failing("rerank", ResearchPaused(code)), "judgment": AdjacentJudgment()})
    monkeypatch.setattr(core_turn, "searcher", lambda: paused)
    model = ScriptedModel(legal=True)  # the same model again on Continue, as the usage-limit turn does
    with pytest.raises(ConversationRefused) as refused:
        core_turn.run(store, model)
    error = refused.value
    assert (error.code, error.status, error.retryable, error.kept) == (code, 503, True, True)
    assert error.why == STOPS[code] + " What NM had finished is kept."
    matter, = store.list_for("owner").matters
    assert matter.brain_chat == () and shown_of(matter)["stopped"]["code"] == code
    monkeypatch.setattr(core_turn, "searcher", lambda: HybridSearcher({"provision": Collection(), "judgment": AdjacentJudgment()}))
    assert core_turn.run(store, model)["committed"] == "committed", "Continue takes it up"


def test_the_advocate_is_told_why_and_what_continue_needs_in_plain_words():
    assert STOPS[GRAPHICS_UNAVAILABLE].startswith("NM's research paused") and "budget" in STOPS[BUDGET_PAUSED]
    assert "Continue" in STOP_NEEDS[GRAPHICS_UNAVAILABLE] and "budget" in STOP_NEEDS[BUDGET_PAUSED]


def test_the_search_uses_the_machines_reranker_without_loading_weights_here(tmp_path):
    stand_in = object()
    models = _Models(tmp_path / "no-weights-here", reranker=stand_in)
    assert models._model("reranking") is stand_in
    with pytest.raises(SearchUnavailable):
        models._model("embedding")  # only the reranker moves; the embedding model still loads here
    local = HybridSearcher.local(root=tmp_path, corpus_dir=tmp_path, reranker=stand_in)
    assert all(collection.models.reranker is stand_in for collection in local.collections.values())


def test_the_machine_is_not_woken_when_the_server_starts(tmp_path, monkeypatch):
    class NeverCalled:
        def predict(self, *args, **kwargs):
            raise AssertionError("the graphics machine was asked to rerank at start")
    collection = HybridSearcher.local(root=tmp_path, corpus_dir=tmp_path, reranker=NeverCalled()).collections["provision"]
    for name in ("_open", "_word_index", "_vector_index", "suppressed_positions", "semantic_many"):
        monkeypatch.setattr(collection, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(collection.models, "load", lambda: None)
    collection.warm()  # pages in its own indices; the machine sleeps until an advocate's message wakes it


# --- the installation's settings -----------------------------------------------------------------------------------------------

def test_with_no_reranker_address_the_reranker_stays_in_this_process(tmp_path):
    assert build_reranker({}, tmp_path, Gatekeeper(policy=egress_policy(ROOT))) is None
    assert HybridSearcher.local(root=tmp_path, corpus_dir=tmp_path).collections["provision"].models.reranker is None


def test_a_reranker_needs_its_address_and_its_secret_file(tmp_path, secret_file):
    main = Gatekeeper(policy=egress_policy(ROOT))
    with pytest.raises(ValueError):
        build_reranker({"NM_RERANKER_INSTANCE": INSTANCE}, tmp_path, main)
    # The operator is told which setting to put right.
    with pytest.raises(ValueError, match="NM_RERANKER_SECRET_FILE"):
        build_reranker({"NM_RERANKER_URL": "http://10.0.1.20:8081"}, tmp_path, main)
    with pytest.raises(ValueError, match="NM_RERANKER_SECRET_FILE"):
        build_reranker({"NM_RERANKER_URL": "http://10.0.1.20:8081", "NM_RERANKER_SECRET_FILE": "relative.secret"}, tmp_path, main)
    built = build_reranker({"NM_RERANKER_URL": "http://10.0.1.20:8081", "NM_RERANKER_SECRET_FILE": str(secret_file),
                            "NM_RERANKER_INSTANCE": INSTANCE}, tmp_path, main)
    assert isinstance(built, RemoteReranker) and built.model == RERANK_MODEL and built.max_length == RERANK_TOKENS
    assert isinstance(built.waker, MachineWaker) and built.waker.region == "ap-south-1"
    assert built.tokenizer_folder == tmp_path / ".nm" / "models" / "BAAI__bge-reranker-v2-m3"


def test_a_message_wakes_the_machine_only_for_a_step_that_may_search():
    assert search_may_run(None), "end to end"
    assert search_may_run(stepwise.first()), "understanding may search early"
    assert search_may_run({"mode": stepwise.MODE, "allowed": ["research"], "n": 2, "waiting": None, "disputes": None})
    assert not search_may_run({"mode": stepwise.MODE, "allowed": ["write"], "n": 3, "waiting": None, "disputes": None})
    assert not search_may_run({"mode": stepwise.MODE, "allowed": ["finish"], "n": 4, "waiting": None, "disputes": None})


def test_waking_at_a_message_never_waits_and_never_fails_it(secret_file):
    started = threading.Event()

    class Slow:
        def wake(self):
            time.sleep(0.3)
            started.set()
            return AWAKE
    reranker = remote("http://10.0.1.20:8081", secret_file, waker=Slow())
    began = time.monotonic()
    reranker.wake_soon()
    assert time.monotonic() - began < 0.2 and started.wait(5)
