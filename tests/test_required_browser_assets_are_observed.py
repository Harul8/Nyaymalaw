"""Negative controls for browser coverage, not successful advocate journeys."""
from __future__ import annotations

import hashlib

import pytest

from tests.test_the_workspace_respects_its_current_context import journey as _base_journey
from tests.test_the_workspace_respects_its_current_context import page as _base_page

pytestmark = pytest.mark.journey
journey = _base_journey
page = _base_page


@pytest.mark.parametrize("delivery", ["unavailable", "empty", "aborted"])
def test_navigation_refuses_an_undelivered_required_script(page, journey, delivery):
    target = "/static/matter-workspace.js"
    document = page.request.get(journey["base"] + "/")
    assert document.status == 200
    assert f'<script src="{target}"></script>' in document.text()
    intercepted = []
    body = b"/* planted unavailable controller */" if delivery == "unavailable" else b""

    def mutate(route):
        intercepted.append(route.request.url)
        if delivery == "aborted":
            route.abort("failed")
        else:
            route.fulfill(status=503 if delivery == "unavailable" else 200,
                          content_type="application/javascript", body=body)

    page.route("**" + target, mutate)
    with pytest.raises(AssertionError, match="Required local asset delivery failed") as refused:
        page.goto(journey["base"] + "/")
    assert len(intercepted) == 1, "a control that changed no real request proves nothing"
    assert target in str(refused.value)
    navigation = page.asset_navigations[-1]
    assert {"path": target, "kind": "script"} in navigation["required"]
    assert any(target in problem for problem in navigation["problems"])
    observed = [row for row in page.static_assets if row["path"] == target]
    if delivery == "aborted":
        assert observed == []
        assert any(row["path"] == target and row["failure"] for row in page.failed_requests)
    else:
        assert len(observed) == 1
        assert observed[0]["status"] == (503 if delivery == "unavailable" else 200)
        assert observed[0]["body_length"] == len(body)
        assert observed[0]["sha256"] == hashlib.sha256(body).hexdigest()
