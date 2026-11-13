"""A hosted installation keeps nothing in the code folder (plan AN.52, 52e, D211; the review's F-15).

The store could already be put on a path of its own (NM_MATTER_STORE). The outgoing-data log could not: it was written
to .nm under the code, whatever the store's setting said. And the secret that seals every matter was either a setting
or a file NM made in .nm under the code. So a hosted server kept a year's log, and possibly the key, in the folder a
deployment replaces. Each now has a named path - NM_MATTER_STORE, NM_EGRESS_LOG_DIR, NM_MATTER_KEY_FILE - and an
application built with all three writes nothing under the code. Nothing changes where none is set.

Offline: the application built over a stand-in code folder that holds only the three files it reads from there.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from nm.app.composition import Application, SharedSealRefused
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file.matter_contracts import Matter
from tests.test_core_turn import ScriptedModel

pytestmark = pytest.mark.class_a

REPOSITORY = Path(__file__).resolve().parents[1]
READ_FROM_THE_CODE = ("docs/blueprint/evaluations.json", "docs/blueprint/processors.yaml", "pipeline/instrument_copies.json")
SECRET = "a-hosted-installation-secret-" + "k" * 24
MODEL = {"NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large"}


@pytest.fixture
def code(tmp_path):
    """A stand-in code folder: only what the application reads from under its code."""
    folder = tmp_path / "code"
    for name in READ_FROM_THE_CODE:
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPOSITORY / name, folder / name)
    return folder


def _files(folder):
    return sorted(str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_file())


def _built(code, settings):
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    return Application(root=code, model=model, legal_search=None, environment={**MODEL, **settings})


def _used(app):
    """What a served application writes: a matter saved, and a line of the outgoing-data log."""
    app.store.commit(Matter(id="m_hosted", advocate_id="advocate@example.test", title="Hosted", version=1), expected_version=0)
    app._egress_audit("one line of the outgoing-data log")


def test_with_the_three_paths_named_nothing_is_written_under_the_code(code, tmp_path):
    data, logs, key = tmp_path / "data", tmp_path / "logs", tmp_path / "secrets" / "matter.key"
    key.parent.mkdir()
    key.write_text(SECRET + "\n", encoding="utf8")
    before = _files(code)
    app = _built(code, {"NM_MATTER_STORE": str(data), "NM_EGRESS_LOG_DIR": str(logs), "NM_MATTER_KEY_FILE": str(key)})
    _used(app)
    assert _files(code) == before, "nothing new under the code"
    assert app.kept_in_code_folder() == ()
    assert [p.name for p in logs.iterdir() if p.name.startswith("egress-")], "the log is in its named folder"
    assert FileMatterStore(data, key=SECRET).load("m_hosted").title == "Hosted", "sealed with the secret in the named file"
    assert key.read_text(encoding="utf8") == SECRET + "\n", "the key file is read, never rewritten"


def test_with_nothing_named_everything_is_where_it_was(code):
    app = _built(code, {})
    _used(app)
    kept = _files(code)
    assert ".nm/matter.key" in kept and any(name.startswith(".nm/egress-") for name in kept)
    assert any(name.startswith(".nm/matters/") for name in kept)
    assert app.kept_in_code_folder() == ("the store", "the key", "the outgoing-data log")


def test_naming_only_the_store_leaves_the_log_under_the_code_and_says_so(code, tmp_path):
    app = _built(code, {"NM_MATTER_STORE": str(tmp_path / "data"), "NM_MATTER_KEY": SECRET})
    _used(app)
    assert any(name.startswith(".nm/egress-") for name in _files(code)), "as before this piece"
    assert app.kept_in_code_folder() == ("the outgoing-data log",), "the key is a setting: it is in no folder"


def test_a_named_path_inside_the_code_folder_is_still_in_the_code_folder(code, tmp_path):
    app = _built(code, {"NM_MATTER_STORE": str(tmp_path / "data"), "NM_MATTER_KEY": SECRET,
                        "NM_EGRESS_LOG_DIR": str(code / "logs")})
    assert app.kept_in_code_folder() == ("the outgoing-data log",)


def test_a_named_key_file_that_is_not_there_refuses_and_no_key_is_made(code, tmp_path):
    missing = tmp_path / "secrets" / "matter.key"
    with pytest.raises(RuntimeError, match="NM_MATTER_KEY_FILE"):
        _built(code, {"NM_MATTER_STORE": str(tmp_path / "data"), "NM_MATTER_KEY_FILE": str(missing)})
    assert not missing.exists() and ".nm/matter.key" not in _files(code), "a key made here would seal a second, empty store"


def test_a_named_key_file_that_is_empty_refuses(code, tmp_path):
    key = tmp_path / "matter.key"
    key.write_text("  \n", encoding="utf8")
    with pytest.raises(RuntimeError, match="NM_MATTER_KEY_FILE"):
        _built(code, {"NM_MATTER_STORE": str(tmp_path / "data"), "NM_MATTER_KEY_FILE": str(key)})


def test_the_secret_named_twice_refuses_whichever_they_hold(code, tmp_path):
    key = tmp_path / "matter.key"
    key.write_text(SECRET, encoding="utf8")
    with pytest.raises(RuntimeError, match="one place"):
        _built(code, {"NM_MATTER_STORE": str(tmp_path / "data"), "NM_MATTER_KEY_FILE": str(key), "NM_MATTER_KEY": SECRET})


def test_a_secret_from_a_file_is_still_refused_where_it_is_also_another_credential(code, tmp_path):
    key = tmp_path / "matter.key"
    key.write_text(SECRET, encoding="utf8")
    with pytest.raises(SharedSealRefused):
        _built(code, {"NM_MATTER_STORE": str(tmp_path / "data"), "NM_MATTER_KEY_FILE": str(key), "NM_MODEL_API_KEY": SECRET})


def test_the_folder_a_test_names_for_the_log_still_wins(code, tmp_path):
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=code, model=model, legal_search=None, audit_root=tmp_path / "audit",
                      environment={**MODEL, "NM_MATTER_KEY": SECRET, "NM_MATTER_STORE": str(tmp_path / "data"),
                                   "NM_EGRESS_LOG_DIR": str(tmp_path / "logs")})
    app._egress_audit("a line")
    assert any(p.name.startswith("egress-") for p in (tmp_path / "audit").iterdir()) and not (tmp_path / "logs").exists()
