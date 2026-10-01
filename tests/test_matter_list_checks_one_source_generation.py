"""A list checks every file and one shared source generation before serving."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.orchestrate.generations_port import GenerationUnavailable
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a


def _seed(wired, count):
    for index in range(count):
        matter = replace(Matter.create("adv_demo", f"Saved file {index}"), version=1)
        wired.store.commit(matter, expected_version=0)


def test_matter_list_checks_its_shared_source_generation_once_at_the_serving_boundary(
    client, wired, monkeypatch,
):
    """Adding a file must not add another whole-knowledge rehash to list latency."""
    _seed(wired, 8)
    guard = wired.source_generation_guard()
    actual = guard.require_current
    checked = Mock(wraps=actual)
    monkeypatch.setattr(guard, "require_current", checked)
    monkeypatch.setattr(wired, "source_generation_guard", lambda: guard)

    response = client.get("/api/matters")

    assert response.status_code == 200, response.text
    assert response.json()["row_count"] == 8
    assert checked.call_count == 1


def test_matter_list_refuses_a_generation_change_before_release(client, wired, monkeypatch):
    """The one late check still rejects source movement while the list builds."""
    _seed(wired, 2)
    guard = wired.source_generation_guard()
    monkeypatch.setattr(guard, "require_current", Mock(side_effect=GenerationUnavailable(
        "The source population changed")))
    monkeypatch.setattr(wired, "source_generation_guard", lambda: guard)

    response = client.get("/api/matters")

    assert response.status_code == 409
    assert "legal sources changed" in response.text.lower()
