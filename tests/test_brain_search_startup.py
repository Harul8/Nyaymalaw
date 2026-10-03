"""Startup warms only the served search and preserves independent collections."""
import threading
from types import SimpleNamespace

import uvicorn

from nm.app import main
from nm.brain.retrieval import HybridSearcher, SearchUnavailable


def test_startup_warms_the_served_search_without_loading_other_adapters(monkeypatch):
    calls = []
    active = SimpleNamespace(warm=lambda: calls.append("active"))
    other = SimpleNamespace(warm=lambda: calls.append("other"))
    application = SimpleNamespace(
        legal_search=active, sections=other, judgments=other,
        health=lambda: {"corpus": "readable"})
    monkeypatch.setattr(main, "Application", lambda: application)
    monkeypatch.setattr(main, "create_app", lambda app: calls.append("wired"))
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append("served"))

    def immediate_thread(*, target, **kwargs):
        return SimpleNamespace(start=target)

    monkeypatch.setattr(threading, "Thread", immediate_thread)

    assert main.main(["--port", "8072"]) == 0
    assert calls == ["wired", "active", "served"]
    calls.clear()
    assert main.main(["--check"]) == 0
    assert calls == []


def test_failed_collection_warm_does_not_hide_its_peer():
    calls = []

    def unavailable():
        calls.append("first")
        raise SearchUnavailable("local model absent")

    search = HybridSearcher({
        "provision": SimpleNamespace(warm=unavailable),
        "judgment": SimpleNamespace(warm=lambda: calls.append("second"))})

    search.warm()

    assert calls == ["first", "second"]
