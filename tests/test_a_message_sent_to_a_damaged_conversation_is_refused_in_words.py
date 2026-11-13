"""A message sent to a damaged conversation is refused in words, not with a server error (plan AN.53, 53j4; D225).

Every place that reads a saved matter and can fail says so by catching the disk's error and a record that does not read as one.
The store's error for a matter file that will not open (53j1) was neither, so wherever a caller had not been told of it - the
turn's own path among them - the advocate's damaged conversation was a server error. A matter file that will not open now raises
an error that is the store's own AND one every such place already catches, so no caller has to be told. A key that cannot be
reached is a different failure and is left as it is. Offline: the served app with stand-in models; no browser.
"""
from __future__ import annotations

import pytest

from nm.shared.storage_errors_port import StoredObjectUnreadable
from nm.shared.store_envelope import KeyUnavailable
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file.matter_contracts import Matter
from tests.test_core_served import OWNER, served, successful  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a
DAMAGE = {
    "overwritten": lambda blob: b"not a saved matter, and longer than the file was",
    "emptied": lambda blob: b"",
    "cut short": lambda blob: blob[: len(blob) // 2],
}


@pytest.mark.parametrize("how", sorted(DAMAGE))
def test_a_new_message_to_the_advocates_own_damaged_conversation_is_refused_in_words(served, how):
    successful(served)
    (matter,) = served.store.list_for(OWNER).matters
    chat = served.client.get("/api/work").json()["chats"][0]["chat_id"]
    path = served.store._matters / f"{matter.id}.nm"
    damaged = DAMAGE[how](path.read_bytes())
    path.write_bytes(damaged)
    answer = served.client.post("/api/turn", json={"message": "A further question.", "turn_id": "turn-next", "chat_id": chat})
    assert 400 <= answer.status_code < 500 or answer.status_code == 503, answer.text
    assert "could not be loaded reliably" in answer.text
    assert path.read_bytes() == damaged, "and nothing is written over the file that could not be read"


@pytest.mark.parametrize("how", sorted(DAMAGE))
def test_the_error_is_the_stores_own_and_one_a_failed_reading_is_already_caught_as(tmp_path, how):
    store = FileMatterStore(tmp_path, key="unreadable-control-" + "k" * 24)
    store.commit(Matter(id="m_one", advocate_id="a@example.test", title="Control", version=1), expected_version=0)
    path = store._matters / "m_one.nm"
    path.write_bytes(DAMAGE[how](path.read_bytes()))
    with pytest.raises(StoredObjectUnreadable) as said:
        store.load("m_one")
    assert isinstance(said.value, ValueError) and said.value.__cause__ is not None


def test_a_key_that_cannot_be_reached_is_not_said_to_be_a_damaged_file(tmp_path, monkeypatch):
    store = FileMatterStore(tmp_path, key="unreadable-control-" + "k" * 24)
    store.commit(Matter(id="m_one", advocate_id="a@example.test", title="Control", version=1), expected_version=0)

    def no_key(matter_id, blob):
        raise KeyUnavailable("The matter key is unavailable.")
    monkeypatch.setattr(store, "_open", no_key)
    with pytest.raises(KeyUnavailable) as said:
        store.load("m_one")
    assert not isinstance(said.value, ValueError), "an installation's failure stays loud; it is not one file's damage"
