"""Readiness is measured, not stated (plan AN.52, 52a1, D207; the review's F-11).

Health answered 'ready' whatever was true: the held law was 'configured_unverified', and nothing asked whether the
store opens, an index answers or the scanner is there. The application now has one owner of readiness, which
performs a cheap real act for each capability and reports it as ready, not ready (with why, in plain words) or not
checked - never 'ready' for something nobody tried. Offline: the application built over a stand-in code folder;
stand-ins for the search and the scanner; no model call.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from nm.app import composition
from nm.app.composition import NOT_CHECKED, NOT_READY, READY, Application
from nm.core_engine.retrieval import SearchUnavailable
from nm.work_the_file.matter_contracts import Matter
from tests.test_core_turn import ScriptedModel

pytestmark = pytest.mark.class_a

REPOSITORY = Path(__file__).resolve().parents[1]
READ_FROM_THE_CODE = ("docs/blueprint/evaluations.json", "docs/blueprint/processors.yaml", "pipeline/instrument_copies.json")
SECRET = "a-readiness-control-secret-" + "k" * 24
MODEL = {"NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large"}
STORE, PROVISIONS, JUDGMENTS, SCANNER = "the store", "the held law: provision", "the held law: judgment", "the malware scanner"
MAIL, AI = "account mail", "the AI service"


@pytest.fixture
def code(tmp_path):
    folder = tmp_path / "code"
    for name in READ_FROM_THE_CODE:
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPOSITORY / name, folder / name)
    return folder


class _Collection:
    def __init__(self, fails=None):
        self.fails, self.warmed = fails, 0

    def warm(self):
        self.warmed += 1
        if self.fails:
            raise self.fails


def _search(provision=None, judgment=None):
    return SimpleNamespace(collections={"provision": _Collection(provision), "judgment": _Collection(judgment)})


def _built(code, tmp_path, *, secret=SECRET, **given):
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    given.setdefault("legal_search", _search())
    return Application(root=code, model=model, environment={
        **MODEL, "NM_MATTER_KEY": secret, "NM_MATTER_STORE": str(tmp_path / "data"),
        "NM_EGRESS_LOG_DIR": str(tmp_path / "logs")}, **given)


def _scanner(app, monkeypatch, verdict):
    monkeypatch.setattr(app.documents.checker, "check", lambda data: verdict)


def _save(app, matter_id="m_ready"):
    app.store.commit(Matter(id=matter_id, advocate_id="advocate@example.test", title="Ready", version=1), expected_version=0)


def test_with_an_empty_library_and_no_scanner_each_is_named_not_ready_with_why(code, tmp_path):
    """The review's smallest failing test. The real search over a code folder that holds no index, and no scanner set."""
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=code, model=model, environment={
        **MODEL, "NM_MATTER_KEY": SECRET, "NM_MATTER_STORE": str(tmp_path / "data"), "NM_EGRESS_LOG_DIR": str(tmp_path / "logs"),
        "NM_CORPUS_DIR": str(tmp_path / "empty-library")})
    measured = app.readiness()
    for name in (PROVISIONS, JUDGMENTS, SCANNER):
        assert measured[name]["state"] == NOT_READY and measured[name]["why"], name
    assert set(composition.not_ready(measured)) == {PROVISIONS, JUDGMENTS, SCANNER}
    assert measured[STORE]["state"] == READY


def test_every_capability_is_one_of_three_states_and_none_is_ready_unmeasured(code, tmp_path, monkeypatch):
    app = _built(code, tmp_path)
    before = app.readiness(measure=False)
    assert set(before) == {STORE, PROVISIONS, JUDGMENTS, SCANNER, MAIL, AI}
    assert {entry["state"] for entry in before.values()} == {NOT_CHECKED}, "nothing is ready that nobody tried"
    _scanner(app, monkeypatch, ("clear", ""))
    measured = app.readiness()
    assert {entry["state"] for entry in measured.values()} <= {READY, NOT_READY, NOT_CHECKED}
    assert [measured[name]["state"] for name in (STORE, PROVISIONS, JUDGMENTS, SCANNER)] == [READY] * 4
    assert composition.not_ready(measured) == ()
    assert app.readiness(measure=False) == measured, "what was measured is kept for a health request to show"


def test_what_has_no_free_check_yet_is_said_as_not_checked_with_why(code, tmp_path):
    measured = _built(code, tmp_path).readiness()
    for name in (MAIL, AI):
        assert measured[name]["state"] == NOT_CHECKED and measured[name]["why"], name


def test_the_search_is_tried_by_its_own_act_and_a_collection_that_fails_is_named_alone(code, tmp_path):
    search = _search(judgment=SearchUnavailable("The judgment index could not be loaded"))
    measured = _built(code, tmp_path, legal_search=search).readiness()
    assert search.collections["provision"].warmed == 1 and search.collections["judgment"].warmed == 1
    assert measured[PROVISIONS]["state"] == READY
    assert measured[JUDGMENTS] == {"state": NOT_READY, "why": "The judgment index could not be loaded"}


def test_a_library_that_does_not_import_is_not_ready_and_a_programming_error_is_not_hidden(code, tmp_path):
    missing = _built(code, tmp_path, legal_search=_search(provision=ImportError("No module named 'faiss'"))).readiness()
    assert missing[PROVISIONS]["state"] == NOT_READY and "faiss" in missing[PROVISIONS]["why"]
    with pytest.raises(TypeError):
        _built(code, tmp_path, legal_search=_search(provision=TypeError("a mistake in the code"))).readiness()


def test_no_search_connected_is_not_ready_and_a_search_with_no_check_is_not_checked(code, tmp_path):
    none = _built(code, tmp_path, legal_search=None).readiness()
    assert none[PROVISIONS]["state"] == NOT_READY and none[JUDGMENTS]["state"] == NOT_READY
    plain = _built(code, tmp_path, legal_search=SimpleNamespace()).readiness()
    assert plain[PROVISIONS]["state"] == NOT_CHECKED and plain[JUDGMENTS]["state"] == NOT_CHECKED


@pytest.mark.parametrize("verdict, state", [
    (("clear", ""), READY),
    (("unavailable", "no malware checker is set up on this installation"), NOT_READY),
    (("held", "Probe.Signature"), NOT_READY),
])
def test_the_scanner_is_asked_about_a_harmless_probe(code, tmp_path, monkeypatch, verdict, state):
    app = _built(code, tmp_path)
    asked = []
    monkeypatch.setattr(app.documents.checker, "check", lambda data: (asked.append(data), verdict)[1])
    measured = app.readiness()[SCANNER]
    assert measured["state"] == state and len(asked) == 1 and asked[0]
    assert (state == READY) or measured["why"]


def test_the_store_is_ready_when_empty_and_when_a_saved_matter_opens(code, tmp_path):
    app = _built(code, tmp_path)
    assert app.readiness()[STORE]["state"] == READY
    _save(app)
    assert app.readiness()[STORE]["state"] == READY


def test_the_store_is_not_ready_under_a_secret_that_opens_none_of_its_matters(code, tmp_path):
    _save(_built(code, tmp_path))
    other = _built(code, tmp_path, secret="another-secret-entirely-" + "z" * 24)
    measured = other.readiness()[STORE]
    assert measured["state"] == NOT_READY and "secret" in measured["why"]
    assert SECRET not in str(measured) and "another-secret" not in str(measured)


def test_one_damaged_matter_among_good_ones_does_not_make_the_store_not_ready(code, tmp_path):
    app = _built(code, tmp_path)
    for name in ("m_a", "m_b", "m_c"):
        _save(app, name)
    (tmp_path / "data" / "matters" / "m_a.nm").write_bytes(b"x")
    assert app.readiness()[STORE]["state"] == READY, "a damaged file is its owner's to be told of; the store still opens"


def test_a_store_folder_that_takes_no_write_is_not_ready(code, tmp_path, monkeypatch):
    app = _built(code, tmp_path)

    def refuse(*args, **kwargs):
        raise PermissionError("read-only")
    monkeypatch.setattr(composition.tempfile, "mkstemp", refuse)
    measured = app.readiness()[STORE]
    assert measured["state"] == NOT_READY and "write" in measured["why"]
