"""P16 served original receipt. Scanning/transcription remain explicitly unproved."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from nm.domain.intake import MAX_CHUNK_BYTES, MAX_UPLOAD_BYTES

pytestmark = pytest.mark.class_a


def _application():
    from nm.edge.api import application

    return application()


def _shell(client, key="open-1"):
    response = client.post(
        "/api/matters/intake",
        json={
            "request_key": key,
            "title": "Synthetic original",
            "parties": {"Fixture Co": "client"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["matter_id"]


def _begin(client, matter_id, data=b"synthetic original", **changes):
    body = {
        "request_key": "original-1",
        "filename": "synthetic.txt",
        "declared_size": len(data),
        "purpose": "review the supplied exhibit",
        "authority": "synthetic client instruction, recorded by advocate",
        "retention": "matter_life",
        "declared_type": "text/plain",
        "declared_hash": hashlib.sha256(data).hexdigest(),
        **changes,
    }
    response = client.post(f"/api/matters/{matter_id}/uploads", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _url(matter_id, upload):
    return f"/api/matters/{matter_id}/uploads/{upload['asset_id']}"


def test_upload_first_is_real_without_a_placeholder_brief_or_a_model_call(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("receiving an original must not call the legal model")

    monkeypatch.setattr(_application().engine, "run", forbidden)
    matter_id = _shell(client)
    assert _shell(client) == matter_id
    held = _application().store.load(matter_id)
    assert held.version == 1
    assert held.facts == () and held.threads == () and held.screens == ()
    assert held.intake_parties == {"Fixture Co": "client"}
    listed = client.get("/api/matters").json()["matters"]
    assert any(row["matter_id"] == matter_id for row in listed)
    changed = client.post(
        "/api/matters/intake", json={"request_key": "open-1", "title": "Different matter"}
    )
    assert changed.status_code == 409


def test_original_resumes_after_adapter_restart_with_real_digest_and_held_locator(client, tmp_path):
    from nm.adapters.store.file_store import FileMatterStore
    from nm.edge.uploads import UploadService
    from tests.test_turn_contract import KEY

    data = b"%PDF-1.7\nSYNTHETIC-NOT-A-VALID-PDF\n"
    matter_id = _shell(client)
    upload = _begin(client, matter_id, data, declared_type="audio/wav")
    url = _url(matter_id, upload)
    first = client.put(url + "/chunks/0", content=data[:9])
    assert first.status_code == 200, first.text
    assert first.json()["receipt"]["observed_size"] == 9
    # A fresh store and byte adapter read the saved state; no Python session
    # or hash object is needed to resume the original.
    store = FileMatterStore(tmp_path, key=KEY)
    resumed = UploadService(store, store.upload_storage())
    assert resumed.get(matter_id, "adv_demo", upload["asset_id"])["receipt"]["observed_size"] == 9
    resumed.append(matter_id, "adv_demo", upload["asset_id"], 9, data[9:])
    result = client.post(url + "/complete")
    assert result.status_code == 200, result.text
    row = result.json()
    assert row["receipt"]["state"] == "received"
    assert row["receipt"]["observed_hash"] == hashlib.sha256(data).hexdigest()
    assert row["receipt"]["observed_type"] == "application/pdf"
    assert row["receipt"]["declared_type"] == "audio/wav"
    assert row["format_assessment"] == "container_signature_only_not_validated"
    assert row["state"] == "uploaded" and row["quarantine"] == "not_assessed"
    assert row["reading"]["state"] == "not_assessed" and row["establishes_a_fact"] is False
    assert row["may_reach_reasoning"] is False
    assert row["original_locator"] == {
        "asset_id": upload["asset_id"],
        "version": 1,
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_length": len(data),
        "content_available": False,
        "reason": row["reason"],
    }
    assert client.get(url + "/content").status_code == 423
    assert client.post(url + "/complete").json() == row
    assert len(client.get(f"/api/matters/{matter_id}/uploads").json()["uploads"]) == 1
    assert store.load(matter_id).facts == ()
    files = list((tmp_path / "uploads").rglob("*.nm"))
    assert len(files) == 2
    for path in files:
        assert b"SYNTHETIC-NOT-A-VALID-PDF" not in path.read_bytes()
    assert not list((tmp_path / "uploads").rglob("*.tmp"))


def test_identical_requests_replay_but_keys_offsets_and_bytes_cannot_be_repurposed(client):
    matter_id = _shell(client)
    row = _begin(client, matter_id, b"abcdef")
    assert _begin(client, matter_id, b"abcdef")["asset_id"] == row["asset_id"]
    different = client.post(
        f"/api/matters/{matter_id}/uploads",
        json={
            "request_key": "original-1",
            "filename": "other.txt",
            "declared_size": 6,
            "purpose": "review",
            "authority": "named synthetic instruction",
            "retention": "matter_life",
        },
    )
    assert different.status_code == 409
    url = _url(matter_id, row)
    first = client.put(url + "/chunks/0", content=b"abc")
    assert first.status_code == 200
    assert client.put(url + "/chunks/0", content=b"abc").json() == first.json()
    assert client.put(url + "/chunks/0", content=b"xyz").status_code == 409
    assert client.put(url + "/chunks/4", content=b"ef").status_code == 409
    assert client.post(url + "/complete").status_code == 409
    assert client.get(url).json()["receipt"]["resumable"] is True
    assert client.put(url + "/chunks/3", content=b"def").status_code == 200
    assert client.post(url + "/complete").json()["receipt"]["state"] == "received"


@pytest.mark.parametrize(
    "changes",
    [
        {"purpose": ""},
        {"authority": ""},
        {"retention": "not_decided"},
        {"retention": "fixed_period"},
        {"retention": "fixed_period", "retain_until": "1900-01-01"},
        {"declared_hash": "invented"},
        {"declared_size": True},
        {"declared_size": MAX_UPLOAD_BYTES + 1},
        {"declared_size": 0},
    ],
)
def test_incomplete_permission_retention_or_bounds_refuse_before_bytes(client, tmp_path, changes):
    matter_id = _shell(client)
    body = {
        "request_key": "x",
        "filename": "a",
        "declared_size": 1,
        "purpose": "review",
        "authority": "synthetic instruction",
        "retention": "matter_life",
        **changes,
    }
    response = client.post(f"/api/matters/{matter_id}/uploads", json=body)
    assert response.status_code in (413, 422), response.text
    assert client.get(f"/api/matters/{matter_id}/uploads").json()["uploads"] == []
    assert not (tmp_path / "uploads").exists()


def test_observed_stream_and_original_bounds_do_not_trust_content_length(client, tmp_path):
    matter_id = _shell(client)
    row = _begin(client, matter_id, b"ab")
    url = _url(matter_id, row)
    assert client.put(url + "/chunks/0", content=b"abc").status_code == 413
    response = client.put(
        url + "/chunks/0", content=b"x" * (MAX_CHUNK_BYTES + 1), headers={"content-length": "1"}
    )
    assert response.status_code == 413
    assert client.get(url).json()["receipt"]["observed_size"] == 0
    assert not (tmp_path / "uploads").exists()


def test_cancelled_receipt_stops_new_bytes_without_claiming_deletion(client):
    matter_id = _shell(client)
    row = _begin(client, matter_id, b"ab")
    url = _url(matter_id, row)
    assert client.put(url + "/chunks/0", content=b"a").status_code == 200
    cancelled = client.post(url + "/cancel")
    assert cancelled.json()["receipt"]["state"] == "cancelled"
    assert "not deleted" in cancelled.json()["receipt"]["note"]
    assert client.post(url + "/cancel").json() == cancelled.json()
    assert client.put(url + "/chunks/1", content=b"b").status_code == 409
    assert client.post(url + "/complete").json()["state"] == "not_assessed"


def test_different_owners_cannot_inspect_append_complete_or_cancel_originals(client, tmp_path):
    matter_id = _shell(client)
    row = _begin(client, matter_id, b"ab")
    url = _url(matter_id, row)
    other = client.sign_in("adv_stranger", fresh=True)
    assert other.get(url).status_code == 404
    assert other.get(f"/api/matters/{matter_id}/uploads").status_code == 404
    assert other.put(url + "/chunks/0", content=b"ab").status_code == 404
    assert other.post(url + "/complete").status_code == 404
    assert other.post(url + "/cancel").status_code == 404
    assert other.get(url + "/content").status_code == 404
    assert not (tmp_path / "uploads").exists()


def test_receipt_requires_csrf_and_a_live_authenticated_session(client):
    matter_id = _shell(client)
    row = _begin(client, matter_id, b"a")
    url = _url(matter_id, row)
    assert (
        client.put(url + "/chunks/0", content=b"a", headers={"x-nm-csrf": "wrong"}).status_code
        == 403
    )
    client.cookies.clear()
    assert client.get(url).status_code == 401
    assert client.put(url + "/chunks/0", content=b"a").status_code in (401, 403)


def test_wrong_declared_hash_is_failed_integrity_not_received(client):
    matter_id = _shell(client)
    row = _begin(client, matter_id, b"actual", declared_hash="0" * 64)
    url = _url(matter_id, row)
    assert client.put(url + "/chunks/0", content=b"actual").status_code == 200
    result = client.post(url + "/complete").json()
    assert result["receipt"]["state"] == "failed_integrity"
    assert result["receipt"]["observed_hash"] == hashlib.sha256(b"actual").hexdigest()
    assert result["state"] == "not_assessed" and result["may_reach_reasoning"] is False


def test_failed_cas_leaves_old_receipt_and_only_unreferenced_sealed_bytes(
    client, tmp_path, monkeypatch
):
    from nm.ports.store import StaleWrite

    matter_id = _shell(client)
    row = _begin(client, matter_id, b"PRIVATE-SYNTHETIC")
    url = _url(matter_id, row)
    original = _application().store.inner.commit

    def stale(*args, **kwargs):
        raise StaleWrite("planted concurrent writer")

    monkeypatch.setattr(_application().store.inner, "commit", stale)
    result = client.put(url + "/chunks/0", content=b"PRIVATE-SYNTHETIC")
    assert result.status_code == 409
    monkeypatch.setattr(_application().store.inner, "commit", original)
    assert client.get(url).json()["receipt"]["observed_size"] == 0
    objects = list((tmp_path / "uploads").rglob("*.nm"))
    assert len(objects) == 1 and b"PRIVATE-SYNTHETIC" not in objects[0].read_bytes()
    assert client.put(url + "/chunks/0", content=b"PRIVATE-SYNTHETIC").status_code == 200
    assert client.post(url + "/complete").json()["receipt"]["state"] == "received"


def test_object_io_failure_and_corruption_never_publish_success(client, monkeypatch):
    matter_id = _shell(client)
    row = _begin(client, matter_id, b"abc")
    url = _url(matter_id, row)
    objects = _application().uploads.objects.inner
    original = objects.put

    def broken(*args):
        raise OSError("planted disk failure with private detail")

    monkeypatch.setattr(objects, "put", broken)
    response = client.put(url + "/chunks/0", content=b"abc")
    assert response.status_code == 503 and "private detail" not in response.text
    assert client.get(url).json()["receipt"]["observed_size"] == 0
    monkeypatch.setattr(objects, "put", original)
    assert client.put(url + "/chunks/0", content=b"abc").status_code == 200
    monkeypatch.setattr(objects, "read", lambda *args: b"xyz")
    assert client.post(url + "/complete").status_code == 409
    assert client.get(url).json()["receipt"]["state"] == "receiving"


def test_original_objects_cannot_be_overwritten_or_decrypted_under_another_matter(tmp_path):
    from nm.adapters.store.envelope import CrossMatterAccess
    from nm.adapters.store.file_store import FileMatterStore
    from tests.test_turn_contract import KEY

    store = FileMatterStore(tmp_path, key=KEY)
    objects = store.upload_storage()
    objects.put("m_one", "chunk_one", b"PRIVILEGED-SYNTHETIC")
    assert objects.read("m_one", "chunk_one") == b"PRIVILEGED-SYNTHETIC"
    with pytest.raises(FileExistsError):
        objects.put("m_one", "chunk_one", b"replacement")
    assert objects.read("m_one", "chunk_one") == b"PRIVILEGED-SYNTHETIC"
    sealed = objects._path("m_one", "chunk_one").read_bytes()
    with pytest.raises(CrossMatterAccess):
        objects._sealer.open("m_two", sealed)
    for invalid in ("../escape", "a/b", "a\\b", "C:", "."):
        with pytest.raises(ValueError):
            objects.put(invalid, "chunk_one", b"x")


@pytest.mark.parametrize("method", ["put", "read"])
def test_each_original_byte_port_method_is_policed_before_its_adapter(client, monkeypatch, method):
    from nm.domain.egress import EgressRefused, Gatekeeper, Policy

    wrapper = _application().uploads.objects
    called = []
    monkeypatch.setattr(wrapper.inner, method, lambda *args: called.append(args) or b"result")
    args = ("m_test", "chunk_test", b"x") if method == "put" else ("m_test", "chunk_test")
    assert getattr(wrapper, method)(*args) == b"result"
    assert called == [args]
    called.clear()
    monkeypatch.setattr(wrapper, "gate", Gatekeeper(policy=Policy()))
    with pytest.raises(EgressRefused):
        getattr(wrapper, method)(*args)
    assert called == []


def test_receipt_metadata_capacity_is_bounded_independently_of_declared_bytes(client, monkeypatch):
    import nm.edge.uploads as uploads

    matter_id = _shell(client)
    row = _begin(client, matter_id, b"abc")
    url = _url(matter_id, row)
    monkeypatch.setattr(uploads, "MAX_UPLOAD_CHUNKS", 1)
    assert client.put(url + "/chunks/0", content=b"a").status_code == 200
    assert client.put(url + "/chunks/1", content=b"b").status_code == 413
    assert client.get(url).json()["receipt"]["observed_size"] == 1
    # A changed unrelated matter field must survive the next receipt write.
    matter = _application().store.load(matter_id)
    _application().store.commit(
        replace(matter, title="Updated supplied title", version=matter.version + 1),
        expected_version=matter.version,
    )
    client.post(url + "/cancel")
    assert _application().store.load(matter_id).title == "Updated supplied title"


def _concurrent_results(operation, values, rendezvous):
    """Join every writer: one timeout must not hide its peer's real error."""
    from concurrent.futures import ThreadPoolExecutor

    def observed(value):
        try:
            return operation(value)
        except Exception:
            rendezvous.abort()
            raise

    results, errors = [], []
    with ThreadPoolExecutor(max_workers=len(values)) as pool:
        pending = [pool.submit(observed, value) for value in values]
        for future in pending:
            try:
                results.append(future.result())
            except Exception as error:
                errors.append(error)
    if errors:
        raise ExceptionGroup("concurrent writer failures (all peers observed)", errors)
    return results


@pytest.mark.parametrize("refused_bytes", [None, b"x", b"y"],
                         ids=["competing-writes", "first-peer-refuses", "second-peer-refuses"])
def test_real_concurrent_chunk_writers_cannot_overwrite_the_accepted_receipt(
        client, tmp_path, refused_bytes):
    from threading import Barrier

    from nm.adapters.store.file_store import FileMatterStore
    from nm.edge.uploads import UploadService
    from nm.ports.store import StaleWrite
    from tests.test_turn_contract import KEY

    matter_id = _shell(client)
    upload = _begin(client, matter_id, b"x", declared_hash="")
    starting_version = upload["version"]
    rendezvous = Barrier(2)

    class ConcurrentObjects:
        def __init__(self, inner):
            self.inner = inner

        def put(self, *args):
            if args[-1] == refused_bytes:
                raise OSError("planted immutable-object write refusal")
            self.inner.put(*args)
            rendezvous.wait(timeout=10)  # both writers derived from the same saved version

        def read(self, *args):
            return self.inner.read(*args)

    def write(data):
        store = FileMatterStore(tmp_path, key=KEY)
        service = UploadService(store, ConcurrentObjects(store.upload_storage()))
        try:
            return data, service.append(matter_id, "adv_demo", upload["asset_id"], 0, data)
        except StaleWrite:
            return data, "stale"

    if refused_bytes is not None:
        with pytest.raises(ExceptionGroup) as failed:
            _concurrent_results(write, (b"x", b"y"), rendezvous)
        assert any(isinstance(error, OSError) and "planted" in str(error)
                   for error in failed.value.exceptions), "the peer failure was masked"
        held = FileMatterStore(tmp_path, key=KEY).load(matter_id)
        assert held.version == starting_version
        assert held.uploads[upload["asset_id"]]["chunks"] == []
        return
    results = _concurrent_results(write, (b"x", b"y"), rendezvous)
    winners = [(data, result) for data, result in results if result != "stale"]
    assert len(winners) == 1 and sum(result == "stale" for _, result in results) == 1
    assert winners[0][1]["version"] == starting_version + 1
    held = FileMatterStore(tmp_path, key=KEY).load(matter_id)
    chunks = held.uploads[upload["asset_id"]]["chunks"]
    assert len(chunks) == 1 and chunks[0]["sha256"] == hashlib.sha256(winners[0][0]).hexdigest()
    completed = client.post(_url(matter_id, upload) + "/complete").json()
    assert completed["version"] == starting_version + 2
    assert completed["receipt"]["observed_hash"] == hashlib.sha256(winners[0][0]).hexdigest()


def test_new_upload_first_shell_is_not_overwritable_by_another_expected_zero_commit(client):
    from nm.domain.matter import Matter
    from nm.ports.store import StaleWrite

    matter_id = _shell(client)
    store = _application().store
    with pytest.raises(StaleWrite):
        store.commit(
            Matter(id=matter_id, advocate_id="adv_demo", title="Different", version=1),
            expected_version=0,
        )
    assert store.load(matter_id).title == "Synthetic original"


def test_opening_retry_uses_original_offer_and_never_reverts_later_instructions(client):
    matter_id = _shell(client)
    store = _application().store
    prior = store.load(matter_id)
    revised = replace(
        prior,
        title="Updated instruction",
        intake_parties={"New supplied party": "opponent"},
        version=prior.version + 1,
    )
    store.commit(revised, expected_version=prior.version)
    assert _shell(client) == matter_id
    held = store.load(matter_id)
    assert held.title == revised.title and held.intake_parties == revised.intake_parties
    assert held.version == revised.version
    assert held.intake_opening_offer == {
        "title": "Synthetic original",
        "parties": {"Fixture Co": "client"},
    }
    changed_offer = client.post(
        "/api/matters/intake",
        json={
            "request_key": "open-1",
            "title": "Updated instruction",
            "parties": {"New supplied party": "opponent"},
        },
    )
    assert changed_offer.status_code == 409
    assert store.load(matter_id).version == revised.version


def test_legacy_shell_without_original_identity_is_not_reconstructed_from_current_state(client):
    matter_id = _shell(client)
    store = _application().store
    prior = store.load(matter_id)
    store.commit(
        replace(prior, intake_opening_offer={}, version=prior.version + 1),
        expected_version=prior.version,
    )
    response = client.post(
        "/api/matters/intake",
        json={
            "request_key": "open-1",
            "title": "Synthetic original",
            "parties": {"Fixture Co": "client"},
        },
    )
    assert response.status_code == 409 and "identity is unavailable" in response.text
    assert store.load(matter_id).intake_opening_offer == {}
