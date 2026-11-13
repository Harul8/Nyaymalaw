"""A matter address that names nothing is 'not found', never a server error (plan AN.53, 53j2; D225; the review's F-41).

The earlier matter address handed whatever was written in it to the store, which refuses a name that is no storage name by
raising; the advocate was answered with a server error. And the advocate's own matter that could not be opened was a server
error too (the limit 53b2 left). The address now answers 'not found' for a name no saved file of the advocate's bears - a
malformed one among them - and says of the advocate's own damaged matter that it could not be read, as a conversation's address
does. Offline: the served app with stand-in models; no browser.
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
    answer = served.client.get(address.format(name))
    assert answer.status_code == 404 and answer.json()["detail"] == "Matter not available."


@pytest.mark.parametrize("address", ADDRESSES)
def test_the_neighbours_answer_as_before(own, address):
    served, matter_id = own
    assert served.client.get(address.format("m_never_saved")).status_code == 404, "a well-formed name of nothing"
    assert served.client.get(address.format(matter_id)).status_code == 409, "the advocate's own matter, whole"
    assert served.login(OTHER).get(address.format(matter_id)).status_code == 404, "another's matter"


@pytest.mark.parametrize("address", ADDRESSES)
def test_the_advocates_own_damaged_matter_is_said_to_be_unreadable_and_to_no_other(own, address):
    served, matter_id = own
    (served.store._matters / f"{matter_id}.nm").write_bytes(b"not a saved matter, and longer than the file was")
    answer = served.client.get(address.format(matter_id))
    assert answer.status_code == 503 and answer.json()["detail"] == "This matter could not be read reliably."
    assert served.login(OTHER).get(address.format(matter_id)).status_code == 404


@pytest.mark.parametrize("address", ADDRESSES)
def test_a_damaged_file_nobody_is_recorded_as_owning_is_not_found_by_anyone(own, address):
    served, _matter_id = own
    (served.store._matters / "m_of_nobody.nm").write_bytes(b"not a saved matter")
    for client in (served.client, served.login(OTHER)):
        assert client.get(address.format("m_of_nobody")).status_code == 404
