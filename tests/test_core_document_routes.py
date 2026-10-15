"""The document routes (owner decisions, 15 Oct 2026): an advocate sends a file as the
request body and sees what was checked and read; nobody else can see it.

The malware checker is a recorded outcome; the reader, the sealed store, sign-in and
CSRF are the served ones.
"""
from urllib.parse import quote

from fastapi.testclient import TestClient
import pytest

from nm.app import api
from nm.core_engine import documents
from tests.test_core_documents import Checker
from tests.test_core_served import OTHER, served  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def upload(client, data=b"The cheque was returned on 3 October 2026.", name="note.txt", **headers):
    return client.post("/api/documents", content=data,
                       headers={"x-nm-document-name": quote(name), **headers})


@pytest.fixture
def desk(served):
    served.app.documents.checker = Checker()
    return served.app.documents


def test_an_advocate_sends_a_document_and_reads_back_what_was_checked_and_read(served, desk):
    reply = upload(served.client, name="नोटिस 3.txt")
    assert reply.status_code == 201, reply.text
    shown = reply.json()
    assert shown["name"] == "नोटिस 3.txt" and shown["state"] == "read" and shown["pages_read"] == 1
    assert "cheque" not in reply.text  # the summary carries no page text
    again = served.client.get(f"/api/documents/{shown['document_ref']}")
    assert again.status_code == 200 and again.json() == shown
    assert again.headers["cache-control"] == "no-store"


def test_another_advocate_or_a_stranger_cannot_see_it(served, desk):
    ref = upload(served.client).json()["document_ref"]
    assert served.login(OTHER).get(f"/api/documents/{ref}").status_code == 404
    with TestClient(api.app) as anonymous:
        assert anonymous.get(f"/api/documents/{ref}").status_code == 401
        assert upload(anonymous).status_code in (401, 403)
    assert len(desk.checker.seen) == 1


def test_a_request_without_this_page_s_csrf_value_is_refused_before_any_check(served, desk):
    assert upload(served.client, **{"x-nm-csrf": "wrong"}).status_code == 403
    assert desk.checker.seen == []


def test_an_oversized_body_is_refused_before_it_is_read_or_checked(served, desk, monkeypatch):
    monkeypatch.setattr(documents, "MAX_BYTES", 8)
    reply = upload(served.client, data=b"more than eight bytes")
    assert reply.status_code == 413 and reply.json()["detail"]["code"] == "document_too_large"
    assert desk.checker.seen == []


@pytest.mark.parametrize("name,data", [("tool.exe", b"MZ\x90\x00"), ("", b"words"), ("a\x01.txt", b"words")])
def test_an_unsupported_or_unnamed_file_is_refused_plainly(served, desk, name, data):
    reply = upload(served.client, data=data, name=name)
    assert reply.status_code == 422 and reply.json()["detail"]["code"] == "document_refused"
    assert desk.checker.seen == []


def test_without_a_configured_malware_checker_a_document_is_held_unread(served):
    reply = upload(served.client)
    assert reply.status_code == 201
    shown = reply.json()
    assert shown["state"] == "held" and shown["pages_read"] == 0
    assert shown["check"]["reason"] == "no malware checker is set up on this installation"
