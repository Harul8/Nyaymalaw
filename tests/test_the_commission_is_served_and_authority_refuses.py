"""THE COMMISSION ON THE SERVED PATH. BK-62-AC1, BK-63-AC1, BK-33-AC1. P13.

`tests/test_one_policy_answers_who_may_act.py` proves the domain. This proves
the PRODUCT USES IT -- a different question, and the one CLAUDE.md section 8
says every external review found this product failing: *a guard that is right
in the core and wrong in the composition root is not a guard.*

WHAT IS ASSERTED THROUGH THE REAL ROUTES
------------------------------------------
    a commission is recorded, survives reload, and is served with its unknowns
    changing a material instruction reopens work AND SAYS WHICH FIELDS
    an unauthorised concession is refused with 403 AND RECORDED on the file
    the refusal names who attempted it and why, and carries no client material
    the cover shows persisted values and marks the rest not assessed
    a stranger gets 404 rather than a hint that the matter exists

WHY THE CAPACITY IS NOT TAKEN FROM THE REQUEST
------------------------------------------------
Because a caller that could name its own capacity could name `deciding` and
concede the client's case. `_capacity_of` reads the commission and accepts a
claimed capacity only when it NARROWS, and
`test_a_caller_cannot_promote_itself_by_claiming_a_capacity` is the test that
would fail if somebody made it convenient.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.class_a


def _matter(client) -> str:
    """One matter, through the real turn route."""
    reply = client.post(
        "/api/turn",
        json={
            "message": "we act for the plaintiff. the goods were never paid for.",
            "today": "2026-08-31",
        },
    )
    assert reply.status_code == 200, reply.text
    listed = client.get("/api/matters")
    assert listed.status_code == 200, listed.text
    rows = listed.json()["matters"]
    assert rows, listed.text
    return rows[0]["matter_id"]


def _full_body() -> dict:
    return {
        "objective": "recover the price of goods sold",
        "work_product": "advice",
        "scope": "the unpaid invoice of 3 March 2024",
        "instructing": {
            "party_id": "sol-1",
            "described_as": "the instructing solicitor",
            "capacity": "instructing",
        },
        "deciding": {"party_id": "client-1", "described_as": "the client", "capacity": "deciding"},
        "forum": "City Civil Court, Hyderabad",
        "deadline": {"kind": "date", "on": "2027-03-03", "basis": "Limitation Act art 14"},
    }


def _record(client, matter_id: str, body: dict):
    """An ordinary edit starts by reading the version it intends to change.

    Stale-form and malformed-precondition tests deliberately bypass this
    helper and submit the exact version their actor previously observed.
    """
    path = f"/api/matters/{matter_id}/commission"
    observed = client.get(path)
    assert observed.status_code == 200, observed.text
    return client.post(path, json={**body, "expected_version": observed.json()["version"]})


# ============================== recorded and read ===========================


def test_a_commission_is_recorded_and_comes_back_after_reload(client):
    """THE NEGATIVE CONTROL for everything below: a route that refused every
    instruction would satisfy each refusal test and record nothing."""
    matter_id = _matter(client)
    posted = _record(client, matter_id, _full_body())
    assert posted.status_code == 200, posted.text
    assert posted.json()["state"] == "commission_recorded"
    assert posted.json()["unknowns"] == []

    # RELOAD. A fresh request, reading what the store holds.
    got = client.get(f"/api/matters/{matter_id}/commission")
    assert got.status_code == 200, got.text
    commission = got.json()["commission"]
    assert commission["objective"] == "recover the price of goods sold"
    assert commission["instructing"]["party_id"] == "sol-1"
    assert commission["deciding"]["party_id"] == "client-1"
    assert commission["version"] == 1
    assert commission["established"] is True


def test_an_incomplete_commission_is_served_with_what_it_lacks(client):
    """Recording an instruction that says little is legitimate; presenting it
    as complete is not."""
    matter_id = _matter(client)
    posted = _record(client, matter_id, {"objective": "something urgent"})
    assert posted.status_code == 200, posted.text
    unknowns = posted.json()["unknowns"]
    assert any("who decides" in u for u in unknowns), unknowns
    assert any("the forum" in u for u in unknowns), unknowns
    assert posted.json()["commission"]["established"] is False


def test_who_instructs_and_who_decides_stay_two_fields_through_the_wire(client):
    """Collapsing them is how a concession gets taken from somebody who could
    not give it."""
    matter_id = _matter(client)
    _record(client, matter_id, _full_body())
    commission = client.get(f"/api/matters/{matter_id}/commission").json()["commission"]
    assert commission["instructing"]["party_id"] != commission["deciding"]["party_id"]
    assert commission["instructing"]["capacity"] == "instructing"
    assert commission["deciding"]["capacity"] == "deciding"


# ========================= a material change reopens ========================


def test_changing_a_material_instruction_reopens_and_names_the_fields(client):
    """BK-62-AC1's second half. An advocate who widens the scope is told what
    reopened rather than discovering it later."""
    matter_id = _matter(client)
    _record(client, matter_id, _full_body())

    changed = _record(
        client, matter_id, {
            "work_product": "negotiation",
            "because": "the client now wants a settlement attempt",
        },
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["reopened"] is True
    assert "work_product" in body["material_changes"]
    assert body["commission"]["version"] == 2


def test_an_immaterial_change_does_not_reopen(client):
    """A reopen on every save trains an advocate to ignore the signal."""
    matter_id = _matter(client)
    _record(client, matter_id, _full_body())
    again = _record(client, matter_id, {"because": "tidied the wording"})
    assert again.status_code == 200, again.text
    assert again.json()["reopened"] is False
    assert again.json()["material_changes"] == []


def test_the_superseded_version_is_kept_and_served(client):
    """An advice given under version 1 was correct work under version 1, and
    deleting version 1 makes it look like a mistake."""
    matter_id = _matter(client)
    _record(client, matter_id, _full_body())
    _record(client, matter_id, {"work_product": "negotiation", "because": "settling"})

    history = client.get(f"/api/matters/{matter_id}/commission").json()["history"]
    assert len(history) == 1
    assert history[0]["work_product"] == "advice"
    assert history[0]["version"] == 1


def test_a_patch_keeps_what_it_did_not_send(client):
    """A field the advocate omitted must not silently become empty, which
    would read as an instruction that said nothing."""
    matter_id = _matter(client)
    _record(client, matter_id, _full_body())
    _record(client, matter_id, {"because": "no change to the substance"})
    commission = client.get(f"/api/matters/{matter_id}/commission").json()["commission"]
    assert commission["objective"] == "recover the price of goods sold"
    assert commission["forum"] == "City Civil Court, Hyderabad"


# ===================== the unauthorised concession ==========================


def test_an_unauthorised_concession_is_refused_and_recorded(client):
    """THE POINT OF THE PACKET. The signed-in advocate is ADVISING, and
    advising may not concede however reasonable the concession looks."""
    matter_id = _matter(client)
    _record(client, matter_id, _full_body())

    attempt = client.post(f"/api/matters/{matter_id}/concede", json={"on": "the limitation point"})
    assert attempt.status_code == 403, attempt.text
    assert "not made" in attempt.json()["detail"]

    # AND RECORDED. A 403 that leaves no trace records nothing, and BK-63-AC1
    # requires refused operations refused AND recorded.
    refusals = client.get(f"/api/matters/{matter_id}/commission").json()["refusals"]
    assert refusals, "the refused concession left no record on the file"
    assert refusals[-1]["act"] == "concede"
    assert refusals[-1]["standing"] == "refused"
    assert refusals[-1]["actor_id"] == "adv_demo"
    assert "at" in refusals[-1]


def test_the_recorded_refusal_carries_no_client_material(client):
    """An authority decision is about who, not about what the matter says."""
    matter_id = _matter(client)
    client.post(
        f"/api/matters/{matter_id}/concede",
        json={"on": "the client admitted possession began in 2011"},
    )
    refusals = client.get(f"/api/matters/{matter_id}/commission").json()["refusals"]
    for record in refusals:
        text = " ".join(str(v) for v in record.values())
        assert "possession" not in text and "2011" not in text


def test_a_caller_cannot_promote_itself_by_claiming_a_capacity(client):
    """A caller that could name its own capacity could name `deciding`. The
    claim is accepted only when it NARROWS."""
    matter_id = _matter(client)
    attempt = client.post(
        f"/api/matters/{matter_id}/concede", json={"on": "everything", "acting_as": "deciding"}
    )
    assert attempt.status_code == 403, attempt.text


def test_a_recorded_decision_maker_may_concede(client):
    """The negative control for the refusals: an authority policy that refused
    every concession would be safe and useless."""
    matter_id = _matter(client)
    body = _full_body()
    # The signed-in advocate IS the recorded decision maker on this file.
    body["deciding"] = {
        "party_id": "adv_demo",
        "described_as": "the client",
        "capacity": "deciding",
    }
    _record(client, matter_id, body)
    _provision_deciding(matter_id)

    allowed = client.post(f"/api/matters/{matter_id}/concede", json={"on": "the interest claim"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["state"] == "decision_recorded"
    assert allowed.json()["externally_effective"] is False
    records = client.get(f"/api/matters/{matter_id}/concede").json()["decisions"]
    assert records[-1]["on"] == "the interest claim"
    assert records[-1]["by"] == "adv_demo"


def _provision_deciding(matter_id, **overrides):
    """Trusted fixture boundary, not a self-service HTTP authority claim."""
    from dataclasses import replace
    from datetime import timedelta

    from nm.domain.advocate import utcnow
    from nm.domain.authority import ActingAs, bind_authority
    from nm.domain.commission import Commission
    from nm.edge.api import application

    store = application().store
    matter = store.load(matter_id)
    now = utcnow()
    grant = bind_authority(
        actor_id="adv_demo",
        capacity=ActingAs.DECIDING,
        issued_by="verified-authority-officer",
        basis="synthetic authority reviewed",
        commission_version=Commission.from_stored(matter.commission).version,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    grant.update(overrides)
    store.commit(
        replace(
            matter,
            authority_bindings=(*matter.authority_bindings, grant),
            version=matter.version + 1,
        ),
        expected_version=matter.version,
    )


def test_posting_oneself_as_decision_maker_does_not_grant_authority(client):
    matter_id = _matter(client)
    body = _full_body()
    body["deciding"] = {"party_id": "adv_demo", "capacity": "deciding", "described_as": "me"}
    assert _record(client, matter_id, body).status_code == 200
    refused = client.post(f"/api/matters/{matter_id}/concede", json={"on": "interest"})
    assert refused.status_code == 403
    assert client.get(f"/api/matters/{matter_id}/concede").json()["decisions"] == []


@pytest.mark.parametrize(
    "override",
    [
        {"expires_at": "2001-01-01T00:00:00+00:00"},
        {"revoked_at": "2026-01-01T00:00:00+00:00"},
        {"commission_version": 999},
    ],
)
def test_expired_revoked_or_stale_authority_cannot_decide(client, override):
    matter_id = _matter(client)
    _record(client, matter_id, _full_body())
    _provision_deciding(matter_id, **override)
    assert (
        client.post(f"/api/matters/{matter_id}/concede", json={"on": "interest"}).status_code == 403
    )


def test_decision_replay_is_one_receipt_and_reused_key_conflicts(client):
    matter_id = _matter(client)
    _record(client, matter_id, _full_body())
    _provision_deciding(matter_id)
    path = f"/api/matters/{matter_id}/concede"
    body = {"decision_id": "intent-1", "on": "interest"}
    first = client.post(path, json=body)
    assert first.status_code == 200
    assert client.post(path, json=body).json() == first.json()
    assert len(client.get(path).json()["decisions"]) == 1
    assert client.post(path, json={**body, "on": "principal"}).status_code == 409


def test_a_material_instruction_reopens_persisted_scope_not_just_a_flag(client):
    from nm.edge.api import application

    matter_id = _matter(client)
    _record(client, matter_id, _full_body())
    before = application().store.load(matter_id)
    assert before.intake_answers.get("scope")
    changed = _record(client, matter_id, {"scope": "different authorised work"})
    assert changed.status_code == 200 and changed.json()["reopened"]
    after = application().store.load(matter_id)
    assert "scope" not in after.intake_answers
    assert after.intake_answers["capacity"] == before.intake_answers["capacity"]
    assert (
        after.commission_invalidations[-1]["prior_scope_answer"] == before.intake_answers["scope"]
    )


def test_decision_and_refusal_write_failure_never_claim_success(client, monkeypatch):
    from nm.edge.api import application

    matter_id = _matter(client)
    _record(client, matter_id, _full_body())
    _provision_deciding(matter_id)

    def unavailable(*args, **kwargs):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(application().store, "commit", unavailable)
    path = f"/api/matters/{matter_id}/concede"
    assert client.post(path, json={"on": "interest"}).status_code == 503
    assert client.post(path, json={"on": "interest", "acting_as": "assisting"}).status_code == 503


# CSRF IS NOT CHECKED HERE, DELIBERATELY.
#
# `tests/test_every_unsafe_route_is_csrf_protected.py` already enumerates the
# route table and fails on any unsafe route without the dependency, so it
# covered these two the moment they existed -- and it passes. A second check
# here was written first, looked for the wrong attribute (`.dependency` on the
# resolved dependant rather than `.call`), and reported a guarded route as
# unguarded: precisely the mistake that sweep's own comment records having
# made and fixed. Two owners of one question, and the newer one was wrong.


# ================================ the cover =================================


def test_the_cover_shows_persisted_values_and_marks_the_rest_unassessed(client):
    """BK-33-AC1. The two ways an unassessed value becomes a fact are a blank
    that reads as none and an implementation id that reads as a name."""
    matter_id = _matter(client)
    cover = client.get(f"/api/matters/{matter_id}/cover")
    assert cover.status_code == 200, cover.text
    body = cover.json()

    assert body["matter_id"] == matter_id
    assert body["title"] and body["title"] != matter_id, "the matter id is being offered as a title"
    assert body["deadline_assessment"] == "not_assessed"
    assert "has been assessed" in body["deadline_said"]
    assert body["commission_state"] == "not_recorded"
    # An unrecorded client is None with a state, never "" and never the id.
    assert body["client"] is None or body["client"] != matter_id
    assert body["client_state"] in ("recorded", "not_recorded")


def test_the_cover_reports_the_deadline_once_a_commission_records_one(client):
    matter_id = _matter(client)
    _record(client, matter_id, _full_body())
    body = client.get(f"/api/matters/{matter_id}/cover").json()
    assert body["deadline_assessment"] == "assessed"
    assert "2027-03-03" in body["deadline_said"]
    assert "Limitation Act art 14" in body["deadline_said"]
    assert body["commission_state"] == "recorded"


def test_a_deadline_that_does_not_apply_reads_differently_from_one_unknown(client):
    """`no deadline applies` is a finding somebody made; `not established` is
    the absence of one, and an advocate acts differently on each."""
    matter_id = _matter(client)
    _record(client, matter_id, {
        "deadline": {"kind": "none_applies", "reason": "this is an advisory opinion"}})
    body = client.get(f"/api/matters/{matter_id}/cover").json()
    assert body["deadline_assessment"] == "assessed"
    assert "no deadline applies" in body["deadline_said"]


# ============================== isolation ===================================


def test_a_stranger_gets_the_same_answer_as_for_a_matter_that_does_not_exist(client):
    """A failed lookup must disclose nothing about what exists."""
    matter_id = _matter(client)
    stranger = client.sign_in("adv_stranger", fresh=True)
    for path in (f"/api/matters/{matter_id}/cover", f"/api/matters/{matter_id}/commission"):
        mine = stranger.get(path)
        absent = stranger.get("/api/matters/mat_doesnotexist/cover")
        assert mine.status_code == 404, path
        assert mine.json()["detail"] == absent.json()["detail"]


def test_a_stranger_cannot_write_a_commission_onto_another_file(client):
    matter_id = _matter(client)
    stranger = client.sign_in("adv_stranger2", fresh=True)
    refused = stranger.post(f"/api/matters/{matter_id}/commission", json=_full_body())
    assert refused.status_code == 404, refused.text


def test_signing_out_removes_access_to_the_new_routes(client):
    matter_id = _matter(client)
    assert client.get(f"/api/matters/{matter_id}/cover").status_code == 200
    assert client.post("/api/logout").status_code == 200
    for path in (f"/api/matters/{matter_id}/cover", f"/api/matters/{matter_id}/commission"):
        assert client.get(path).status_code == 401, path


def test_two_sequential_forms_cannot_overwrite_newer_instructions(client):
    from nm.edge.api import application

    matter_id = _matter(client)
    path = f"/api/matters/{matter_id}/commission"
    form_a = client.get(path).json()
    form_b = client.get(path).json()
    assert form_a["version"] == form_b["version"]
    first = client.post(path, json={**_full_body(), "expected_version": form_a["version"]})
    assert first.status_code == 200, first.text
    assert first.json()["version"] == form_a["version"] + 1
    recorded = application().store.load(matter_id)
    # This is a later request, not simultaneous store calls. Reading the
    # current version inside POST would accept it and replace the first form.
    second = client.post(path, json={
        **_full_body(), "scope": "a different scope from the older form",
        "expected_version": form_b["version"], "because": "older form was left open"})
    assert second.status_code == 409, second.text
    assert application().store.load(matter_id) == recorded
    refreshed = client.get(path).json()
    third = client.post(path, json={
        "scope": "a newly reviewed scope", "because": "client changed the instruction",
        "expected_version": refreshed["version"]})
    assert third.status_code == 200, third.text
    assert third.json()["commission"]["scope"] == "a newly reviewed scope"
    assert len(client.get(path).json()["history"]) == 1


@pytest.mark.parametrize("precondition", [None, True, False, "1", -1, 1.0, [], {}])
def test_commission_writes_require_a_real_observed_version(client, precondition):
    from nm.edge.api import application

    matter_id = _matter(client)
    before = application().store.load(matter_id)
    body = _full_body()
    if precondition is not None:
        body["expected_version"] = precondition
    response = client.post(f"/api/matters/{matter_id}/commission", json=body)
    assert response.status_code == 422, response.text
    assert application().store.load(matter_id) == before


def test_a_future_version_is_not_permission_to_overwrite_the_present(client):
    from nm.edge.api import application

    matter_id = _matter(client)
    before = application().store.load(matter_id)
    response = client.post(f"/api/matters/{matter_id}/commission", json={
        **_full_body(), "expected_version": before.version + 1})
    assert response.status_code == 409, response.text
    assert application().store.load(matter_id) == before


def test_a_change_after_the_observed_version_check_still_meets_store_cas(client, monkeypatch):
    from dataclasses import replace

    from nm.edge.api import application

    matter_id = _matter(client)
    path = f"/api/matters/{matter_id}/commission"
    observed = client.get(path).json()["version"]
    store = application().store.inner
    original_commit = store.commit
    intervening = []

    def competing_commit(matter, *, expected_version):
        current = store.load(matter_id)
        changed = replace(current, title="A concurrent saved title", version=current.version + 1)
        original_commit(changed, expected_version=current.version)
        intervening.append(changed)
        return original_commit(matter, expected_version=expected_version)

    monkeypatch.setattr(store, "commit", competing_commit)
    response = client.post(path, json={**_full_body(), "expected_version": observed})
    assert response.status_code == 409, response.text
    assert len(intervening) == 1
    assert store.load(matter_id) == intervening[0]
    assert store.load(matter_id).commission is None
