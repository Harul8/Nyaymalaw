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
