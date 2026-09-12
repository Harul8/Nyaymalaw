"""REPLACING RECOVERY CODES OVER HTTP, AND WHAT THE WIRE REFUSES. BK-31-AC20.

CLAUDE.md §8: verify on the bytes, not the return value. The adapter is proven
in `tests/test_recovery_codes_are_replaced_safely.py`; every defect the first
external review of this project found lived between a correct module and the
served path, so the same questions are asked again here of the HTTP surface.

WHAT THE SERVED PATH ADDS THAT THE ADAPTER CANNOT
---------------------------------------------------
    the actor comes from the SESSION, never the body
    a cross-site caller is refused before any of it runs
    the proof is spent through a real request, not a direct call
    the codes appear in ONE response body and in no later GET
    a 409 and a 401 mean different things to the page

WHY THE STATUS CODES ARE TESTED AS BEHAVIOUR
----------------------------------------------
`403` on a stale rotation would tell the advocate they are not permitted,
which sends them to an administrator. They ARE permitted; the state moved.
That is `409`, and it is the difference between a retry that works and a
support call.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.class_a

PASSWORD = "Fixture-password-not-a-secret-1"


def _proof(client, password: str = PASSWORD):
    return client.post("/api/reauthenticate", json={"password": password})


def _rotate(client, proof: str, generation: int = 1, **headers):
    return client.post("/api/recovery-codes/rotate",
                       json={"proof": proof,
                             "expected_recovery_generation": generation},
                       **headers)


def _generation(client, advocate_id: str = "adv_demo") -> int:
    from nm.domain.advocate import AccountSecurity
    return AccountSecurity.read(
        client.directory._read(advocate_id)).recovery_generation


# ================================ it works ==================================

def test_a_signed_in_advocate_replaces_their_codes_over_http(client):
    """THE NEGATIVE CONTROL. Without it every refusal below is satisfied by an
    endpoint that refuses everything."""
    before = _generation(client)
    earned = _proof(client)
    assert earned.status_code == 200, earned.text
    assert earned.json()["expires_in_seconds"] == 300

    replaced = _rotate(client, earned.json()["proof"], generation=before)
    assert replaced.status_code == 200, replaced.text
    body = replaced.json()
    assert body["replaced"] == len(body["recovery_codes"]) == 10
    assert _generation(client) == before + 1


def test_the_codes_appear_once_and_no_later_request_returns_them(client):
    """THERE IS NO READ-BACK AND THERE MUST NEVER BE ONE.

    Not a claim about today's routes -- a scan of what the whole served surface
    will hand back afterwards. A `GET` added next month that helpfully includes
    them is the defect this asserts against.
    """
    codes = _rotate(client, _proof(client).json()["proof"],
                    generation=_generation(client)).json()["recovery_codes"]
    assert codes

    seen = []
    for path in ("/api/session", "/api/sessions", "/api/matters", "/api/health"):
        response = client.get(path)
        if response.status_code == 200:
            seen.append(response.text)
    later = "\n".join(seen)
    assert later, "no follow-up route answered, so this checked nothing"
    for code in codes:
        assert code not in later, "a recovery code was served after its one response"
        assert code.replace("-", "") not in later


def test_the_actor_comes_from_the_session_and_not_from_the_body(client):
    """B-082 was exactly this: the caller named whichever advocate they liked.
    An extra field must be REFUSED, not ignored -- a body that is silently
    dropped looks to the caller like it was honoured."""
    proof = _proof(client).json()["proof"]
    response = client.post("/api/recovery-codes/rotate",
                           json={"proof": proof,
                                 "expected_recovery_generation": 1,
                                 "advocate_id": "somebody-else"})
    assert response.status_code == 422, response.text


# ============================== what it refuses =============================

def test_an_anonymous_caller_gets_401_from_both_routes(client):
    anonymous = client.__class__(client.app) if hasattr(client, "app") else None
    if anonymous is None:
        pytest.skip("the fixture client cannot produce an unauthenticated peer")
    for path, body in (("/api/reauthenticate", {"password": PASSWORD}),
                       ("/api/recovery-codes/rotate",
                        {"proof": "x", "expected_recovery_generation": 1})):
        response = anonymous.post(
            path, json=body, headers={"origin": str(anonymous.base_url).rstrip("/")})
        assert response.status_code in (401, 403), (path, response.status_code)


def test_a_wrong_password_earns_no_proof_and_says_nothing_more(client):
    response = _proof(client, "Not-The-Password-9z")
    assert response.status_code == 401
    assert "password" not in response.json()["detail"].lower(), (
        "the refusal named the field that failed, which is an oracle")


def test_a_cross_site_caller_is_refused_before_anything_happens(client):
    """The CSRF guard, on the real route rather than on the dependency."""
    before = _generation(client)
    proof = _proof(client).json()["proof"]
    refused = _rotate(client, proof, generation=before,
                      headers={"origin": "https://evil.example"})
    assert refused.status_code == 403
    assert _generation(client) == before, "a refused cross-site call still rotated"


def test_a_spent_proof_is_409_and_not_403(client):
    """A 403 reads as *you may not*, which sends the advocate to an
    administrator. They may; the proof is spent. That is a 409 and a retry."""
    before = _generation(client)
    proof = _proof(client).json()["proof"]
    assert _rotate(client, proof, generation=before).status_code == 200
    again = _rotate(client, proof, generation=before + 1)
    assert again.status_code == 409, again.text
    assert "still work" in again.json()["detail"], (
        "the advocate is not told their existing codes are intact")


def test_a_stale_expected_generation_is_refused(client):
    before = _generation(client)
    response = _rotate(client, _proof(client).json()["proof"], generation=before + 7)
    assert response.status_code == 409
    assert _generation(client) == before


def test_the_expected_generation_is_required_rather_than_defaulted(client):
    """A default would make *the caller did not check* indistinguishable from
    *the caller checked and it matched*."""
    proof = _proof(client).json()["proof"]
    response = client.post("/api/recovery-codes/rotate", json={"proof": proof})
    assert response.status_code == 422, response.text


def test_every_rotation_refusal_reads_the_same_to_the_caller(client):
    """One sentence for spent, stale and unknown alike."""
    said = set()
    for attempt in ("unknown", "stale"):
        proof = _proof(client).json()["proof"]
        response = (_rotate(client, "not-a-real-proof", generation=_generation(client))
                    if attempt == "unknown"
                    else _rotate(client, proof, generation=_generation(client) + 5))
        assert response.status_code == 409
        said.add(response.json()["detail"])
    assert len(said) == 1, f"refusals differ by cause: {said}"


# ============================= the security event ===========================

def test_the_audit_records_the_replacement_and_never_a_code(client, tmp_path):
    codes = _rotate(client, _proof(client).json()["proof"],
                    generation=_generation(client)).json()["recovery_codes"]
    audit = "\n".join(
        path.read_bytes().decode("utf8", "replace")
        for path in tmp_path.rglob("*.log") if path.is_file())
    assert "recovery codes replaced" in audit, (
        "the security event was not recorded at all")
    for code in codes:
        assert code not in audit and code.replace("-", "") not in audit


def test_the_other_sessions_end_and_this_one_survives(client):
    """A rotation is a security event; another live session must not outlive
    it. The one being used does, or nobody uses the control twice."""
    other = client.sign_in(fresh=True)
    assert other.get("/api/session").status_code == 200

    assert _rotate(client, _proof(client).json()["proof"],
                   generation=_generation(client)).status_code == 200

    assert client.get("/api/session").status_code == 200, "the rotating session ended"
    assert other.get("/api/session").status_code == 401, (
        "another session survived a recovery-credential replacement")


# ========================= sensitive failure admission =======================

def _sensitive_attempt(client, operation, proof):
    if operation == "reauthenticate":
        return _proof(client)
    return _rotate(client, proof, generation=_generation(client))


def _assert_paused(response):
    assert response.status_code == 429, response.text
    assert int(response.headers["retry-after"]) > 0
    assert "Nothing is locked" in response.json()["detail"]


@pytest.mark.parametrize("path,body", [
    ("/api/register", {"password": PASSWORD, "password_again": PASSWORD}),
    ("/api/recover", {"advocate_id": "adv_demo", "recovery_code": "unissued",
                      "password": PASSWORD, "password_again": PASSWORD}),
    ("/api/login", {"advocate_id": "adv_demo", "password": PASSWORD}),
    ("/api/reauthenticate", {"password": PASSWORD}),
    ("/api/recovery-codes/rotate", {"proof": "unissued",
                                    "expected_recovery_generation": 1}),
])
def test_every_failure_counted_authentication_door_obeys_source_admission(
        client, path, body):
    from nm.domain import attempts
    from nm.edge import api

    now = api.utcnow()
    for number in range(attempts.PER_SOURCE):
        client.directory.note_failure(f"other-{number}", "testclient", now)
    # Public signup counts every admitted attempt in its own durable ledger.
    # This population is the retained failure-counted invitation lane.
    headers = {"X-Enrolment-Invitation": "unissued"} if path == "/api/register" else {}
    _assert_paused(client.post(path, json=body, headers=headers))


@pytest.mark.parametrize("operation", ["reauthenticate", "rotate_recovery_codes"])
@pytest.mark.parametrize("limit", ["account", "source"])
def test_sensitive_limits_refuse_before_the_consumer_without_changing_state(
        client, monkeypatch, operation, limit):
    from nm.domain import attempts
    from nm.edge import api

    now = api.utcnow()
    monkeypatch.setattr(api, "utcnow", lambda: now)
    # A real positive path precedes the planted limiting population.
    earned = _proof(client)
    assert earned.status_code == 200, earned.text
    proof = earned.json()["proof"]
    before = _generation(client)
    calls = []
    original = getattr(client.directory, operation)

    def watched(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(client.directory, operation, watched)
    count = attempts.PER_ADVOCATE if limit == "account" else attempts.PER_SOURCE
    for number in range(count):
        client.directory.note_failure(
            "adv_demo" if limit == "account" else f"other-{number}",
            "elsewhere" if limit == "account" else "testclient", now)
    counts = client.directory.failures_since(
        "adv_demo", "testclient", now - attempts.WINDOW)
    assert counts is not None and len(counts[0 if limit == "account" else 1]) == count

    paused = _sensitive_attempt(client, operation, proof)
    _assert_paused(paused)
    assert calls == [], "a throttled attempt still reached secret verification/mutation"
    assert _generation(client) == before
    assert client.get("/api/session").status_code == 200
    assert client.directory.failures_since(
        "adv_demo", "testclient", now - attempts.WINDOW) == counts, (
        "a refused retry must not extend the pause")


@pytest.mark.parametrize("operation", ["reauthenticate", "rotate_recovery_codes"])
def test_sensitive_failure_records_the_observed_source_once(client, operation):
    from nm.domain import attempts
    from nm.edge import api

    since = api.utcnow() - attempts.WINDOW
    assert client.directory.failures_since("adv_demo", "testclient", since) == ((), ())
    response = (_proof(client, "Wrong-password-9") if operation == "reauthenticate"
                else _rotate(client, "unissued-proof", generation=_generation(client)))
    assert response.status_code == (401 if operation == "reauthenticate" else 409)
    counts = client.directory.failures_since("adv_demo", "testclient", since)
    assert counts is not None
    assert len(counts[0]) == len(counts[1]) == 1, (
        "one failure must count once for both the account and the real source")


def test_a_claimed_forwarded_address_cannot_reset_a_sensitive_source_limit(client):
    from nm.domain import attempts
    from nm.edge import api

    now = api.utcnow()
    # An observed failure participates in the same source counter as the
    # synthetic other-account population; the caller cannot rename that source.
    assert _proof(client, "Wrong-password-9").status_code == 401
    for number in range(attempts.PER_SOURCE - 1):
        client.directory.note_failure(f"other-{number}", "testclient", now)
    response = client.post(
        "/api/reauthenticate", json={"password": PASSWORD},
        headers={"x-forwarded-for": "198.51.100.17"})
    _assert_paused(response)


def test_the_sensitive_pause_ages_out_without_locking_the_account(client, monkeypatch):
    from datetime import timedelta

    from nm.domain import attempts
    from nm.edge import api

    now = api.utcnow()
    monkeypatch.setattr(api, "utcnow", lambda: now)
    for _ in range(attempts.PER_ADVOCATE):
        assert _proof(client, "Wrong-password-9").status_code == 401
    _assert_paused(_proof(client))
    now += attempts.WINDOW + timedelta(seconds=1)
    response = _proof(client)
    assert response.status_code == 200, response.text
    assert response.json()["proof"]


def test_the_sensitive_limit_witness_rejects_an_admission_bypass(client, monkeypatch):
    from nm.domain import attempts
    from nm.edge import api

    assert _proof(client).status_code == 200
    now = api.utcnow()
    for _ in range(attempts.PER_ADVOCATE):
        client.directory.note_failure("adv_demo", "testclient", now)
    _assert_paused(_proof(client))
    original = api._admit_auth_attempt
    assert callable(original)
    monkeypatch.setattr(api, "_admit_auth_attempt", lambda *args, **kwargs: None)
    assert api._admit_auth_attempt is not original
    with pytest.raises(AssertionError):
        _assert_paused(_proof(client))
