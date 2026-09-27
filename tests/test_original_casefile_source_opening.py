"""The real normal-casefile/original transport, not a test-only reader route.

The configured scanner is explicitly controlled local test configuration. These
tests establish custody, permission and UI controls, not production clearance,
semantic fact correctness or browser-native PDF rendering acceptance.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from nm.arrive.advocate_contracts import utcnow
from nm.close import retention as rt
from nm.close.retention_contracts import (
    AssetRef,
    RequestedAction,
    RequestScope,
    RetentionRequest,
    RetentionState,
    Tombstone,
)
from nm.open_matter.intake_contracts import ReadQuality
from nm.work_the_file.casefile import build
from nm.work_the_file.matter_contracts import Certainty, Fact, Provenance
from nm.work_the_file.original_source_locators import MAX_ORIGINAL_VIEW_BYTES, add_original_locators
from tests.test_document_transport_keeps_local_reading_permission_separate import (
    WORDS,
    ControlledLocalChecker,
    invalidate,
    post,
    read,
    upload,
)

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def params(instruction, version):
    return {"view": "original", "version": version,
            "asset_version": instruction["asset_version"],
            "source_sha256": instruction["source_sha256"], "purpose": "human_original_inspection"}


def endpoint(matter_id, original_id):
    return f"/api/matters/{matter_id}/uploads/{original_id}/content"


def seed_fact(wired, matter_id, document, *, page=1):
    matter = wired.store.load(matter_id)
    fact = Fact.create("The supplied original is said to record payment.",
        Provenance("document", "controlled_source_turn", document, page, "Recorded paragraph"),
        certainty=Certainty.ASSERTED, confirmed=None, read_quality=ReadQuality.CLEAR)
    return wired.store.commit(replace(matter, facts=(fact,), version=matter.version + 1),
                              expected_version=matter.version)


def test_the_normal_casefile_opens_its_exact_original_without_confirming_or_rewriting_facts(client, wired):
    matter_id, instruction, saved, checker = read(client, wired)
    matter = seed_fact(wired, matter_id, instruction["original_id"])
    before = wired.store.load(matter_id)
    response = client.get(f"/api/matters/{matter_id}/casefile")
    assert response.status_code == 200, response.text
    source = response.json()["entries"][0]["attribution"]
    locator = source["original"]
    assert locator == {"original_id": instruction["original_id"], "matter_version": matter.version,
        "asset_version": instruction["asset_version"], "source_sha256": instruction["source_sha256"],
        "byte_length": len(WORDS.encode("utf8")), "page": 1, "span": "Recorded paragraph"}
    url = endpoint(matter_id, locator["original_id"])
    assert client.get(url).status_code == 423  # Holding alone still never opens bytes.
    opened = client.get(url, params=params(instruction, matter.version))
    assert opened.status_code == 200, opened.text
    result = opened.json()
    assert result["state"] == "original_opened" and result["representation"] == "original_bytes"
    assert result["facts_established"] is False and result["purpose"] == "human_original_inspection"
    assert result["format"] == "text"
    assert base64.b64decode(result["content_base64"], validate=True) == WORDS.encode("utf8")
    assert opened.headers["cache-control"] == "no-store"
    assert opened.headers["x-content-type-options"] == "nosniff"
    assert len(checker.calls) == 1  # Opening neither invents a new clearance nor parses again.
    after = wired.store.load(matter_id)
    assert after == before and after.facts[0].confirmed is None
    assert after.facts[0].certainty is Certainty.ASSERTED
    assert after.uploads[instruction["original_id"]]["document_reading"] == saved["result"]


@pytest.mark.parametrize("document", ["private.txt", "https://elsewhere.test/private.txt", "missing_upload"])
def test_legacy_filename_url_or_missing_source_never_resolves_by_name(client, wired, document):
    matter_id, instruction, _saved, _checker = read(client, wired)
    seed_fact(wired, matter_id, document)
    response = client.get(f"/api/matters/{matter_id}/casefile")
    assert response.status_code == 200
    source = response.json()["entries"][0]["attribution"]
    assert source["original"] is None and "No filename or URL was substituted" in source["original_unavailable"]
    assert source["document"] == document


@pytest.mark.parametrize("change,status", [({"version": "true"}, 422), ({"asset_version": "true"}, 422),
    ({"asset_version": 2}, 409), ({"source_sha256": "a" * 64}, 409), ({"source_sha256": "not-a-hash"}, 409),
    ({"purpose": "automatic_analysis"}, 409), ({"view": "unquarantined"}, 423)])
def test_exact_version_asset_hash_and_inspection_purpose_precede_any_byte_read(client, wired, monkeypatch, change, status):
    matter_id, instruction, saved, _checker = read(client, wired)
    calls = []
    actual = wired.uploads.objects.inner.read
    monkeypatch.setattr(wired.uploads.objects.inner, "read", lambda *args, **kwargs:
                        (calls.append(True), actual(*args, **kwargs))[1])
    response = client.get(endpoint(matter_id, instruction["original_id"]),
        params={**params(instruction, saved["matter_version"]), **change})
    assert response.status_code == status, response.text
    assert not calls and "content_base64" not in response.text


def test_stale_casefile_version_and_foreign_owner_cannot_open_current_original(client, wired):
    matter_id, instruction, saved, _checker = read(client, wired)
    url = endpoint(matter_id, instruction["original_id"])
    stale = client.get(url, params=params(instruction, instruction["version"]))
    assert stale.status_code == 409, stale.text
    foreign = client.sign_in("adv_original_stranger", fresh=True)
    assert foreign.get(url, params=params(instruction, saved["matter_version"])).status_code == 404
    assert client.get(url, params=params(instruction, saved["matter_version"]),
                      headers={"user-agent": "another-device"}).status_code == 401
    assert client.post("/api/logout").status_code == 200
    assert client.get(url, params=params(instruction, saved["matter_version"])).status_code == 401


def test_holding_permission_without_current_local_analysis_never_opens_original(client, wired, monkeypatch):
    matter_id, instruction = upload(client)
    calls = []
    monkeypatch.setattr(wired.uploads.objects.inner, "read", lambda *args, **kwargs: calls.append(True))
    response = client.get(endpoint(matter_id, instruction["original_id"]),
                          params=params(instruction, instruction["version"]))
    assert response.status_code == 409, response.text
    assert not calls and "content_base64" not in response.text
    assert wired.store.load(matter_id).facts == ()


@pytest.mark.parametrize("shape", ["duplicate", "missing", "extra"])
def test_original_view_accepts_only_one_complete_exact_query(client, wired, monkeypatch, shape):
    matter_id, instruction, saved, _checker = read(client, wired)
    query = list(params(instruction, saved["matter_version"]).items())
    if shape == "duplicate":
        query.append(("asset_version", 1))
    elif shape == "missing":
        query = [(key, value) for key, value in query if key != "purpose"]
    else:
        query.append(("caller_clearance", "released"))
    calls = []
    monkeypatch.setattr(wired.uploads.objects.inner, "read", lambda *args, **kwargs: calls.append(True))
    response = client.get(endpoint(matter_id, instruction["original_id"]), params=query)
    assert response.status_code == 422, response.text
    assert not calls and "content_base64" not in response.text


def test_missing_local_read_owner_never_uses_the_upload_store_as_an_alternate_reader(client, wired):
    matter_id, instruction, saved, _checker = read(client, wired)
    wired.documents = None
    response = client.get(endpoint(matter_id, instruction["original_id"]),
                          params=params(instruction, saved["matter_version"]))
    assert response.status_code == 503 and "content_base64" not in response.text


@pytest.mark.parametrize("change", ["withdrawn", "clearance", "restriction", "tombstone", "expired", "damaged_derivative", "damaged_original"])
def test_current_permission_clearance_retention_and_integrity_are_not_replaced_by_a_saved_locator(client, wired, change):
    matter_id, instruction, saved, _checker = read(client, wired)
    matter = wired.store.load(matter_id)
    uploads = deepcopy(matter.uploads)
    row = uploads[instruction["original_id"]]
    retained = matter.retention
    if change == "withdrawn":
        row["document_reading"]["revoked_at"] = utcnow().isoformat()
    elif change == "clearance":
        row["document_reading"]["clearance_digest"] = "a" * 64
    elif change in {"restriction", "tombstone"}:
        record = RetentionRequest("controlled_original_retention", matter_id, matter.advocate_id,
            utcnow().isoformat(), RequestScope.SELECTED_ASSETS, RequestedAction.RESTRICT_ACCESS,
            "Controlled current custody restriction", "controlled_owner", 1,
            assets=(AssetRef(instruction["original_id"], 1),), state=RetentionState.APPROVED)
        if change == "tombstone":
            record = replace(record, requested_action=RequestedAction.ERASE,
                tombstones=(Tombstone(instruction["original_id"], 1, utcnow().isoformat(), record.request_id),))
        retained = (rt.as_dict(record),)
    elif change == "expired":
        row["offer"]["retention"] = "fixed_period"
        row["offer"]["retain_until"] = utcnow().date().isoformat()
    elif change == "damaged_derivative":
        derivative = saved["result"]["derivative"]
        # Controlled corruption of this test-only sealed object, not another store.
        path = wired.documents.derivatives.inner._path(matter_id, derivative["id"])
        path.write_bytes(b"controlled damaged sealed derivative")
    else:
        path = wired.uploads.objects.inner._path(matter_id, row["chunks"][0]["object_id"])
        path.write_bytes(b"controlled damaged sealed original")
    saved_matter = wired.store.commit(replace(matter, uploads=uploads, retention=retained,
        version=matter.version + 1), expected_version=matter.version)
    response = client.get(endpoint(matter_id, instruction["original_id"]),
                          params=params(instruction, saved_matter.version))
    assert response.status_code == 409, response.text
    assert "content_base64" not in response.text and WORDS not in response.text
    assert wired.store.load(matter_id).version == saved_matter.version


@pytest.mark.parametrize("change", ["session", "file_version"])
@pytest.mark.parametrize("boundary", ["first_chunk", "derivative", "final_original"])
def test_original_read_rechecks_authority_between_sinks_and_before_disclosure(client, wired, monkeypatch, change, boundary):
    checker = ControlledLocalChecker()
    wired.documents.quarantine = checker
    matter_id, instruction = upload(client, chunk_size=12)
    saved = post(client, matter_id, "analyse", instruction).json()
    opened = []
    if boundary == "first_chunk":
        target, method = wired.uploads.objects.inner, "read"
    elif boundary == "derivative":
        target, method = wired.documents.derivatives.inner, "read"
    else:
        target, method = wired.documents.uploads, "verified_original"
    actual = getattr(target, method)
    def observed(*args, **kwargs):
        opened.append(True)
        result = actual(*args, **kwargs)
        if boundary != "final_original" or len(opened) == 2:
            invalidate(client, wired, matter_id, change)
        return result
    monkeypatch.setattr(target, method, observed)
    response = client.get(endpoint(matter_id, instruction["original_id"]),
                          params=params(instruction, saved["matter_version"]))
    assert response.status_code in {401, 409, 422}, response.text
    assert "content_base64" not in response.text and WORDS not in response.text
    assert len(opened) == (2 if boundary == "final_original" else 1)


def test_original_transport_bound_is_applied_before_any_protected_read_or_base64(client, wired, monkeypatch):
    matter_id, instruction, saved, _checker = read(client, wired)
    matter = wired.store.load(matter_id)
    uploads = deepcopy(matter.uploads)
    uploads[instruction["original_id"]]["receipt"]["observed_size"] = MAX_ORIGINAL_VIEW_BYTES + 1
    current = wired.store.commit(replace(matter, uploads=uploads, version=matter.version + 1),
                                expected_version=matter.version)
    calls = []
    monkeypatch.setattr(wired.uploads.objects.inner, "read", lambda *args, **kwargs: calls.append(True))
    response = client.get(endpoint(matter_id, instruction["original_id"]),
                          params=params(instruction, current.version))
    assert response.status_code == 409, response.text
    assert not calls and "content_base64" not in response.text


def test_original_locator_projection_is_fresh_and_cannot_be_applied_to_another_file(client, wired):
    matter_id, instruction, _saved, _checker = read(client, wired)
    matter = seed_fact(wired, matter_id, instruction["original_id"])
    projection = build(matter)
    enriched = add_original_locators(projection, matter)
    assert "original" not in projection["entries"][0]["attribution"]
    assert enriched["entries"][0]["attribution"]["original"]["original_id"] == instruction["original_id"]
    with pytest.raises(ValueError):
        add_original_locators({**projection, "matter_id": "another"}, matter)


def test_the_shipped_original_controller_controls_run_without_a_browser_or_network():
    node = shutil.which("node")
    if node is None:
        pytest.skip("NOT ASSESSED: the original-source controller requires the local JS runtime")
    result = subprocess.run([node, "--test", str(ROOT / "tests/original-casefile-source.test.cjs")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# pass 12" in result.stdout and "# fail 0" in result.stdout
