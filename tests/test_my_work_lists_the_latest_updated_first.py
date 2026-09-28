"""F-B-14. My work lists the latest updated matter first.

Owner, 28 September 2026: *"my work, sort the matters based on the last updated
date, with latest updated at the top."*

THE RULE: a file's last update is stamped by the SAVE DOOR -- every store's
`commit` -- and My work is ordered by it, newest first, whatever the deadlines.
A writer never stamps it, so no way of changing a file can be left out.
"""
from __future__ import annotations

import ast
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from nm.work_the_file.matter_contracts import Matter
from nm.work_the_file.projections_api import latest_first, matter_list_projection

pytestmark = pytest.mark.class_a

NM = Path(__file__).resolve().parents[1] / "nm"
TODAY = date(2026, 9, 4)


def _store_classes() -> list[tuple[Path, ast.ClassDef]]:
    """EVERY class in the product that saves a matter: a method `commit` whose
    first argument after `self` is the matter. Drawn from the whole of `nm/`,
    so a store added next month is in the population without anyone listing it.
    """
    found = []
    for path in NM.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if (isinstance(item, ast.FunctionDef) and item.name == "commit"
                        and len(item.args.args) >= 2 and item.args.args[1].arg == "matter"
                        and not any(isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                    and s.value.value is Ellipsis for s in item.body)):
                    found.append((path, node))
    return found


def test_every_store_stamps_the_time_of_each_save():
    stores = _store_classes()
    assert len(stores) >= 2, f"the store population is too small to mean anything: {stores}"
    unstamped = [f"{path.relative_to(NM.parent)}::{cls.name}" for path, cls in stores
                 if "save_stamp" not in ast.unparse(cls)]
    assert not unstamped, (
        f"{unstamped} save a matter without stamping `updated_at` through `save_stamp` "
        "-- My work would not see those saves (F-B-14)")


def test_a_save_stamps_the_file_and_a_later_save_stamps_it_later(tmp_path, monkeypatch):
    from nm.shared import store_file_store
    from nm.shared.operation_contracts import save_stamp
    from tests.test_turn_contract import KEY

    stamps = iter(["2026-09-28T09:00:00.000001+00:00", "2026-09-28T09:00:00.000002+00:00"])
    monkeypatch.setattr(store_file_store, "save_stamp", lambda: next(stamps))
    store = store_file_store.FileMatterStore(tmp_path, key=KEY)
    matter = Matter.create(advocate_id="adv", title="A stamped file")
    assert matter.updated_at == ""
    first = store.commit(matter, expected_version=matter.version)
    assert first.updated_at == "2026-09-28T09:00:00.000001+00:00", (
        "the save door did not stamp the file")
    assert store.load(matter.id).updated_at == first.updated_at, "the stamp was not saved"
    second = store.commit(replace(first, version=first.version + 1),
                          expected_version=first.version)
    assert second.updated_at == "2026-09-28T09:00:00.000002+00:00", (
        "a later save kept the earlier time, so the list cannot tell them apart")
    # ONE FIXED WIDTH, so stamps compare as text in time order.
    assert len(save_stamp()) == len("2026-09-28T09:00:00.000001+00:00")


def test_the_latest_updated_matter_leads_whatever_else_it_holds():
    def matter(title: str, *, saved: str = "", worked: str = "") -> Matter:
        return replace(Matter.create(advocate_id="adv", title=title),
                       updated_at=saved, last_activity=worked)

    older = matter("saved earlier", saved="2026-09-28T09:00:00.000001+00:00", worked="2026-09-28")
    newer = matter("saved later", saved="2026-09-28T09:00:00.000002+00:00", worked="2026-09-28")
    legacy = matter("worked the same day, never stamped", worked="2026-09-28")
    yesterday = matter("worked yesterday", worked="2026-09-27")
    never = matter("never worked")

    ordered = [m.title for m in latest_first([never, legacy, older, yesterday, newer])]
    assert ordered == ["saved later", "saved earlier", "worked the same day, never stamped",
                       "worked yesterday", "never worked"]

    rows = matter_list_projection([older, newer])["matters"]
    assert [r["matter"] for r in rows] == ["saved later", "saved earlier"]
    assert rows[0]["last_updated"] == newer.updated_at, (
        "the row does not show the time its place in the list comes from")
    assert matter_list_projection([legacy])["matters"][0]["last_updated"] is None


def _turn(client, message: str, matter_id: str | None = None) -> dict:
    payload = {"message": message, "today": TODAY.isoformat()}
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
    assert listed[0]["last_updated"] > listed[1]["last_updated"]
