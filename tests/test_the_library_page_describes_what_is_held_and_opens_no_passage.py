"""The Library page (plan AN.46, piece 46l; owner decisions D119, D122 and D125, 7 Nov 2026): what the held law holds, described from the
stores' own records - passages and vectors, the model, when recorded, how they were checked, the Acts catalogue's counts, the earlier
copies kept beside a store, and stores built beside the live ones. It opens no passage and changes nothing; a source that cannot be read
says so for itself and leaves the other standing. Synthetic stores in a temporary folder."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.admin_api import admin_router
from nm.app.admin_views import content_free, library_view
from nm.app.composition import Application
from nm.arrive.admin_checks import AdminChecks
from nm.arrive.admin_library import SHOWN, AdminLibrary
from nm.arrive.admin_port import AdminLibraryPort
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, csrf_token, enrol, utcnow
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
from datetime import datetime, timezone  # noqa: E402

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def places(tmp_path):
    (tmp_path / "matters").mkdir()
    (tmp_path / "law").mkdir()
    (tmp_path / "root" / ".nm" / "retrieval").mkdir(parents=True)
    return tmp_path


def library_in(places):
    checks = AdminChecks(storage=places / "matters", root=places / "root", settings={}, corpus_dir=places / "law")
    return AdminLibrary(checks=checks, root=places / "root", corpus_dir=places / "law")


def store(places, kind, lineage_file, index_path, db_path, *, passages=10, size=100, acts=None):
    law = places / "law"
    (law / index_path).parent.mkdir(parents=True, exist_ok=True)
    (law / index_path).write_bytes(b"v" * size)
    (law / db_path).write_bytes(b"d" * 7)
    (law / f"{kind}_bm25").mkdir(exist_ok=True)
    (places / "root" / ".nm" / "retrieval" / lineage_file).write_text(json.dumps({
        "passages": passages, "model": "synthetic-model", "recorded_at": "2026-10-01T00:00:00+00:00",
        "vector_index": {"path": index_path, "vectors": passages, "bytes": size}, "passage_store": {"path": db_path, "count": passages},
        "bm25": {"path": f"{kind}_bm25"}, "verified": {"sampled": 4, "same_vector": 4}}), encoding="utf8")
    if acts is not None:
        (law / db_path).parent.joinpath("acts.json").write_text(json.dumps(acts), encoding="utf8")


def acts(*rows):
    return [{"act_id": f"a{i}", "jurisdiction": j, "standing": s} for i, (j, s) in enumerate(rows)]


def test_it_is_the_library_port(places):
    assert isinstance(library_in(places), AdminLibrary) and hasattr(AdminLibraryPort, "library")


def test_each_store_is_described_from_its_record_with_sizes_and_the_acts_catalogue_counted_by_jurisdiction_and_standing(places):
    store(places, "acts", "bare_acts.lineage.json", "acts_v5/acts_v5.index", "acts_v5/acts_v5.db", passages=12, size=100,
          acts=acts(("Union of India", "in force"), ("Union of India", "in force"), ("Union of India", "repealed"), ("Telangana", "in force")))
    store(places, "cases", "judgments.lineage.json", "cases.index", "cases.db", passages=30, size=50)
    found = library_in(places).library()
    acts_store, judgments = found["stores"]
    assert (acts_store["collection"], acts_store["passages"], acts_store["index_bytes"], acts_store["passage_store_bytes"]) == ("acts", 12, 100, 7)
    assert acts_store["catalogue"] == {"acts": 4, "by_jurisdiction": [{"name": "Union of India", "acts": 3}, {"name": "Telangana", "acts": 1}],
                                       "by_standing": [{"name": "in force", "acts": 3}, {"name": "repealed", "acts": 1}]}
    assert judgments["collection"] == "judgments" and judgments["passages"] == 30 and "catalogue" not in judgments
    assert acts_store["sampled"] == acts_store["same_vector"] == 4 and acts_store["model"] == "synthetic-model"


def test_a_long_list_of_jurisdictions_shows_the_most_and_counts_the_rest_as_others(places):
    rows = [(f"State {n:03d}", "in force") for n in range(SHOWN + 5)]
    store(places, "acts", "bare_acts.lineage.json", "acts.index", "acts.db", acts=acts(*rows, ("State 000", "in force")))
    by_jurisdiction = library_in(places).library()["stores"][0]["catalogue"]["by_jurisdiction"]
    assert len(by_jurisdiction) == SHOWN + 1 and by_jurisdiction[0] == {"name": "State 000", "acts": 2}
    assert by_jurisdiction[-1] == {"name": "others", "acts": 5}


def test_the_catalogue_is_read_again_only_when_its_file_changes(places):
    store(places, "acts", "bare_acts.lineage.json", "acts.index", "acts.db", acts=acts(("Union of India", "in force")))
    library = library_in(places)
    assert library.library()["stores"][0]["catalogue"]["acts"] == 1
    catalogue = places / "law" / "acts.json"
    catalogue.write_text(json.dumps(acts(("Union of India", "in force"), ("Goa", "in force"))), encoding="utf8")
    assert library.library()["stores"][0]["catalogue"]["acts"] == 2


def test_an_unreadable_catalogue_is_none_and_an_unreadable_record_leaves_the_other_store_standing(places):
    store(places, "acts", "bare_acts.lineage.json", "acts.index", "acts.db")
    (places / "law" / "acts.json").write_text("{not json", encoding="utf8")
    (places / "root" / ".nm" / "retrieval" / "judgments.lineage.json").write_text("{broken", encoding="utf8")
    acts_store, judgments = library_in(places).library()["stores"]
    assert acts_store["readable"] is True and acts_store["catalogue"] is None
    assert judgments["readable"] is False and "passages" not in judgments


def test_earlier_copies_are_named_with_their_sizes_and_nothing_else_is_taken_for_one(places):
    store(places, "acts", "bare_acts.lineage.json", "acts_v5/acts_v5.index", "acts_v5/acts_v5.db")
    law = places / "law"
    (law / "acts_v5" / "acts_v5.index.before-20261105T1941").write_bytes(b"o" * 30)
    folder = law / "acts_v5" / "acts_v5_bm25s.before-20261105T1941"
    folder.mkdir()
    (folder / "data.npy").write_bytes(b"x" * 11)
    (places / "root" / ".nm" / "retrieval" / "bare_acts.lineage.json.before-20261105T1941").write_text("{}", encoding="utf8")
    (law / "acts_v5" / "notes.txt").write_text("not a copy", encoding="utf8")
    copies = {c["name"]: (c["bytes"], c["folder"]) for c in library_in(places).library()["earlier_copies"]}
    assert copies == {"acts_v5/acts_v5.index.before-20261105T1941": (30, False), "acts_v5/acts_v5_bm25s.before-20261105T1941": (11, True),
                      "bare_acts.lineage.json.before-20261105T1941": (2, False)}


def test_a_store_built_beside_is_listed_with_counts_and_whether_it_has_an_index_and_nothing_of_its_words(places):
    folder = places / "law" / "judgments_v3"
    folder.mkdir()
    (folder / "passages.jsonl").write_text('{"text": "A SECRET WORD OF A JUDGMENT"}\n', encoding="utf8")
    (folder / "summary.json").write_text(json.dumps({"judgments": 5, "passages": 40, "problems": 2, "built_at": "2026-11-07T11:56:27+00:00",
                                                     "kinds": {"facts": 3}, "not in the earlier store": 1, "aliases": "checked"}), encoding="utf8")
    (places / "law" / "other").mkdir()
    (places / "law" / "other" / "summary.json").write_text("{}", encoding="utf8")
    (candidate,) = library_in(places).library()["candidates"]
    assert candidate == {"name": "judgments_v3", "readable": True, "built_at": "2026-11-07T11:56:27+00:00", "passages_file_bytes": (folder / "passages.jsonl").stat().st_size,
                         "has_index": False, "judgments": 5, "passages": 40, "problems": 2, "not_in_the_earlier_store": 1}
    assert "SECRET" not in json.dumps(library_in(places).library())


def test_the_store_now_searched_is_not_listed_as_waiting_though_it_keeps_its_read_stages_files(places):
    """After the swap of 8 Nov 2026 the judgment store searched is the folder that was built beside: it keeps its summary and passages
    file. It must not be listed as waiting; a store built after it still is."""
    store(places, "judgments", "judgments.lineage.json", "judgments_v4/judgments_v4.index", "judgments_v4/judgments_v4.db")
    for name in ("judgments_v4", "judgments_v5"):
        folder = places / "law" / name
        folder.mkdir(exist_ok=True)
        (folder / "passages.jsonl").write_text("{}\n", encoding="utf8")
        (folder / "summary.json").write_text(json.dumps({"judgments": 5, "passages": 40}), encoding="utf8")
    assert [c["name"] for c in library_in(places).library()["candidates"]] == ["judgments_v5"]


def test_reading_changes_nothing(places):
    store(places, "acts", "bare_acts.lineage.json", "acts.index", "acts.db", acts=acts(("Union of India", "in force")))
    before = sorted((p.relative_to(places).as_posix(), p.stat().st_mtime_ns, p.stat().st_size) for p in places.rglob("*") if p.is_file())
    library_in(places).library()
    assert before == sorted((p.relative_to(places).as_posix(), p.stat().st_mtime_ns, p.stat().st_size) for p in places.rglob("*") if p.is_file())


def test_the_view_is_content_free_and_says_when_it_was_read(places):
    store(places, "acts", "bare_acts.lineage.json", "acts.index", "acts.db", acts=acts(("Union of India", "in force")))
    page = library_view(library_in(places), NOW)
    assert page["as_of"] == NOW.isoformat() and content_free(page) and set(page) == {"as_of", "stores", "earlier_copies", "candidates", "disk"}


# ------------------------------------------------------------------------- the route ---

BOSS, VIEWER, ADVOCATE = "boss@example.test", "viewer@example.test", "advocate@example.test"


def test_both_admin_levels_are_given_the_page_and_an_advocate_the_404_of_an_address_that_is_not_there(places, monkeypatch):
    storage = places / "served"
    storage.mkdir()
    directory = FileDirectory(storage, key=KEY)
    for who in (BOSS, VIEWER, ADVOCATE):
        directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=Path(__file__).resolve().parents[1], model=model, store=FileMatterStore(storage, key=KEY), directory=directory,
                      mail=FileOutbox(storage, key=KEY), legal_search=searcher(), audit_root=storage / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(storage), "NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1",
                          "NM_EMBED_MODEL": "text-embedding-3-large", "NM_BARE_ACTS_DIR": str(storage / "no-held-acts"),
                          "NM_CORPUS_DIR": str(places / "law"), "NM_ADMINS": f"{BOSS}:admin,{VIEWER}:view-only"})
    monkeypatch.setattr(api, "_application", app)
    web = FastAPI()
    web.include_router(admin_router(application=api.application, signed_in=api.signed_in, csrf=api.CsrfProtected,
                                    admit_attempt=api._admit_auth_attempt))

    def client(who):
        made = TestClient(web)
        token = app.directory.open_session(who, api._device("device-1", "testclient"), utcnow())
        made.cookies.update({"nm_session": token, "nm_device": "device-1", "nm_csrf": csrf_token(token)})
        made.headers.update({"origin": "http://testserver", "x-nm-csrf": csrf_token(token)})
        return made

    for who in (BOSS, VIEWER):
        reply = client(who).get("/api/admin/library")
        assert reply.status_code == 200 and {s["collection"] for s in reply.json()["stores"]} == {"acts", "judgments"}
    advocate = client(ADVOCATE)
    assert advocate.get("/api/admin/library").status_code == 404
    assert advocate.get("/api/admin/library").json() == advocate.get("/api/admin/nothing-here").json()
