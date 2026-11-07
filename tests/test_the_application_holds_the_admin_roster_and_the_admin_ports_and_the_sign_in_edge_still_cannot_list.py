"""The application is composed with the Admin area's roster and three ports (plan AN.46, piece 46g; D117-D119, D126).

The settings name the admins; the Admin ports read the same directory, usage store and Admin record the application already uses; the
directory port the sign-in edge holds still has no way to list accounts (A1). Synthetic accounts, a scripted model."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from nm.app.composition import ADMIN_FILE, Application
from nm.arrive.admin_access import Level
from nm.arrive.admin_port import AuditEntry
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


def application(tmp_path, admins):
    directory = FileDirectory(tmp_path, key=KEY)
    for who in ("boss@example.test", "advocate@example.test"):
        directory.enrol(Enrolment(AdvocateIdentity(who, who), enrol(PASSWORD)))
    environment = {"NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                   "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                   "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts")}
    if admins is not None:
        environment["NM_ADMINS"] = admins
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    return Application(root=Path(__file__).resolve().parents[1], model=model, store=FileMatterStore(tmp_path, key=KEY),
                       directory=directory, mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(),
                       audit_root=tmp_path / "audit", environment=environment)


def test_the_settings_name_the_admins_and_everyone_else_is_an_advocate(tmp_path):
    app = application(tmp_path, "Boss@Example.test:admin, other@example.test:view-only")
    assert app.admin_roster.level_of("boss@example.test") is Level.ADMIN
    assert app.admin_roster.level_of("other@example.test") is Level.VIEW_ONLY
    assert app.admin_roster.level_of("advocate@example.test") is None


def test_without_the_setting_nobody_is_an_admin(tmp_path):
    assert application(tmp_path, None).admin_roster.named() == ()


def test_the_admin_directory_lists_the_accounts_the_application_holds(tmp_path):
    app = application(tmp_path, "boss@example.test:admin")
    listing = app.admin_directory.listing(NOW)
    assert [a.id for a in listing.accounts] == ["advocate@example.test", "boss@example.test"]


def test_the_admin_usage_reader_is_the_same_file_the_application_meters_into(tmp_path):
    app = application(tmp_path, "boss@example.test:admin")
    assert app.admin_usage.balances() == {}  # nothing used yet, and reading started nobody's trial
    app.usage.standing("advocate@example.test")
    assert len(app.admin_usage.balances()) == 1


def test_the_admin_record_is_made_at_its_first_use_and_not_before(tmp_path):
    app = application(tmp_path, "boss@example.test:admin")
    assert not (tmp_path / ADMIN_FILE).exists()
    entry = app.admin_record.append(AuditEntry(NOW, "boss@example.test", "allowance.add", "advocate@example.test",
                                               "Development account", "done"))
    assert (tmp_path / ADMIN_FILE).exists() and entry.id == 1 and app.admin_record.verify().ok


def test_the_directory_port_the_sign_in_edge_holds_still_cannot_list_who_exists(tmp_path):
    app = application(tmp_path, "boss@example.test:admin")
    for name in ("listing", "list_accounts", "accounts", "list_advocates"):
        with pytest.raises(AttributeError):
            getattr(app.directory, name)
