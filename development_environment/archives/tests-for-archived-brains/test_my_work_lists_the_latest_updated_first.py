"""F-B-14. My work lists the latest updated matter first.

Owner, 28 September 2026: *"my work, sort the matters based on the last updated
date, with latest updated at the top."*

THE RULE: when each file was last saved is the STORE's own record -- every save
goes through it -- and My work is ordered by it, newest first, whatever the
deadlines. It is kept OUT of the sealed matter: a stamp inside the file would
change the file's identity on every save, and the checks that ask "has the file
changed since I read it?" would see a change after every journal write.
"""
from __future__ import annotations

from dataclasses import fields, replace

import pytest

from nm.shared.store_port import MatterList
from nm.work_the_file.matter_contracts import Matter
from nm.work_the_file.projections_api import latest_first, matter_list_projection

pytestmark = pytest.mark.class_a


def test_the_save_time_is_the_stores_record_and_never_a_field_of_the_file():
    names = {f.name for f in fields(Matter)}
    assert not names & {"updated_at", "saved_at", "last_saved"}, (
        "a save time inside the matter changes its identity on every save")


def test_the_file_store_dates_every_matter_by_its_last_save(tmp_path):
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_turn_contract import KEY

    store = FileMatterStore(tmp_path, key=KEY)
    first = store.commit(Matter.create(advocate_id="adv", title="First"), expected_version=0)
    second = store.commit(Matter.create(advocate_id="adv", title="Second"), expected_version=0)
    held = store.list_for("adv")
    assert held.saved(first.id) and held.saved(second.id), "a saved matter was not dated"
    before = held.saved(first.id)
    import os
    import time

    later = time.time() + 5
    os.utime(tmp_path / "matters" / f"{first.id}.nm", (later, later))
    assert store.list_for("adv").saved(first.id) > before
    # The file is unchanged by being dated: what is stored is what was saved.
    assert store.load(first.id) == first


def test_the_latest_updated_matter_leads_whatever_else_it_holds():
    def matter(title: str, *, worked: str = "") -> Matter:
        return replace(Matter.create(advocate_id="adv", title=title), last_activity=worked)

    older = matter("saved earlier", worked="2026-09-28")
    newer = matter("saved later", worked="2026-09-28")
    undated = matter("worked the same day, not dated by the store", worked="2026-09-28")
    yesterday = matter("worked yesterday", worked="2026-09-27")
    never = matter("never worked")
    held = MatterList((never, undated, older, yesterday, newer), saved_at=(
        (str(older.id), "2026-09-28T09:00:00.000001+00:00"),
        (str(newer.id), "2026-09-28T09:00:00.000002+00:00")))

    assert [m.title for m in latest_first(held)] == [
        "saved later", "saved earlier", "worked the same day, not dated by the store",
        "worked yesterday", "never worked"]

    rows = matter_list_projection(MatterList((older, newer), saved_at=held.saved_at))["matters"]
    assert [r["matter"] for r in rows] == ["saved later", "saved earlier"]
    assert rows[0]["last_updated"] == held.saved(newer.id), (
        "the row does not show the time its place in the list comes from")
    assert matter_list_projection(MatterList((undated,)))["matters"][0]["last_updated"] is None


def _turn(client, message: str, matter_id: str | None = None) -> dict:
    payload = {"message": message, "today": "2026-09-04"}
    if matter_id:
        payload["matter_id"] = matter_id
    r = client.post("/api/turn", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_served_list_moves_a_matter_to_the_top_when_it_is_worked(client):
    first = _turn(client, "We act for the plaintiff. Goods were supplied and never paid for.")
    second = _turn(client, "We act for the tenant. The landlord has cut the water supply.")
    listed = client.get("/api/matters").json()["matters"]
    assert [r["matter_id"] for r in listed][:2] == [second["matter_id"], first["matter_id"]]

    _turn(client, "The invoices were dated 14 March 2023.", first["matter_id"])
    listed = client.get("/api/matters").json()["matters"]
    assert listed[0]["matter_id"] == first["matter_id"], (
        "working an older matter did not bring it to the top of My work")
    assert listed[0]["last_updated"] >= listed[1]["last_updated"]
