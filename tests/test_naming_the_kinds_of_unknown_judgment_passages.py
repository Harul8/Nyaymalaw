"""The passages of the judgment store whose kind the earlier labeller could not name are named by a model, as a separate job the owner runs
(plan AN.45, D105). The default is an estimate and makes no call; a run needs the owner's spend limit and stops at it; the labels go to a
side file and into the store only on apply (server stopped), and undo puts them back; and code keeps of the model's answer only a passage it
was asked about, named once, with a kind we keep. An invented store and a scripted model prove the job's arithmetic and its refusals, not
the model's reading of a judgment: that is measured by a bounded run the owner sees (kinds.jsonl, the look stage)."""
import json
import sqlite3
from types import SimpleNamespace

import pytest

from nm.core_engine import retrieval
from nm.shared.model_config import token_pricing
from nm.shared.model_port import ModelError, UsageLimitReached
from pipeline import classify_judgment_paragraphs as job

pytestmark = pytest.mark.class_a

# (case, kind, text): case A has three unknown passages among five, B one unknown, C none.
PASSAGES = [("A", "facts", "The appellant bought the land in 1990 under a registered deed."),
            ("A", "unknown", "The respondent says the deed was never acted upon by the parties."),
            ("A", "unknown", "We hold that a registered deed passes title when delivered."),
            ("A", "ratio", "A sale deed once registered and delivered cannot be avoided later."),
            ("A", "unknown", "The appeal is therefore allowed with costs."),
            ("A", "order", "Costs of Rs. 5,000 to be paid within a month."),
            ("B", "unknown", "Heard counsel on both sides at length today."),
            ("B", "reasoning", "The court looks to the substance of the dealing between them."),
            ("B", "arguments", "Counsel contends the deed was a sham."),
            ("C", "facts", "The facts are not in dispute."),
            ("C", "facts", "The tenant went into possession in 2001.")]


def words(texts):
    return [len(text.split()) for text in texts]


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "vector_store" / "judgments_t"
    path.mkdir(parents=True)
    con = sqlite3.connect(path / "judgments_t.db")
    con.execute("create table chunks (doc_type text, pos integer, chunk_id text, act_id text, case_id text, parent_chunk_id text, "
                "atom_type text, section_number text, blob text, primary key (doc_type, pos))")
    for pos, (case, kind, text) in enumerate(PASSAGES):
        blob = {"chunk_id": f"{case}_P{pos:04d}", "case_id": case, "paragraph_type": kind, "full_text": text, "doc_type": "case_law"}
        con.execute("insert into chunks values ('case_law', ?, ?, null, ?, null, ?, null, ?)", (pos, blob["chunk_id"], case, kind, json.dumps(blob)))
    con.commit()
    con.close()
    return path


def kinds_in(folder):
    con = sqlite3.connect(folder / "judgments_t.db")
    try:
        return [row[0] for row in con.execute("select atom_type from chunks order by pos")]
    finally:
        con.close()


class Model:
    """A scripted model: answer(user) -> the answer's data (or an exception to raise); every call costs `cost`."""

    def __init__(self, answer, cost=0.01):
        self.answer, self.cost, self.calls = answer, cost, []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append(prompt.user)
        data = self.answer(prompt.user)
        if isinstance(data, Exception):
            raise data
        return SimpleNamespace(data=data, usable=True, model="gpt-6-luna", usage=SimpleNamespace(cost_usd=self.cost))


def everything_is(kind):
    """An answer naming every passage marked TO LABEL as `kind`."""
    def answer(user):
        numbers = [int(line[1:line.index("]")]) for line in user.splitlines() if line.startswith("[") and line.endswith(" TO LABEL")]
        return {"passages": [{"number": n, "kind": kind} for n in numbers]}
    return answer


def test_a_window_is_a_run_of_one_judgments_passages_that_holds_an_unknown_one(folder):
    store = job.store_of(folder)
    whole = job.plan(store)
    assert [(case, [pos for pos, _, _ in run]) for case, run in whole] == [("A", [0, 1, 2, 3, 4, 5]), ("B", [6, 7, 8])], "C has none unknown"
    assert [flag for _, _, flag in whole[0][1]] == [False, True, True, False, True, False]
    small = job.plan(store, window_chars=100)
    assert all(sum(size for _, size, _ in run) <= 100 + max(size for _, size, _ in run) for _, run in small) and len(small) > len(whole)
    assert all(any(unknown for _, _, unknown in run) for _, run in small), "a run with none to label is not read"
    window = job.read_window(store, whole[0][1])
    assert [(pos, chunk, unknown) for pos, chunk, _, unknown in window] == [
        (0, "A_P0000", False), (1, "A_P0001", True), (2, "A_P0002", True), (3, "A_P0003", False), (4, "A_P0004", True), (5, "A_P0005", False)]
    text = job.ask_text(window)
    assert text.startswith("[1]\nThe appellant") and "[2] TO LABEL\nThe respondent says" in text and "[3] TO LABEL\nWe hold" in text


def test_the_estimate_is_the_sum_for_every_unknown_passage_at_the_models_price_and_makes_no_call(folder):
    result = job.estimate(job.store_of(folder), words, sample=11)
    assert (result["passages"], result["unknown"], result["windows"]) == (11, 4, 2)
    chars = sum(len(text) for case, _, text in PASSAGES if case in "AB")
    ratio = sum(len(text.split()) for _, _, text in PASSAGES) / sum(len(text) for _, _, text in PASSAGES)
    tokens_in = int(chars * ratio) + 2 * job.PROMPT_OVERHEAD
    assert result["tokens in"] == tokens_in and result["tokens out (at most)"] == 4 * job.OUTPUT_PER_PASSAGE
    assert result["cost in USD (no discount for the repeated prompt)"] == round(token_pricing(job.MODEL).cost_usd(tokens_in, 64), 2)
    assert result["model"] == "gpt-6-luna"
    assert sorted(p.name for p in folder.iterdir()) == ["judgments_t.db"], "nothing written"


def test_a_run_without_the_owners_spend_limit_is_refused():
    with pytest.raises(SystemExit, match="needs --spend-limit"):
        job.main(["--folder", "judgments_t", "--stage", "run"])
    with pytest.raises(SystemExit, match="needs --spend-limit"):
        job.main(["--folder", "judgments_t", "--stage", "run", "--spend-limit", "0"])


def test_code_keeps_of_the_models_answer_only_a_passage_it_was_asked_about_named_once_with_a_kind_we_keep(folder):
    window = job.read_window(job.store_of(folder), job.plan(job.store_of(folder))[0][1])       # to label: 2, 3 and 5
    answer = {"passages": [{"number": 2, "kind": "facts"}, {"number": 1, "kind": "reasoning"}, {"number": 2, "kind": "ratio"},
                           {"number": 9, "kind": "order"}, {"number": 3, "kind": "unclear"}, {"number": True, "kind": "order"}]}
    kept, refused = job.checked(window, answer)
    assert kept == [{"pos": 1, "chunk_id": "A_P0001", "kind": "facts"}]
    assert sorted(refused) == sorted(["a passage it was not asked about", "a passage named twice", "a passage it was not asked about",
                                      "left unclear", "a passage it was not asked about", "not named"])
    assert job.checked(window, {"passages": []}) == ([], ["not named"] * 3) and job.checked(window, "nonsense") == ([], ["not named"] * 3)


def test_a_run_writes_labels_to_a_side_file_and_never_touches_the_store(folder):
    before = (folder / "judgments_t.db").read_bytes()
    model = Model(everything_is("reasoning"))
    done = job.run_stage(folder, model, spend_limit=1.0)
    assert done["windows read this run"] == len(model.calls) == 2 and done["passages labelled"] == 4
    labels = [json.loads(line) for line in (folder / "kinds.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(item["pos"], item["kind"]) for item in labels] == [(1, "reasoning"), (2, "reasoning"), (4, "reasoning"), (6, "reasoning")]
    assert (folder / "judgments_t.db").read_bytes() == before and kinds_in(folder)[1] == "unknown"
    assert done["spent in all (USD)"] == 0.02 and done["model"] == "gpt-6-luna"
    assert all(isinstance(call, str) and "TO LABEL" in call for call in model.calls)


def test_a_run_stops_at_the_spend_limit_and_goes_on_from_where_it_stopped_reading_no_window_twice(folder):
    model = Model(everything_is("facts"), cost=0.20)
    first = job.run_stage(folder, model, spend_limit=0.50, window_chars=60)
    assert first["windows read this run"] == 2 and "could pass the spend limit" in first["stopped because"]
    assert first["spent in all (USD)"] == 0.4
    second = job.run_stage(folder, model, spend_limit=5.0, window_chars=60)
    total = len(job.plan(job.store_of(folder), 60))
    assert second["windows read this run"] == total - 2 and second["windows done in all"] == total == len(model.calls)
    assert len(set(model.calls)) == len(model.calls), "no window was read twice"
    keys = (folder / "kinds.windows.txt").read_text(encoding="utf-8").split()
    assert len(keys) == len(set(keys)) == total, "each window is listed once, in a list that is added to and not rewritten"
    assert "done" not in json.loads((folder / "kinds.progress.json").read_text(encoding="utf-8"))
    again = job.run_stage(folder, model, spend_limit=5.0, window_chars=60)
    assert again["windows read this run"] == 0 and len(model.calls) == total
    assert [json.loads(line)["pos"] for line in (folder / "kinds.jsonl").read_text(encoding="utf-8").splitlines()] == [1, 2, 4, 6]


def test_a_run_reads_as_many_windows_as_it_is_told_and_no_more(folder):
    model = Model(everything_is("order"))
    done = job.run_stage(folder, model, spend_limit=5.0, windows=1)
    assert done["windows read this run"] == len(model.calls) == 1 and "1 windows asked for" in done["stopped because"]


def test_a_window_the_model_cannot_answer_costs_that_window_and_not_the_run_but_a_usage_limit_stops_it(folder):
    answers = iter([ModelError("down"), None])

    def answer(user):
        error = next(answers)
        return error if error is not None else everything_is("facts")(user)
    done = job.run_stage(folder, Model(answer), spend_limit=5.0)
    assert done["windows failed"] == 1 and done["windows done in all"] == 1 and done["passages labelled"] == 1
    assert json.loads((folder / "kinds.progress.json").read_text(encoding="utf-8"))["failed"][0]["why"] == "ModelError"
    other = folder.parent / "judgments_u"
    other.mkdir()
    (other / "judgments_u.db").write_bytes((folder / "judgments_t.db").read_bytes())
    stopped = job.run_stage(other, Model(lambda user: UsageLimitReached("no credit")), spend_limit=5.0)
    assert "usage limit" in stopped["stopped because"] and stopped["windows read this run"] == 0


def test_look_shows_the_labels_by_kind_with_passages_to_read(folder):
    job.run_stage(folder, Model(everything_is("headnote")), spend_limit=1.0)
    seen = job.look_stage(folder, examples=2)
    assert seen["labels"] == 4 and seen["by kind"]["headnote"] == 4 and seen["by kind"]["facts"] == 0
    assert len(seen["examples"]["headnote"]) == 2 and seen["examples"]["headnote"][0].startswith("The respondent says")
    with pytest.raises(SystemExit, match="no labels yet"):
        job.look_stage(folder.parent)


def test_apply_names_only_a_passage_still_unknown_says_who_named_it_and_undo_puts_it_back(folder):
    job.run_stage(folder, Model(everything_is("arguments")), spend_limit=1.0)
    with pytest.raises(SystemExit, match="server is up"):
        job.apply_stage(folder, running=lambda: True)
    # One of the passages was named by someone else between the run and the apply.
    con = sqlite3.connect(folder / "judgments_t.db")
    con.execute("update chunks set atom_type='ratio' where pos=2")
    con.commit()
    con.close()
    done = job.apply_stage(folder, running=lambda: False)
    assert done["passages named"] == 3 and done["labels not applied (no longer unknown or not there)"] == 1
    assert kinds_in(folder) == ["facts", "arguments", "ratio", "ratio", "arguments", "order", "arguments", "reasoning", "arguments", "facts", "facts"]
    con = sqlite3.connect(folder / "judgments_t.db")
    blob = json.loads(con.execute("select blob from chunks where pos=1").fetchone()[0])
    con.close()
    assert blob["paragraph_type"] == "arguments" and "gpt-6-luna" in blob["kind_by"]
    with pytest.raises(SystemExit, match="applied already"):
        job.apply_stage(folder, running=lambda: False)
    with pytest.raises(SystemExit, match="server is up"):
        job.undo_stage(folder, running=lambda: True)
    assert job.undo_stage(folder, running=lambda: False) == {"passages put back to unknown": 3}
    assert kinds_in(folder)[1] == kinds_in(folder)[4] == kinds_in(folder)[6] == "unknown" and kinds_in(folder)[2] == "ratio"
    con = sqlite3.connect(folder / "judgments_t.db")
    assert "kind_by" not in json.loads(con.execute("select blob from chunks where pos=1").fetchone()[0])
    con.close()
    with pytest.raises(SystemExit, match="nothing was applied"):
        job.undo_stage(folder, running=lambda: False)


def test_the_prompt_names_every_kind_asks_for_a_loop_and_the_schema_allows_exactly_those_kinds():
    for kind in (*job.KINDS, "unclear"):
        assert f"- {kind}:" in job.PROMPT, kind
    assert "Work in a loop" in job.PROMPT
    allowed = job.SCHEMA["properties"]["passages"]["items"]["properties"]["kind"]["enum"]
    assert allowed == [*job.KINDS, "unclear"]
    assert {"facts", "arguments", "order"} <= set(job.KINDS), "the kinds search treats as reporting rather than deciding can be named"
    assert retrieval.REPORTED_PARAGRAPHS - {"argument"} <= set(job.KINDS)
