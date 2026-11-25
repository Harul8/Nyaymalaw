"""An Admin closes an account at the advocate's written request (plan AN.53, 53h7c; D241's closed account, with D246's
safeguards: two steps, the address typed, a reason naming the request, an audit entry, and neither an admin's account nor one's
own).

The route is a change like the others (D116): the Admin's level permits it, they gave their password just now in this session,
the reason is one line, and the audit takes an entry before and after. More is asked of a closure than of any other change,
since it cannot be undone: the account must already be suspended (the first step, which Reinstate undoes); the Admin types the
account's address; an admin's account, and one's own, are never closed from here; and nothing goes while NM works on one of the
account's conversations. Then the application closes it (53h7b): its conversations and papers, then its record, so that it can
no longer sign in, and what this process held of its conversations is let go of. Another account is untouched.

Through the real login and the real stack, on synthetic accounts; no model call beyond the scripted stand-in.
"""
from __future__ import annotations

import pytest

from nm.app import api
from nm.arrive.admin_access import Action, Level, permits
from tests.served_application import PASSWORD
from tests.test_an_admins_change_is_made_only_with_the_level_the_password_a_reason_and_an_audit_entry import (  # noqa: F401
    ADMIN,
    ADVOCATE,
    OTHER,
    VIEWER,
    audit,
    served,
)
from tests.test_core_document_routes import upload
from tests.test_core_documents import Checker

pytestmark = pytest.mark.class_a
REQUEST = "Written request of 12 Nov 2026 from the advocate"


def _used(served, who):
    """An account with a conversation and a paper, its history read once so that this process holds its line."""
    client = served.login(who)
    reply = client.post("/api/turn", json={"message": "Is a cheque returned for insufficient funds an offence?",
                                           "turn_id": f"turn-{who.split('@')[0]}"})
    assert reply.status_code == 200, reply.text
    assert upload(client).status_code == 201
    assert client.get("/api/chats").status_code == 200
    return client


@pytest.fixture
def ready(served):
    served.app.documents.checker = Checker()
    _used(served, ADVOCATE)
    _used(served, OTHER)
    return served


def _matters(served, who):
    return ({entry[0] for entry in served.app.store.saved_files_for(who)}
            | {said["matter_id"] for said in served.app.store.deleted_for(who)})


def _suspend(admin, who=ADVOCATE):
    assert admin.post(f"/api/admin/users/{who}/suspend", json={"reason": "Asked to close the account"}).status_code == 200


def close(client, who=ADVOCATE, **changes):
    body = {"address": who, "reason": REQUEST}
    body.update(changes)
    return client.post(f"/api/admin/users/{who}/close", json=body)


def test_closing_is_an_action_only_an_admin_may_make():
    assert Action.CLOSE.value == "close"
    assert permits(Level.ADMIN, Action.CLOSE) and not permits(Level.VIEW_ONLY, Action.CLOSE) and not permits(None, Action.CLOSE)


def test_an_admin_closes_a_suspended_account_and_it_can_no_longer_sign_in(ready):
    served = ready
    admin = served.login(ADMIN, confirmed=True)
    _suspend(admin)
    mine, others = _matters(served, ADVOCATE), _matters(served, OTHER)
    assert mine and any(matter in api._LISTED for matter in mine)
    reply = close(admin)
    assert reply.status_code == 200, reply.text
    said = reply.json()
    assert said["closed"] is True and said["conversations"] == len(mine) and said["papers"] == 1
    assert "erased" not in said, "the matter IDs are the process's own business, not the page's"
    assert _matters(served, ADVOCATE) == set() and not any(matter in api._LISTED or matter in api._READ for matter in mine)
    assert _matters(served, OTHER) == others
    login = served.asgi and __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(served.asgi)
    refused = login.post("/api/login", headers={"origin": "http://testserver"},
                         json={"advocate_id": ADVOCATE, "password": PASSWORD})
    assert refused.status_code == 401, "the record is gone, so is its credential"
    assert [entry[1:] for entry in audit(served)][-2:] == [("close", ADVOCATE, REQUEST, "started"),
                                                           ("close", ADVOCATE, REQUEST, "done")]


def test_an_account_not_suspended_first_is_refused_and_nothing_goes(ready):
    served = ready
    admin = served.login(ADMIN, confirmed=True)
    before = _matters(served, ADVOCATE)
    reply = close(admin)
    assert reply.status_code == 409 and "Suspend" in reply.json()["detail"]
    assert _matters(served, ADVOCATE) == before


def test_the_address_must_be_typed_as_the_accounts_own(ready):
    served = ready
    admin = served.login(ADMIN, confirmed=True)
    _suspend(admin)
    before, entries = _matters(served, ADVOCATE), len(audit(served))
    for typed in ("", OTHER, "advocate@example"):
        reply = close(admin, address=typed)
        assert reply.status_code == 422, typed
    assert close(admin, address=ADVOCATE.upper()).status_code == 200, "an address is the same address in any case"
    assert len(audit(served)) == entries + 2 and before


def test_an_admins_account_and_ones_own_are_never_closed_from_here(ready):
    served = ready
    admin = served.login(ADMIN, confirmed=True)
    for who in (VIEWER, ADMIN):
        reply = close(admin, who)
        assert reply.status_code == 409, who
    assert served.app.directory.identity(VIEWER) is not None and served.app.directory.identity(ADMIN) is not None


def test_a_view_only_admin_and_an_advocate_cannot_close_an_account(ready):
    served = ready
    viewer = served.login(VIEWER, confirmed=True)
    assert close(viewer).status_code == 403
    advocate = served.login(OTHER)
    assert close(advocate).status_code == 404
    assert _matters(served, ADVOCATE)


def test_a_closure_without_a_reason_is_refused(ready):
    served = ready
    admin = served.login(ADMIN, confirmed=True)
    _suspend(admin)
    assert close(admin, reason="").status_code in (400, 422)
    assert _matters(served, ADVOCATE)


def test_a_closure_whose_directory_step_fails_never_tells_the_admin_nothing_changed(ready, monkeypatch):
    """The Admin area's words for a source it could not read say "Nothing has been changed": after the erasures that is untrue."""
    from nm.arrive.admin_port import AdminUnavailable
    served = ready
    admin = served.login(ADMIN, confirmed=True)
    _suspend(admin)

    def failing(account_id, now):
        raise AdminUnavailable("a sign-in could not be read")
    monkeypatch.setattr(served.app.admin_accounts, "close", failing)
    reply = close(admin)
    assert reply.status_code == 503
    said = reply.json()["detail"]
    assert "part-way" in said and "Nothing has been changed" not in said and "Nothing was changed" not in said
    assert _matters(served, ADVOCATE) == set()
    assert [entry[1:] for entry in audit(served)][-2:] == [("close", ADVOCATE, REQUEST, "started"),
                                                           ("close", ADVOCATE, REQUEST, "part-way")], "nor does the audit"
