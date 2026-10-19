"""P14 instruction capture cannot invent an answer or its provenance."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


pytestmark = pytest.mark.class_a
NOW = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)


def _request(**extra):
    return {
        "message": "We act for the plaintiff in an unpaid invoice dispute.",
        "parties": {"Scope Client": "client", "Scope Opponent": "adverse"},
        "capacity": {"state": "not_in_doubt", "basis": "The advocate assessed capacity."},
        **extra,
    }


@pytest.mark.parametrize("value", ["", " \t\n", None, 7, True, ["advice"], {"answer": "advice"}])
def test_supplied_nontext_or_blank_instruction_cannot_create_a_matter(client, value):
    from nm.app.api import application

    response = client.post("/api/turn", json=_request(release={"scope": value}))
    assert response.status_code == 422
    listing = application().store.list_for("adv_demo")
    assert listing.complete
    assert listing.unreadable == ()
    assert listing.matters == ()


