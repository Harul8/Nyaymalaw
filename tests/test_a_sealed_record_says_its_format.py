"""A sealed record's format number is checked when it is opened (plan AN.50, piece 50g; D193; the review's F-34).

Every sealed record has said which format it is since there were any, and nothing read the number: a record of a format this
code does not know was opened as if it were the one it does. It is now refused by name - for a matter, a paper's original bytes
and a paper's derivatives alike, since all three open through the one sealer - and a matter so refused is listed among those that
could not be read rather than opened wrongly. Offline: a temporary store and invented records.
"""
from __future__ import annotations

import json

import pytest

from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_sealing import SEALED_FORMAT, MatterSealer, SealedFormatUnknown
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a
KEY = "sealed-format-control-" + "k" * 24


def test_a_record_sealed_now_says_the_format_this_code_reads_and_opens(tmp_path):
    sealer = MatterSealer(KEY, tmp_path / "keys")
    blob = sealer.seal("matter-1", b"what was sealed")
    assert json.loads(blob)["envelope"] == SEALED_FORMAT == 1
    assert sealer.open("matter-1", blob) == b"what was sealed"


@pytest.mark.parametrize("said", [2, 0, -1, "1", 1.0, True, None, [1]])
def test_a_record_of_a_format_this_code_does_not_know_is_refused_by_name(tmp_path, said):
    sealer = MatterSealer(KEY, tmp_path / "keys")
    record = json.loads(sealer.seal("matter-1", b"what was sealed"))
    record["envelope"] = said
    with pytest.raises(SealedFormatUnknown, match="format"):
        sealer.open("matter-1", json.dumps(record).encode("utf8"))


def test_a_record_that_says_no_format_is_refused(tmp_path):
    sealer = MatterSealer(KEY, tmp_path / "keys")
    record = json.loads(sealer.seal("matter-1", b"what was sealed"))
    del record["envelope"]
    with pytest.raises(SealedFormatUnknown):
        sealer.open("matter-1", json.dumps(record).encode("utf8"))


def test_a_matter_file_of_an_unknown_format_is_not_opened_and_is_listed_as_unreadable(tmp_path):
    store = FileMatterStore(tmp_path / "store", key=KEY)
    store.commit(Matter(id="matter-1", advocate_id="adv", title="First", version=1), expected_version=0)
    path = tmp_path / "store" / "matters" / "matter-1.nm"
    record = json.loads(path.read_bytes())
    record["envelope"] = 2  # as code newer than this one might write it
    path.write_text(json.dumps(record, indent=2), encoding="utf8")
    with pytest.raises(SealedFormatUnknown):
        store.load("matter-1")
    listed = store.list_for("adv")
    assert listed.matters == () and listed.unreadable == ("matter-1",)
