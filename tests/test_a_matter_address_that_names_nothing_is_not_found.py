"""No address of the server opens a matter saved before conversations (plan AN.48, D307; the owner, 18 Nov 2026).

The earlier matter's address answered 'not found' for a name no saved file of the advocate's bears, 'could not be read' for the
advocate's own damaged matter, and 409 for their own whole one (plan AN.53, 53j2; D225). Only the screens deleted under D292
(AN.57) called it, so it is removed: whatever is written in it, by whoever, is 'not found' - never a server error, never a word
about whether such a matter is there - and the matter's file stays as it was. Offline: the served app with stand-in models; no
browser.
"""
from __future__ import annotations

import pytest

from tests.test_core_served import OTHER, OWNER, served, successful  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a
ADDRESSES = ("/api/matters/{}", "/api/matters/{}/transcript")
NO_STORAGE_NAME = ("a.b", "has space", "x" * 300, "-starts-with-a-dash", "semi;colon")


@pytest.fixture
def own(served):
    """(served, the identifier of the owner's one saved matter)."""
    successful(served)
    (matter,) = served.store.list_for(OWNER).matters
    return served, matter.id


@pytest.mark.parametrize("address", ADDRESSES)
@pytest.mark.parametrize("name", NO_STORAGE_NAME)
def test_a_name_that_is_no_storage_name_is_not_found(own, address, name):
    served, _matter_id = own
    assert served.client.get(address.format(name)).status_code == 404


@pytest.mark.parametrize("address", ADDRESSES)
def test_the_advocates_own_matter_and_anothers_are_not_found_alike_and_kept(own, address):
    served, matter_id = own
    before = served.store.load(matter_id)
    answers = [served.client.get(address.format(matter_id)), served.login(OTHER).get(address.format(matter_id)),
               served.client.get(address.format("m_never_saved"))]
    assert [answer.status_code for answer in answers] == [404, 404, 404]
    assert len({answer.text for answer in answers}) == 1, "the answer says nothing of whether such a matter is there"
    assert served.store.load(matter_id) == before


@pytest.mark.parametrize("address", ADDRESSES)
def test_a_damaged_file_is_not_found_by_anyone(own, address):
    served, matter_id = own
    (served.store._matters / f"{matter_id}.nm").write_bytes(b"not a saved matter, and longer than the file was")
    (served.store._matters / "m_of_nobody.nm").write_bytes(b"not a saved matter")
    for client in (served.client, served.login(OTHER)):
        for name in (matter_id, "m_of_nobody"):
            assert client.get(address.format(name)).status_code == 404
