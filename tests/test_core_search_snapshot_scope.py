"""One search checks its corpus snapshot on first use and on exit, not per read."""
import threading

import pytest

from nm.core_engine import retrieval

pytestmark = pytest.mark.class_a


def loaded(tmp_path, revisions):
    item = retrieval.LocalCollection(corpus_dir=tmp_path, lineage=tmp_path / "unused.json",
                                     doc_type="bare_act", models=None)
    item._revision = "r1"
    calls = []

    def revision():
        calls.append(threading.get_ident())
        return revisions[min(len(calls), len(revisions)) - 1]

    item.revision = revision
    return item, calls


def test_reads_inside_one_search_check_the_snapshot_once_and_again_on_exit(tmp_path):
    item, calls = loaded(tmp_path, ["r1"])
    with item.snapshot_scope():
        for _ in range(500):
            item._check_snapshot()
    assert len(calls) == 2


def test_a_change_during_the_search_fails_it_on_exit(tmp_path):
    item, calls = loaded(tmp_path, ["r1", "r2"])
    with pytest.raises(retrieval.SearchUnavailable):
        with item.snapshot_scope():
            item._check_snapshot()
            item._check_snapshot()
    assert len(calls) == 2


def test_outside_a_search_every_read_still_checks(tmp_path):
    item, calls = loaded(tmp_path, ["r1"])
    for _ in range(3):
        item._check_snapshot()
    assert len(calls) == 3
    item2, _ = loaded(tmp_path, ["r2"])
    with pytest.raises(retrieval.SearchUnavailable):
        item2._check_snapshot()


def test_another_threads_reads_are_not_covered_by_this_search(tmp_path):
    item, calls = loaded(tmp_path, ["r1"])
    with item.snapshot_scope():
        item._check_snapshot()
        other = threading.Thread(target=lambda: [item._check_snapshot() for _ in range(3)])
        other.start()
        other.join()
        item._check_snapshot()
    assert len(calls) == 1 + 3 + 1


def test_hybrid_search_runs_inside_each_collections_scope(monkeypatch):
    entered = []

    class Scoped:
        def __init__(self, kind):
            self.kind = kind

        def snapshot_scope(self):
            outer = self

            class Scope:
                def __enter__(self):
                    entered.append(("enter", outer.kind))

                def __exit__(self, *exc):
                    entered.append(("exit", outer.kind))
                    return False
            return Scope()

    searcher = retrieval.HybridSearcher({"provision": Scoped("provision"), "judgment": Scoped("judgment")})
    monkeypatch.setattr(searcher, "_search", lambda queries, instruments=None: entered.append(("search", len(queries))) or "result")
    assert searcher.search([{"query_id": "q", "text": "t"}]) == "result"
    assert entered == [("enter", "provision"), ("enter", "judgment"), ("search", 1),
                       ("exit", "judgment"), ("exit", "provision")]
