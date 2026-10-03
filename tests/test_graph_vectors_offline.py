"""Optional developer embeddings respect explicit offline mode before spending."""
import subprocess

import pytest

from development_environment.developer_tooling import graph_vectors

pytestmark = pytest.mark.class_a


def test_offline_mode_never_reads_credentials_or_dispatches(monkeypatch, capsys):
    monkeypatch.setenv("CRG_OFFLINE", "1")
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("Explicit offline mode must stop before credentials or embedding dispatch")

    monkeypatch.setattr(graph_vectors, "_credentials", forbidden)
    monkeypatch.setattr(graph_vectors.subprocess, "run", forbidden)

    assert graph_vectors.embed() == 1
    assert calls == []
    notice = capsys.readouterr().err
    assert "CRG_OFFLINE=1" in notice and "offline" in notice and "not refreshed" in notice


@pytest.mark.parametrize("offline", [None, "0"])
def test_without_offline_flag_keeps_the_existing_dispatch(monkeypatch, offline):
    if offline is None:
        monkeypatch.delenv("CRG_OFFLINE", raising=False)
    else:
        monkeypatch.setenv("CRG_OFFLINE", offline)
    credentials = {"CRG_OPENAI_API_KEY": "synthetic-not-a-real-key",
                   "CRG_OPENAI_MODEL": "synthetic-embedding-model"}
    calls = []
    monkeypatch.setattr(graph_vectors, "_credentials", lambda: credentials)

    def dispatched(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="refreshed", stderr="")

    monkeypatch.setattr(graph_vectors.subprocess, "run", dispatched)

    assert graph_vectors.embed() == 0
    assert len(calls) == 1
    command, options = calls[0]
    assert command == ["code-review-graph", "embed", "--provider", "openai", "--model",
                       "synthetic-embedding-model", "--repo", str(graph_vectors.REPO)]
    assert options["env"] is credentials
    assert options["capture_output"] is True and options["text"] is True
