"""Acts staged by an admin (plan AN.46, pieces 46m and 46o; owner decisions D122 and D125, 7 Nov 2026): chosen on the Library page, copied into a
folder of their own, read by the free reading job (the append job's own reading of an Act, without its encoder), approved once looked at, and
then appended by the owner's job with the server stopped. Nothing here puts a word into the library. Real reading job, synthetic Act text."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.composition import Application
from nm.app.main import create_app
from nm.arrive.admin_port import AdminChangeRefused, AdminStagingPort
from nm.arrive.admin_staging import MAX_FILES, AdminStaging
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
ACT = "1.\nShort title.\nThis Act may be called the Test Act, 2020.\n2.\nDefinitions.\n(1) In this Act, thing means a thing.\n(2) Nothing else.\n3.\nPowers.\nThe Government may make rules.\n"
NAME = "2020_5_The Test Act, 2020.txt"
ACT_ID = "UNION OF INDIA_2020_5_THE TEST ACT, 2020"


def staging(tmp_path, held=lambda: set(), **kw):
    return AdminStaging(tmp_path / "staging", root=ROOT, held=held, **kw)


def library_files(tmp_path):
    return sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file() and not p.is_relative_to(tmp_path / "staging"))


def test_it_is_the_staging_port(tmp_path):
    assert isinstance(staging(tmp_path), AdminStaging) and hasattr(AdminStagingPort, "stage")


def test_a_staged_act_is_read_by_the_free_job_and_its_sections_and_passages_are_told(tmp_path):
    batch = staging(tmp_path).stage("Union of India", [(NAME, ACT)], NOW)
    (act,) = batch["acts"]
    assert (batch["state"], batch["in_library"], batch["commands"]) == ("checked", False, [])
    assert (act["act_id"], act["sections"], act["passages"], act["ranges"], act["skipped"], act["already_held"]) == (ACT_ID, 3, 5, "1-3", 0, False)
    assert (tmp_path / "staging" / f"batch-{batch['id']}" / "files" / NAME).read_text(encoding="utf8") == ACT
    assert library_files(tmp_path) == []


def test_a_file_the_job_cannot_read_is_said_so_and_the_batch_needs_attention(tmp_path):
    batch = staging(tmp_path).stage("Union of India", [("2020_6_Empty Act.txt", "no sections here at all\njust words\n")], NOW)
    assert batch["state"] == "needs attention"


def test_an_act_the_library_already_holds_is_marked_and_the_batch_cannot_be_approved(tmp_path):
    stager = staging(tmp_path, held=lambda: {ACT_ID})
    batch = stager.stage("Union of India", [(NAME, ACT)], NOW)
    assert batch["state"] == "needs attention" and batch["acts"][0]["already_held"] is True and batch["in_library"] is True
    with pytest.raises(AdminChangeRefused) as refused:
        stager.approve(batch["id"], "admin@example.test", NOW)
    assert refused.value.status == 409


def test_approving_records_who_and_when_and_gives_the_two_commands_for_the_owner_in_order(tmp_path):
    stager = staging(tmp_path)
    batch = stager.stage("Telangana", [(NAME, ACT)], NOW)
    approved = stager.approve(batch["id"], "admin@example.test", NOW)
    assert (approved["state"], approved["approved_by"]) == ("approved", "admin@example.test")
    dry, real = approved["commands"]
    assert dry == real + " --dry-run" and "pipeline\\append_bare_acts.py" in real and '--jurisdiction "Telangana"' in real
    assert str(tmp_path / "staging" / f"batch-{batch['id']}" / "files" / NAME) in real
    assert stager.approve(batch["id"], "someone-else@example.test", NOW)["approved_by"] == "admin@example.test"  # saying it twice changes nothing


def test_once_the_library_holds_the_acts_the_batch_reads_in_the_library(tmp_path):
    held = set()
    stager = staging(tmp_path, held=lambda: held)
    batch = stager.stage("Union of India", [(NAME, ACT)], NOW)
    stager.approve(batch["id"], "admin@example.test", NOW)
    held.add(ACT_ID)
    (listed,) = stager.batches()
    assert listed["in_library"] is True and listed["state"] == "approved"


def test_discarding_removes_the_batch_and_nothing_else(tmp_path):
    stager = staging(tmp_path)
    first, second = stager.stage("Union of India", [(NAME, ACT)], NOW), stager.stage("Goa", [("2021_1_Other Act, 2021.txt", ACT)], NOW)
    assert stager.discard(first["id"]) is True
    assert [b["id"] for b in stager.batches()] == [second["id"]]
    with pytest.raises(AdminChangeRefused):
        stager.discard(first["id"])


@pytest.mark.parametrize("jurisdiction, files", [
    ("Union of India", [("../escape.txt", ACT)]), ("Union of India", [("notes.txt", ACT)]), ("Union of India", [(NAME, ACT), (NAME, ACT)]),
    ("Union of India", [(NAME, "")]), ("Union of India", []), ("", [(NAME, ACT)]), ("../../x", [(NAME, ACT)]), ("Union of India", [(NAME.replace(".txt", ".exe"), ACT)]),
    ("Union of India", [(f"2020_{n}_Act {n}.txt", ACT) for n in range(MAX_FILES + 1)])])
def test_a_name_a_size_or_a_count_that_is_not_allowed_is_refused_before_anything_is_written(tmp_path, jurisdiction, files):
    with pytest.raises(AdminChangeRefused) as refused:
        staging(tmp_path).stage(jurisdiction, files, NOW)
    assert refused.value.status == 422 and not (tmp_path / "staging").exists()


def test_a_batch_id_is_only_ever_twelve_hex_characters(tmp_path):
    for bad in ("../x", "..", "batch-1", "ABCDEF123456", "", "a" * 13):
        with pytest.raises(AdminChangeRefused) as refused:
            staging(tmp_path).approve(bad, "a@example.test", NOW)
        assert refused.value.status == 404


def test_a_reading_that_does_not_finish_in_time_says_nothing_was_checked(tmp_path):
    batch = staging(tmp_path, timeout=0).stage("Union of India", [(NAME, ACT)], NOW)
    assert batch["state"] == "needs attention" and "nothing was checked" in batch["problem"] and batch["acts"] == []


def test_an_unreadable_batch_is_listed_as_such_and_the_others_stand(tmp_path):
    stager = staging(tmp_path)
    good = stager.stage("Union of India", [(NAME, ACT)], NOW)
    broken = tmp_path / "staging" / "batch-0123456789ab"
    broken.mkdir()
    (broken / "batch.json").write_text("{not json", encoding="utf8")
    listed = {b["id"]: b for b in stager.batches()}
    assert listed["0123456789ab"] == {"id": "0123456789ab", "unreadable": True} and listed[good["id"]]["state"] == "checked"


# ------------------------------------------------------------------------- the routes ---

ADMIN, VIEWER, ADVOCATE = "admin@example.test", "viewer@example.test", "advocate@example.test"


@pytest.fixture
def served(tmp_path, monkeypatch):
    directory = FileDirectory(tmp_path, key=KEY)
    for who in (ADMIN, VIEWER, ADVOCATE):
        directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=ROOT, model=model, store=FileMatterStore(tmp_path, key=KEY), directory=directory, mail=FileOutbox(tmp_path, key=KEY),
                      legal_search=searcher(), audit_root=tmp_path / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1",
                          "NM_EMBED_MODEL": "text-embedding-3-large", "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"),
                          "NM_CORPUS_DIR": str(tmp_path / "no-law"), "NM_ADMINS": f"{ADMIN}:admin,{VIEWER}:view-only"})
    monkeypatch.setattr(api, "_application", app)
    asgi = create_app(app)
    clients = []

    def login(who, *, confirmed=False):
        client = TestClient(asgi)
        clients.append(client)
        assert client.post("/api/login", headers={"origin": "http://testserver"}, json={"advocate_id": who, "password": PASSWORD}).status_code == 200
        client.headers.update({"origin": "http://testserver", "x-nm-csrf": client.cookies.get("nm_csrf")})
        if confirmed:
            assert client.post("/api/admin/password", json={"password": PASSWORD}).status_code == 200
        return client

    class Served:
        pass

    made = Served()
    made.app, made.login, made.tmp_path = app, staticmethod(login), tmp_path
    yield made
    for client in clients:
        client.close()


def stage(client, reason="Acts the chambers asked for"):
    return client.post("/api/admin/library/acts/stage", json={"jurisdiction": "Union of India", "reason": reason, "files": [{"name": NAME, "text": ACT}]})


def audit(served):
    return [(e.action, e.outcome) for e in reversed(served.app.admin_record.entries(limit=20))]


def test_an_admin_stages_approves_and_discards_through_the_one_change_path_and_each_step_is_audited(served):
    admin = served.login(ADMIN, confirmed=True)
    reply = stage(admin)
    assert reply.status_code == 200, reply.text
    batch = reply.json()["batch"]
    assert batch["state"] == "checked" and batch["acts"][0]["sections"] == 3
    listed = admin.get("/api/admin/library/batches").json()["batches"]
    assert [b["id"] for b in listed] == [batch["id"]]
    approved = admin.post(f"/api/admin/library/batches/{batch['id']}/approve", json={"reason": "Read it, it looks right"})
    assert approved.status_code == 200 and approved.json()["batch"]["state"] == "approved" and len(approved.json()["batch"]["commands"]) == 2
    assert admin.post(f"/api/admin/library/batches/{batch['id']}/discard", json={"reason": "Not needed after all"}).json()["discarded"] is True
    assert admin.get("/api/admin/library/batches").json()["batches"] == []
    assert audit(served) == [("library acts stage", "started"), ("library acts stage", "done"), ("library batch approve", "started"),
                             ("library batch approve", "done"), ("library batch discard", "started"), ("library batch discard", "done")]


def test_a_view_only_admin_an_unconfirmed_admin_and_an_advocate_cannot_stage_approve_or_discard(served):
    for client, status in ((served.login(VIEWER, confirmed=True), 403), (served.login(ADMIN), 403), (served.login(ADVOCATE), 404)):
        assert stage(client).status_code == status
        assert client.post("/api/admin/library/batches/0123456789ab/approve", json={"reason": "x"}).status_code == status
        assert client.post("/api/admin/library/batches/0123456789ab/discard", json={"reason": "x"}).status_code == status
    assert audit(served) == []
    assert served.login(VIEWER).get("/api/admin/library/batches").status_code == 200
    assert served.login(ADVOCATE).get("/api/admin/library/batches").status_code == 404


def test_a_refused_file_leaves_no_batch_and_the_log_says_it_was_not_made(served):
    admin = served.login(ADMIN, confirmed=True)
    reply = admin.post("/api/admin/library/acts/stage", json={"jurisdiction": "Union of India", "reason": "x", "files": [{"name": "../x.txt", "text": ACT}]})
    assert reply.status_code == 422 and "named <year>_<number>_<title>.txt" in reply.json()["detail"]
    assert audit(served) == [("library acts stage", "started"), ("library acts stage", "not made")]
    assert admin.get("/api/admin/library/batches").json()["batches"] == []


def test_nothing_staged_reaches_the_library_or_carries_a_word_the_payload_guard_refuses(served):
    admin = served.login(ADMIN, confirmed=True)
    stage(admin)
    assert not (served.tmp_path / "no-law").exists()
    assert all("files" not in b for b in admin.get("/api/admin/library/batches").json()["batches"])  # the key "files" is never sent
