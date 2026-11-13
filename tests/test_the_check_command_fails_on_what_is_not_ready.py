"""The check command fails on what is not ready, and names it (plan AN.52, 52a2, D207; the review's F-11).

`python -m nm.app.main --check` printed health and exited 0 whenever the application could be built, since health
always said 'ready'. It now measures readiness (52a1): it prints each capability's state, names each one that is
not ready on its own line with why, and exits non-zero for any. What is 'not checked' is said and does not fail the
check: nothing was learned about it. It starts no server and takes nothing up.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from nm.app import main
from nm.app.composition import NOT_CHECKED, NOT_READY, READY, Application
from tests.test_core_turn import ScriptedModel

pytestmark = pytest.mark.class_a

REPOSITORY = Path(__file__).resolve().parents[1]
READ_FROM_THE_CODE = ("docs/blueprint/evaluations.json", "docs/blueprint/processors.yaml", "pipeline/instrument_copies.json")


def _stand_in(measured, kept=()):
    return lambda: SimpleNamespace(health=lambda: {"runtime": "ready"}, readiness=lambda: measured,
                                   kept_in_code_folder=lambda: kept)


def _never_serves(monkeypatch):
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: pytest.fail("a check must not start the server"))
    monkeypatch.setattr(main.step_worker, "take_the_store", lambda *args, **kwargs: pytest.fail("a check takes no store"))


def test_everything_ready_exits_zero_and_prints_each_state(monkeypatch, capsys):
    _never_serves(monkeypatch)
    measured = {"the store": {"state": READY, "why": ""}, "the malware scanner": {"state": READY, "why": ""}}
    monkeypatch.setattr(main, "Application", _stand_in(measured))
    assert main.main(["--check"]) == 0
    printed = capsys.readouterr()
    assert json.loads(printed.out)["readiness"] == measured
    assert "NOT READY" not in printed.err


def test_what_is_not_ready_is_named_with_why_and_the_check_exits_non_zero(monkeypatch, capsys):
    _never_serves(monkeypatch)
    measured = {"the store": {"state": READY, "why": ""},
                "the held law: judgment": {"state": NOT_READY, "why": "The judgment index could not be loaded"},
                "the malware scanner": {"state": NOT_READY, "why": "no malware checker is set up on this installation"}}
    monkeypatch.setattr(main, "Application", _stand_in(measured))
    assert main.main(["--check"]) == 1
    said = capsys.readouterr().err.splitlines()
    assert "NOT READY: the held law: judgment: The judgment index could not be loaded" in said
    assert "NOT READY: the malware scanner: no malware checker is set up on this installation" in said
    assert not any("the store" in line for line in said)


def test_what_is_not_checked_is_said_and_does_not_fail_the_check(monkeypatch, capsys):
    _never_serves(monkeypatch)
    measured = {"the store": {"state": READY, "why": ""},
                "account mail": {"state": NOT_CHECKED, "why": "no check of account mail is built yet"}}
    monkeypatch.setattr(main, "Application", _stand_in(measured))
    assert main.main(["--check"]) == 0
    assert "NOT CHECKED: account mail: no check of account mail is built yet" in capsys.readouterr().err.splitlines()


def test_what_is_kept_under_the_code_is_said(monkeypatch, capsys):
    _never_serves(monkeypatch)
    monkeypatch.setattr(main, "Application", _stand_in({"the store": {"state": READY, "why": ""}},
                                                       kept=("the key", "the outgoing-data log")))
    assert main.main(["--check"]) == 0
    printed = capsys.readouterr()
    assert json.loads(printed.out)["kept_in_code_folder"] == ["the key", "the outgoing-data log"]
    assert any(line.startswith("KEPT UNDER THE CODE: the key, the outgoing-data log") for line in printed.err.splitlines())


def test_the_real_application_with_an_empty_library_and_no_scanner_fails_the_check_and_names_each(
        monkeypatch, capsys, tmp_path):
    """The review's smallest failing test, through the command itself."""
    _never_serves(monkeypatch)
    code = tmp_path / "code"
    for name in READ_FROM_THE_CODE:
        (code / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPOSITORY / name, code / name)

    def built():
        model = ScriptedModel(legal=True)
        model.provider = "scripted"
        return Application(root=code, model=model, environment={
            "NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
            "NM_MATTER_KEY": "a-check-command-control-" + "k" * 24, "NM_MATTER_STORE": str(tmp_path / "data"),
            "NM_EGRESS_LOG_DIR": str(tmp_path / "logs"), "NM_CORPUS_DIR": str(tmp_path / "empty-library")})
    monkeypatch.setattr(main, "Application", built)
    assert main.main(["--check"]) == 1
    said = capsys.readouterr().err
    for name in ("the held law: provision", "the held law: judgment", "the malware scanner"):
        assert f"NOT READY: {name}: " in said, name
    assert "NOT READY: the store" not in said
