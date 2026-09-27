"""The served local-reading path, using actual sealed bytes and the real parser.

The scanner here is explicitly controlled test configuration. It is not a
production clearance, an external processor, or permission implied by upload.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
from nm.domain.media import Quarantine
from nm.ports.document_text import DocumentFormat
from nm.ports.matter_documents import QuarantineRead

pytestmark = pytest.mark.class_a
WORDS = "The original records payment on 4 March 2026. Amount ₹10000. Straße."


class ControlledLocalChecker:
    """An attributed test-only result over the actual reconstructed bytes."""

    def __init__(self, *, state=Quarantine.RELEASED, after_read=None):
        self.state, self.after_read = state, after_read
        self.calls = []

    def inspect(self, original_id, source_sha256, data):
        self.calls.append((original_id, source_sha256, data))
        if self.after_read is not None:
            self.after_read()
        return QuarantineRead(
            original_id,
            hashlib.sha256(data).hexdigest(),
            len(data),
            self.state,
            DocumentFormat.TEXT,
            "controlled-local-checker",
            "fixture-v1",
            "Controlled test-only check; no production scanner approval.",
        )


def upload(client, *, key="one", words=WORDS, chunk_size=None):
    opened = client.post(
        "/api/matters/intake",
        json={"request_key": "intake_" + key, "title": "Private document", "parties": {}},
    )
    assert opened.status_code == 200, opened.text
    matter_id = opened.json()["matter_id"]
    data = words.encode("utf8")
    offered = client.post(
        f"/api/matters/{matter_id}/uploads",
        json={
            "request_key": "upload_" + key,
            "filename": "private.txt",
            "declared_size": len(data),
            "purpose": "Hold this original only; do not analyse it",
            "authority": "The owner permits holding only",
            "retention": "matter_life",
        },
    )
    assert offered.status_code == 200, offered.text
    original_id = offered.json()["asset_id"]
    size = chunk_size or len(data)
    for offset in range(0, len(data), size):
        accepted = client.put(
            f"/api/matters/{matter_id}/uploads/{original_id}/chunks/{offset}",
            content=data[offset:offset + size],
        )
        assert accepted.status_code == 200, accepted.text
    completed = client.post(f"/api/matters/{matter_id}/uploads/{original_id}/complete")
    assert completed.status_code == 200, completed.text
    receipt = completed.json()
    locator = receipt["original_locator"]
    return matter_id, {
        "version": receipt["version"],
        "request_key": "read_" + key,
        "original_id": original_id,
        "asset_version": locator["version"],
        "source_sha256": locator["sha256"],
        "purpose": "Read this supplied original for this matter",
        "authority": "The authenticated owner explicitly requests local reading",
        "analysis_allowed": True,
    }


def post(client, matter_id, action, body, **kwargs):
    return client.post(f"/api/matters/{matter_id}/documents/{action}", json=body, **kwargs)


def search(client, matter_id, version, query="4 March"):
    return post(client, matter_id, "search", {"version": version, "query": query})


def read(client, wired, *, key="one"):
    checker = ControlledLocalChecker()
    wired.documents.quarantine = checker
    matter_id, instruction = upload(client, key=key)
    accepted = post(client, matter_id, "analyse", instruction)
    assert accepted.status_code == 200, accepted.text
    saved = accepted.json()
    return matter_id, instruction, saved, checker


def quote_request(source, version):
    names = (
        "original_id", "asset_version", "source_sha256", "derivative_sha256",
        "number", "location_kind", "part", "start", "end",
    )
    return {"version": version, **{name: source[name] for name in names}}


def invalidate(client, wired, matter_id, change):
    if change == "session":
        assert client.post("/api/logout").status_code == 200
    else:
        matter = wired.store.load(matter_id)
        wired.store.commit(
            replace(matter, title="A concurrently revised file", version=matter.version + 1),
            expected_version=matter.version,
        )


def test_holding_upload_is_not_analysis_or_fact_or_external_permission(client, wired):
    checker = ControlledLocalChecker()
    wired.documents.quarantine = checker
    matter_id, instruction = upload(client)
    before = search(client, matter_id, instruction["version"])
    assert before.status_code == 200, before.text
    result = before.json()
    assert result["facts_established"] is False
    assert result["external_processing_granted"] is False
    assert result["result"]["partial"] is True
    assert not result["result"]["matches"] and not result["result"]["searched"]
    assert result["result"]["not_searched"][0]["original_id"] == instruction["original_id"]
    assert not checker.calls
    declined = post(client, matter_id, "analyse", {**instruction, "analysis_allowed": False})
    assert declined.status_code == 422
    assert not checker.calls
    matter = wired.store.load(matter_id)
    assert matter.version == instruction["version"] and matter.facts == ()
    assert "document_reading" not in matter.uploads[instruction["original_id"]]


def test_upload_read_search_quote_withdraw_is_one_owned_exact_served_journey(client, wired):
    matter_id, instruction, saved, checker = read(client, wired)
    assert checker.calls == [(
        instruction["original_id"], instruction["source_sha256"], WORDS.encode("utf8")
    )]
    assert saved["matter_version"] == instruction["version"] + 1
    assert saved["facts_established"] is False and saved["external_processing_granted"] is False
    assert saved["result"]["instruction"]["actor_id"] == "adv_demo"
    assert saved["result"]["extraction"]["complete"] is True
    assert "text" not in saved["result"]["extraction"]["units"][0]
    assert saved["result"]["quarantine"]["state"] == "released"
    version = saved["matter_version"]
    found = search(client, matter_id, version)
    assert found.status_code == 200, found.text
    assert found.headers["cache-control"] == "no-store"
    assert found.headers["x-content-type-options"] == "nosniff"
    result = found.json()["result"]
    assert result["searched"] == [instruction["original_id"]] and not result["partial"]
    assert result["matches"][0]["words"] == "4 March"
    body = quote_request(result["matches"][0]["source"], version)
    quoted = post(client, matter_id, "quote", body)
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()["result"]["text"] == "4 March"
    assert quoted.json()["result"]["source"]["facts_established"] is False
    assert quoted.json()["result"]["source"]["representation"] == "local_extracted_text"
    original = client.get(
        f"/api/matters/{matter_id}/uploads/{instruction['original_id']}/content"
    )
    assert original.status_code == 423
    derivative = saved["result"]["derivative"]
    sealed_path = wired.documents.derivatives.inner._path(matter_id, derivative["id"])
    assert WORDS.encode("utf8") not in sealed_path.read_bytes()
    assert wired.store.load(matter_id).facts == ()
    withdrawn = post(client, matter_id, "revoke", {
        "version": version, "original_id": instruction["original_id"]
    })
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["result"]["revoked_at"]
    version = withdrawn.json()["matter_version"]
    after = search(client, matter_id, version)
    assert after.status_code == 200
    assert after.json()["result"]["partial"] and not after.json()["result"]["matches"]
    assert post(client, matter_id, "quote", {**body, "version": version}).status_code == 422
    retry = post(client, matter_id, "analyse", {**instruction, "version": version})
    assert retry.status_code == 422
    assert len(checker.calls) == 1 and sealed_path.exists()


def test_default_missing_checker_stays_unassessed_and_unread_on_wire(client, wired):
    assert wired.documents.quarantine is None
    matter_id, instruction = upload(client)
    refused = post(client, matter_id, "analyse", instruction)
    assert refused.status_code == 422, refused.text
    assert WORDS not in refused.text
    after = search(client, matter_id, instruction["version"])
    assert after.status_code == 200
    assert after.json()["result"]["partial"] and not after.json()["result"]["searched"]
    assert "document_reading" not in wired.store.load(matter_id).uploads[instruction["original_id"]]


@pytest.mark.parametrize("extra", [
    {"actor_id": "adv_other"}, {"quarantine": "released"},
    {"checker": "trusted"}, {"parser": "arbitrary"},
    {"external_processing_granted": True}, {"clearance_digest": "a" * 64},
])
def test_request_cannot_self_authenticate_or_release_or_choose_processor(client, wired, extra):
    checker = ControlledLocalChecker()
    wired.documents.quarantine = checker
    matter_id, instruction = upload(client)
    refused = post(client, matter_id, "analyse", {**instruction, **extra})
    assert refused.status_code == 422
    assert not checker.calls
    assert wired.store.load(matter_id).version == instruction["version"]


@pytest.mark.parametrize("changed", [
    {"version": 1}, {"version": True}, {"asset_version": 2},
    {"asset_version": True}, {"source_sha256": "a" * 64},
    {"source_sha256": "not-a-hash"}, {"analysis_allowed": "true"},
])
def test_exact_current_version_original_and_strict_permission_precede_bytes(client, wired, changed):
    checker = ControlledLocalChecker()
    wired.documents.quarantine = checker
    matter_id, instruction = upload(client)
    refused = post(client, matter_id, "analyse", {**instruction, **changed})
    stale_version = type(changed.get("version")) is int and changed["version"] == 1
    assert refused.status_code == (409 if stale_version else 422)
    assert not checker.calls
    assert wired.store.load(matter_id).version == instruction["version"]


@pytest.mark.parametrize("action", ["analyse", "search", "quote", "revoke"])
def test_all_served_document_operations_refuse_foreign_owner_csrf_and_signed_out(client, wired,
                                                                               action):
    matter_id, instruction, saved, checker = read(client, wired)
    version = saved["matter_version"]
    found = search(client, matter_id, version).json()["result"]["matches"][0]["source"]
    bodies = {
        "analyse": {**instruction, "version": version},
        "search": {"version": version, "query": "March"},
        "quote": quote_request(found, version),
        "revoke": {"version": version, "original_id": instruction["original_id"]},
    }
    body = bodies[action]
    wrong_csrf = post(client, matter_id, action, body, headers={"x-nm-csrf": "wrong"})
    assert wrong_csrf.status_code == 403
    foreign_origin = post(client, matter_id, action, body, headers={"origin": "https://evil.test"})
    assert foreign_origin.status_code == 403
    foreign = client.sign_in("adv_other", fresh=True)
    assert post(foreign, matter_id, action, body).status_code == 404
    assert len(checker.calls) == 1 and wired.store.load(matter_id).version == version
    wrong_device = post(client, matter_id, action, body, headers={"user-agent": "other-device"})
    assert wrong_device.status_code == 401
    assert len(checker.calls) == 1 and wired.store.load(matter_id).version == version
    assert client.post("/api/logout").status_code == 200
    assert post(client, matter_id, action, body).status_code == 401
    assert len(checker.calls) == 1 and wired.store.load(matter_id).version == version


@pytest.mark.parametrize("state", [Quarantine.HELD, Quarantine.NOT_ASSESSED])
def test_checker_non_release_records_receipt_but_never_searchable_text(client, wired, state):
    checker = ControlledLocalChecker(state=state)
    wired.documents.quarantine = checker
    matter_id, instruction = upload(client)
    accepted = post(client, matter_id, "analyse", instruction)
    assert accepted.status_code == 200, accepted.text
    saved = accepted.json()
    assert saved["result"]["quarantine"]["state"] == state.value
    assert saved["result"]["derivative"] is None and saved["result"]["extraction"] is None
    found = search(client, matter_id, saved["matter_version"])
    assert found.status_code == 200
    assert found.json()["result"]["partial"] and not found.json()["result"]["matches"]
    assert wired.store.load(matter_id).facts == ()


def test_checker_result_cannot_identify_different_actual_bytes(client, wired):
    class WrongBytesChecker(ControlledLocalChecker):
        def inspect(self, original_id, source_sha256, data):
            return replace(super().inspect(original_id, source_sha256, data),
                           source_sha256="a" * 64)

    checker = WrongBytesChecker()
    wired.documents.quarantine = checker
    matter_id, instruction = upload(client)
    assert post(client, matter_id, "analyse", instruction).status_code == 422
    assert len(checker.calls) == 1
    assert wired.store.load(matter_id).version == instruction["version"]


def test_withdrawn_session_during_checker_does_not_parse_or_commit(client, wired, monkeypatch):
    parsed = []
    actual = wired.documents.parser.inner.extract

    def observed_extract(*args, **kwargs):
        parsed.append(True)
        return actual(*args, **kwargs)

    monkeypatch.setattr(wired.documents.parser.inner, "extract", observed_extract)
    matter_id, instruction = upload(client)
    checker = ControlledLocalChecker(after_read=lambda: client.post("/api/logout"))
    wired.documents.quarantine = checker
    refused = post(client, matter_id, "analyse", instruction)
    assert refused.status_code == 422, refused.text
    assert len(checker.calls) == 1 and not parsed
    matter = wired.store.load(matter_id)
    assert matter.version == instruction["version"]
    assert "document_reading" not in matter.uploads[instruction["original_id"]]
    assert matter.facts == ()


def test_corrupt_original_precedes_checker_parser_and_does_not_leak(client, wired):
    checker = ControlledLocalChecker()
    wired.documents.quarantine = checker
    matter_id, instruction = upload(client)
    row = wired.store.load(matter_id).uploads[instruction["original_id"]]
    chunk = row["chunks"][0]
    path = wired.uploads.objects.inner._path(matter_id, chunk["object_id"])
    path.write_bytes(b"broken sealed object")
    refused = post(client, matter_id, "analyse", instruction)
    assert refused.status_code == 503, refused.text
    assert WORDS not in refused.text and str(path) not in refused.text
    assert not checker.calls
    assert wired.store.load(matter_id).version == instruction["version"]


def test_session_withdrawn_during_parse_stops_derivative_dispatch(client, wired, monkeypatch):
    original_extract = wired.documents.parser.inner.extract
    original_put = wired.documents.derivatives.inner.put
    stored = []

    def observed_extract(*args, **kwargs):
        result = original_extract(*args, **kwargs)
        assert client.post("/api/logout").status_code == 200
        return result

    def observed_put(*args, **kwargs):
        stored.append(True)
        return original_put(*args, **kwargs)

    monkeypatch.setattr(wired.documents.parser.inner, "extract", observed_extract)
    monkeypatch.setattr(wired.documents.derivatives.inner, "put", observed_put)
    wired.documents.quarantine = ControlledLocalChecker()
    matter_id, instruction = upload(client)
    refused = post(client, matter_id, "analyse", instruction)
    assert refused.status_code == 422, refused.text
    assert not stored
    matter = wired.store.load(matter_id)
    assert matter.version == instruction["version"]
    assert "document_reading" not in matter.uploads[instruction["original_id"]]


@pytest.mark.parametrize("change", ["session", "file_version"])
@pytest.mark.parametrize("boundary", ["original", "quarantine", "parser"])
def test_analysis_rechecks_authority_after_each_slow_boundary_before_next_sink(
    client, wired, monkeypatch, change, boundary
):
    matter_id, instruction = upload(client)
    dispatched = []
    actual_original = wired.documents.uploads.verified_original
    actual_parser = wired.documents.parser.inner.extract
    actual_put = wired.documents.derivatives.inner.put

    def observed_original(*args, **kwargs):
        result = actual_original(*args, **kwargs)
        if boundary == "original":
            invalidate(client, wired, matter_id, change)
        return result

    def observed_parser(*args, **kwargs):
        dispatched.append("parser")
        result = actual_parser(*args, **kwargs)
        if boundary == "parser":
            invalidate(client, wired, matter_id, change)
        return result

    def observed_put(*args, **kwargs):
        dispatched.append("derivative")
        return actual_put(*args, **kwargs)

    checker = ControlledLocalChecker(
        after_read=(lambda: invalidate(client, wired, matter_id, change))
        if boundary == "quarantine" else None
    )
    wired.documents.quarantine = checker
    monkeypatch.setattr(wired.documents.uploads, "verified_original", observed_original)
    monkeypatch.setattr(wired.documents.parser.inner, "extract", observed_parser)
    monkeypatch.setattr(wired.documents.derivatives.inner, "put", observed_put)
    refused = post(client, matter_id, "analyse", instruction)
    assert refused.status_code == 422, refused.text
    assert bool(checker.calls) is (boundary != "original")
    assert dispatched == (["parser"] if boundary == "parser" else [])
    matter = wired.store.load(matter_id)
    assert "document_reading" not in matter.uploads[instruction["original_id"]]
    assert matter.version == instruction["version"] + (change == "file_version")
    assert matter.facts == ()


@pytest.mark.parametrize("change", ["session", "file_version"])
@pytest.mark.parametrize("boundary", ["original", "derivative"])
@pytest.mark.parametrize("action", ["search", "quote"])
def test_search_and_quote_recheck_authority_between_protected_reads_and_before_disclosure(
    client, wired, monkeypatch, change, boundary, action
):
    matter_id, instruction, saved, _checker = read(client, wired)
    version = saved["matter_version"]
    found = search(client, matter_id, version).json()["result"]["matches"][0]["source"]
    actual_original = wired.documents.uploads.verified_original
    actual_derivative = wired.documents.derivatives.inner.read
    opened = []

    def observed_original(*args, **kwargs):
        result = actual_original(*args, **kwargs)
        if boundary == "original":
            invalidate(client, wired, matter_id, change)
        return result

    def observed_derivative(*args, **kwargs):
        opened.append(True)
        result = actual_derivative(*args, **kwargs)
        if boundary == "derivative":
            invalidate(client, wired, matter_id, change)
        return result

    monkeypatch.setattr(wired.documents.uploads, "verified_original", observed_original)
    monkeypatch.setattr(wired.documents.derivatives.inner, "read", observed_derivative)
    body = {"version": version, "query": "4 March"} if action == "search" \
        else quote_request(found, version)
    refused = post(client, matter_id, action, body)
    assert refused.status_code == 422, refused.text
    assert "4 March" not in refused.text
    assert opened == ([True] if boundary == "derivative" else [])
    matter = wired.store.load(matter_id)
    assert matter.version == version + (change == "file_version")
    assert matter.uploads[instruction["original_id"]]["document_reading"] == saved["result"]


@pytest.mark.parametrize("change", ["session", "file_version"])
@pytest.mark.parametrize("action", ["analyse", "search", "quote"])
def test_long_original_stops_after_first_chunk_when_authority_changes(
    client, wired, monkeypatch, change, action
):
    checker = ControlledLocalChecker()
    wired.documents.quarantine = checker
    matter_id, instruction = upload(client, chunk_size=12)
    assert len(wired.store.load(matter_id).uploads[instruction["original_id"]]["chunks"]) > 1
    version = instruction["version"]
    if action == "analyse":
        body = instruction
    else:
        accepted = post(client, matter_id, "analyse", instruction)
        assert accepted.status_code == 200, accepted.text
        version = accepted.json()["matter_version"]
        found = search(client, matter_id, version).json()["result"]["matches"][0]["source"]
        body = {"version": version, "query": "4 March"} if action == "search" \
            else quote_request(found, version)
    actual_read = wired.uploads.objects.inner.read
    opened = []

    def observed_read(*args, **kwargs):
        opened.append(args[1])
        result = actual_read(*args, **kwargs)
        invalidate(client, wired, matter_id, change)
        return result

    monkeypatch.setattr(wired.uploads.objects.inner, "read", observed_read)
    refused = post(client, matter_id, action, body)
    assert refused.status_code == 422, refused.text
    assert "4 March" not in refused.text and len(opened) == 1
    assert len(checker.calls) == (0 if action == "analyse" else 1)
    matter = wired.store.load(matter_id)
    assert matter.version == version + (change == "file_version")
    assert matter.facts == ()
    if action == "analyse":
        assert "document_reading" not in matter.uploads[instruction["original_id"]]


def test_corrupt_derivative_cannot_be_quoted_as_checked_text(client, wired):
    matter_id, _instruction, saved, _checker = read(client, wired)
    version = saved["matter_version"]
    found = search(client, matter_id, version).json()["result"]["matches"][0]["source"]
    derivative = saved["result"]["derivative"]
    path = wired.documents.derivatives.inner._path(matter_id, derivative["id"])
    path.write_bytes(b"broken sealed derivative")
    refused = post(client, matter_id, "quote", quote_request(found, version))
    assert refused.status_code == 422, refused.text
    assert WORDS not in refused.text and str(path) not in refused.text
    searched = search(client, matter_id, version)
    assert searched.status_code == 200, searched.text
    assert not searched.json()["result"]["matches"] and searched.json()["result"]["partial"]


@pytest.mark.parametrize("changed", [
    {"derivative_sha256": "a" * 64}, {"source_sha256": "b" * 64},
    {"start": True}, {"end": 100000}, {"part": "a different source window"},
])
def test_quoted_window_cannot_launder_stale_or_different_provenance(client, wired, changed):
    matter_id, _instruction, saved, _checker = read(client, wired)
    version = saved["matter_version"]
    found = search(client, matter_id, version).json()["result"]["matches"][0]["source"]
    refused = post(client, matter_id, "quote", {**quote_request(found, version), **changed})
    assert refused.status_code == 422, refused.text
    assert "4 March" not in refused.text


@pytest.mark.parametrize("action", ["analyse", "quote", "revoke"])
def test_unknown_original_is_safe_refusal_not_an_unhandled_server_failure(client, wired, action):
    matter_id, instruction, saved, checker = read(client, wired)
    version = saved["matter_version"]
    found = search(client, matter_id, version).json()["result"]["matches"][0]["source"]
    bodies = {
        "analyse": {**instruction, "version": version},
        "quote": quote_request(found, version),
        "revoke": {"version": version, "original_id": instruction["original_id"]},
    }
    refused = post(client, matter_id, action, {**bodies[action], "original_id": "unknown_original"})
    assert refused.status_code == 404, refused.text
    assert WORDS not in refused.text
    assert len(checker.calls) == 1 and wired.store.load(matter_id).version == version
