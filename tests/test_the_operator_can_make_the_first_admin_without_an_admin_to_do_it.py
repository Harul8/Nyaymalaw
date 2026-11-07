"""The operator tool that makes the first admin (plan AN.46; owner, 7 Nov 2026): an account is an Advocate until an Admin sets it, and the very
first Admin needs somewhere to start. `operations/admin.py` sets one account's user type from the operator host, writes the audit entry the
Users page would have written naming the operator, refuses an unknown account, and its `list` changes nothing."""
from __future__ import annotations

from pathlib import Path

import pytest

from nm.app.composition import Application
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from operations.admin import main
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
FIRST, OTHER = "first@example.test", "other@example.test"


@pytest.fixture
def app(tmp_path):
    directory = FileDirectory(tmp_path, key=KEY)
    for who in (FIRST, OTHER):
        directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    return Application(root=Path(__file__).resolve().parents[1], model=model, store=FileMatterStore(tmp_path, key=KEY), directory=directory,
                       mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(), audit_root=tmp_path / "audit", environment={
                           "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1",
                           "NM_EMBED_MODEL": "text-embedding-3-large", "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts")})


def run(app, *argv):
    return main(list(argv), application=app)


def test_the_first_admin_is_made_from_the_operator_host_and_the_account_is_then_an_admin_without_any_setting(app, capsys):
    assert app.admin_level_of(FIRST) is None
    assert run(app, "make-admin", "--account", FIRST.upper(), "--operator", "rahul", "--reason", "first admin") == 0
    assert "is now an Admin" in capsys.readouterr().out
    assert app.admin_level_of(FIRST).value == "admin" and app.admin_level_of(OTHER) is None
    entries = [(e.actor, e.action, e.target, e.reason, e.outcome) for e in reversed(app.admin_record.entries(limit=10))]
    assert entries == [("operator rahul", "user type admin", FIRST, "first admin", "started"),
                       ("operator rahul", "user type admin", FIRST, "first admin", "done")]


def test_it_can_be_taken_back_and_saying_it_twice_says_it_was_already_so(app, capsys):
    run(app, "make-admin", "--account", FIRST, "--operator", "rahul", "--reason", "x")
    assert run(app, "make-advocate", "--account", FIRST, "--operator", "rahul", "--reason", "y") == 0
    assert app.admin_level_of(FIRST) is None
    run(app, "make-advocate", "--account", FIRST, "--operator", "rahul", "--reason", "z")
    assert "already an Advocate" in capsys.readouterr().out


def test_an_unknown_account_and_a_bad_reason_change_nothing_and_the_log_says_so(app):
    with pytest.raises(SystemExit):
        run(app, "make-admin", "--account", "nobody@example.test", "--operator", "rahul", "--reason", "x")
    with pytest.raises(SystemExit):
        run(app, "make-admin", "--account", FIRST, "--operator", "rahul", "--reason", "  ")
    assert app.admin_level_of(FIRST) is None
    assert [e.outcome for e in reversed(app.admin_record.entries(limit=10))] == ["started", "not made"]


def test_listing_shows_each_accounts_type_and_changes_nothing(app, capsys):
    run(app, "make-admin", "--account", OTHER, "--operator", "rahul", "--reason", "x")
    capsys.readouterr()
    before = app.admin_record.verify().entries
    assert run(app, "list") == 0
    lines = dict(line.split("\t")[:2] for line in capsys.readouterr().out.strip().splitlines())
    assert lines == {FIRST: "advocate", OTHER: "admin"} and app.admin_record.verify().entries == before
