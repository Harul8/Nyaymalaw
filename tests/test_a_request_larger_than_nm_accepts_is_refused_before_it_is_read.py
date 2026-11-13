"""A request larger than NM accepts is refused before it is read (plan AN.53, 53d1; D219 with the numbers of D235; F-29).

Only the two routes that take a paper or a recording looked at a request's size. Every other route read whatever body it was
sent, whole, into memory, before anything looked at it - sign-in among them, which anyone can reach. One layer at the edge now
holds every route to a size: 2 MB, and 25 MB for the two that take a file. A request that says it is larger is refused without
a byte of it being read; one that does not say is read only until it has passed the size.

The application is driven as the server drives it (ASGI), so that what is read can be counted. No browser.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from nm.app import api
from tests.test_core_served import served, successful  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a
MB = 1024 * 1024


def _ask(method, path, *, declared=None, chunks=(), headers=()):
    """One request given to the application as a server gives it: (status, answer headers, body, chunks read)."""
    sent, read = [], []
    waiting = list(chunks)

    async def receive():
        read.append(1)
        if not waiting:
            return {"type": "http.request", "body": b"", "more_body": False}
        chunk = waiting.pop(0)
        return {"type": "http.request", "body": chunk, "more_body": bool(waiting)}

    async def send(message):
        sent.append(message)

    given = [(b"content-type", b"application/json"), *headers]
    if declared is not None:
        given.append((b"content-length", str(declared).encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "path": path,
             "raw_path": path.encode(), "query_string": b"", "root_path": "", "scheme": "http", "headers": given,
             "client": ("203.0.113.9", 4000), "server": ("testserver", 80)}
    asyncio.run(api.app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), body, len(read)


def test_a_sign_in_that_says_it_is_larger_is_refused_and_not_a_byte_is_read(served):
    status, headers, body, read = _ask("POST", "/api/login", declared=3 * MB, chunks=[b"x" * 1024] * 8)
    assert status == 413 and read == 0
    assert json.loads(body)["detail"]["code"] == "request_too_large"
    assert headers.get(b"x-content-type-options") == b"nosniff", "the refusal carries the headers every answer carries"


def test_one_that_does_not_say_its_size_is_read_only_until_it_has_passed_it(served):
    status, _headers, body, read = _ask("POST", "/api/login", chunks=[b"x" * (512 * 1024)] * 40)
    assert status == 413 and json.loads(body)["detail"]["code"] == "request_too_large"
    assert read <= 6, f"twenty megabytes were offered and {read} half-megabyte chunks were read"


def test_one_that_says_less_than_it_sends_is_stopped_at_the_size_all_the_same(served):
    status, _headers, _body, read = _ask("POST", "/api/login", declared=100, chunks=[b"x" * (512 * 1024)] * 40)
    assert status == 413 and read <= 6


def test_a_size_that_is_not_a_number_is_refused(served):
    status, _headers, _body, read = _ask("POST", "/api/login", declared="many")
    assert status == 400 and read == 0


@pytest.mark.parametrize("path", ["/api/documents", "/api/dictation"])
def test_the_routes_that_take_a_file_keep_their_larger_size_and_no_more(served, path):
    status, _headers, _body, _read = _ask("POST", path, declared=20 * MB)
    assert status != 413, "twenty megabytes is within what a recording may be; the route's own checks go on"
    status, _headers, body, read = _ask("POST", path, declared=26 * MB)
    assert status == 413 and read == 0 and json.loads(body)["detail"]["code"] == "request_too_large"


def test_what_is_within_the_size_goes_through_as_before(served):
    successful(served)
    assert served.client.get("/api/work").status_code == 200
    wrong = served.client.post("/api/login", json={"advocate_id": "nobody@example.test", "password": "not the password"})
    assert wrong.status_code in (401, 403, 429), "an ordinary sign-in is answered by the sign-in, not by the size"
    # What waits to be sent may hold twenty messages of 20,000 characters: 1.2 MB in an Indian script. It is not refused.
    chat = served.client.get("/api/work").json()["chats"][0]["chat_id"]
    waits = served.client.put(f"/api/chats/{chat}/queued", json={"queued": [{"text": "న" * 20000} for _ in range(20)]})
    assert waits.status_code == 200, waits.text
    status, _headers, _body, _read = _ask("GET", "/api/health")
    assert status == 200


def test_the_size_is_the_one_the_plan_records():
    assert api.BODY_LIMIT == 2 * MB and api.FILE_BODY_LIMIT == 25 * MB
    assert set(api.FILE_ROUTES) == {("POST", "/api/documents"), ("POST", "/api/dictation")}


# ------------------------------------------------------------- the fields that had no length (D235) ---

def test_a_message_that_opens_a_turn_may_be_long_and_not_without_end():
    assert api.TurnRequest(message="న" * 100_000).message, "a pasted brief of a hundred thousand characters is taken"
    with pytest.raises(ValueError):
        api.TurnRequest(message="x" * 100_001)
    for field in ("matter_id", "chat_id", "thread_id", "turn_id"):
        assert getattr(api.TurnRequest(message="A question.", **{field: "i" * 200}), field)
        with pytest.raises(ValueError):
            api.TurnRequest(message="A question.", **{field: "i" * 201})


def test_a_sign_in_name_longer_than_any_real_one_is_refused_as_malformed_and_not_said_back(served):
    given = {"advocate_id": "a" * 321, "password": "Not-the-password-1"}
    answer = served.client.post("/api/login", json=given)
    assert answer.status_code == 422, answer.text
    assert given["password"] not in answer.text and given["advocate_id"] not in answer.text


def test_a_long_password_is_taken_to_the_sign_in_which_an_earlier_account_may_need(served):
    """An account made before new passwords were bounded may hold a longer one (tests/test_public_email_registration.py holds
    that it still signs in). Its length is bounded by the size of the request, not by a count of its own."""
    answer = served.client.post("/api/login", json={"advocate_id": "a" * 307 + "@example.test", "password": "p" * 4096})
    assert answer.status_code in (401, 403, 429), "answered by the sign-in itself, not refused for its length"
