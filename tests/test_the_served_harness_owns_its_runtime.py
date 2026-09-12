"""A temporary served product cannot borrow a live provider, corpus or store."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from nm.bootstrap import composition
from nm.ports.evidence import Coverage
from nm.ports.model import ConfigurationError, Prompt, Tier
from tools.served import KEY, served

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def spec_root(tmp_path):
    root = tmp_path / "spec-root"
    for relative in ("spec/manifest.yaml", "docs/blueprint/processors.yaml"):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return root


@pytest.fixture(autouse=True)
def restore_served_application(monkeypatch):
    # create_app currently owns one process-global ASGI application. This
    # suite is serial and makes no claim of concurrent ASGI-box isolation.
    from nm.edge import api
    monkeypatch.setattr(api, "_application", api._application)


def _environment(root):
    return {
        "NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1",
        "NM_EMBED_MODEL": "text-embedding-3-large", "NM_MATTER_KEY": KEY,
        "NM_MATTER_STORE": str(root / "store"),
        "NM_CORPUS_DIR": str(root / "corpus"),
        "NM_AUTHORITY_INDEX": str(root / "authority.db"),
        "NM_IDENTITY_INDEX": str(root / "identity.db"),
    }


def _poison(monkeypatch, outside):
    # Synthetic sentinels, never a real credential or corpus. Deliberately
    # invalid provider/pins ensure accidental ambient reads are loud.
    poisoned = {
        "NM_MODEL_PROVIDER": "unapproved-poison-provider",
        "NM_MODEL_ROUTINE": "floating-poison-model",
        "NM_MODEL_HARD": "floating-poison-hard",
        "NM_MODEL_JUDGE": "floating-poison-judge",
        "NM_EMBED_MODEL": "floating-poison-embed",
        "NM_MODEL_API_KEY": "synthetic-shared-poison-key",
        "NM_MATTER_KEY": "synthetic-shared-poison-key",
        "NM_MATTER_STORE": str(outside / "store"),
        "NM_CORPUS_DIR": str(outside / "corpus"),
        "NM_AUTHORITY_INDEX": str(outside / "authority.db"),
        "NM_IDENTITY_INDEX": str(outside / "identity.db"),
    }
    for name, value in poisoned.items():
        monkeypatch.setenv(name, value)
    return dict(os.environ)


def _dotenv_forbidden(*args, **kwargs):
    raise AssertionError("explicit composition must not read or apply .env")


def test_actual_served_runtime_ignores_poison_and_keeps_writes_temporary(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    outside = tmp_path / "forbidden-live-location"
    before = _poison(monkeypatch, outside)
    monkeypatch.setattr(composition, "load_dotenv", _dotenv_forbidden)
    writes = []
    original_open, original_os_open = Path.open, os.open

    def guarded_open(path, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            resolved = path.resolve()
            assert resolved.is_relative_to(runtime.resolve()), f"non-temporary write: {resolved}"
            writes.append(resolved)
        return original_open(path, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            resolved = Path(path).resolve()
            assert resolved.is_relative_to(runtime.resolve()), (
                f"non-temporary descriptor: {resolved}")
            writes.append(resolved)
        return original_os_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(os, "open", guarded_os_open)
    box = served(runtime)
    actor = box.enrol()
    shell = box.application.uploads.create_intake(actor, {
        "request_key": "isolation-witness", "title": "Synthetic isolated file"})
    assert box.application.store.load(shell["matter_id"]).title == "Synthetic isolated file"
    assert box.application.model.provider == "scripted"
    result = box.application.model.complete(
        Prompt(user="Synthetic offline request"), tier=Tier.ROUTINE)
    assert result.text == "Issue the statutory notice and diarise the window."
    assert box.application.search.inner._path == runtime / "authority.db"
    search = box.application.search.search("Synthetic private query")
    assert search.coverage is Coverage.NOT_ASSESSED
    assert not (runtime / "authority.db").exists()
    assert (runtime / "audit/egress.log").is_file()
    audit = (runtime / "audit/egress.log").read_text(encoding="utf-8")
    assert "Synthetic private query" not in audit
    assert writes and all(path.is_relative_to(runtime.resolve()) for path in writes)
    assert not outside.exists()
    assert dict(os.environ) == before


def test_explicit_configuration_is_copied_once_and_not_writable(spec_root, monkeypatch):
    settings = _environment(spec_root)
    monkeypatch.setattr(composition, "load_dotenv", _dotenv_forbidden)
    app = composition.Application(
        root=spec_root, environment=settings, audit_root=spec_root / "audit")
    settings["NM_AUTHORITY_INDEX"] = str(spec_root / "replacement.db")
    settings["NM_MODEL_PROVIDER"] = "unapproved-replacement"
    assert app.environment["NM_MODEL_PROVIDER"] == "scripted"
    assert app.search.inner._path == spec_root / "authority.db"
    assert app.config.for_tier(Tier.ROUTINE).provider == "scripted"
    with pytest.raises(TypeError):
        app.environment["NM_MATTER_STORE"] = "replacement"


def test_an_incomplete_explicit_mapping_never_borrows_ambient_tiers(tmp_path, monkeypatch):
    for name, value in _environment(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(composition, "load_dotenv", _dotenv_forbidden)
    with pytest.raises(ConfigurationError, match="NM_MODEL_ROUTINE is not set"):
        composition.Application(environment={"NM_MODEL_PROVIDER": "scripted"})


def test_default_composition_still_loads_production_configuration(spec_root, monkeypatch):
    settings = _environment(spec_root)
    for name in list(os.environ):
        if name.startswith("NM_"):
            monkeypatch.delenv(name)
    loaded = []

    def controlled_dotenv(path):
        loaded.append(path)
        for name, value in settings.items():
            monkeypatch.setenv(name, value)

    monkeypatch.setattr(composition, "load_dotenv", controlled_dotenv)
    app = composition.Application(root=spec_root)
    assert loaded == [composition.ROOT / ".env"]
    assert app.environment["NM_MODEL_PROVIDER"] == "scripted"
    assert app.audit_root == spec_root / ".nm"
    assert (spec_root / ".nm/egress.log").is_file()


def test_explicit_configuration_keeps_the_shared_seal_refusal(spec_root, monkeypatch):
    settings = _environment(spec_root)
    settings["SYNTHETIC_PROVIDER_TOKEN"] = KEY
    monkeypatch.setattr(composition, "load_dotenv", _dotenv_forbidden)
    with pytest.raises(composition.SharedSealRefused, match="SYNTHETIC_PROVIDER_TOKEN"):
        composition.Application(root=spec_root, environment=settings)


def test_bypassing_the_explicit_snapshot_triggers_the_poison_control(tmp_path, monkeypatch):
    _poison(monkeypatch, tmp_path / "forbidden")
    monkeypatch.setattr(composition, "load_dotenv", _dotenv_forbidden)
    original_load = composition.load
    called = []

    def wrongly_read_process_environment(env=None):
        assert env is not None and env["NM_MODEL_PROVIDER"] == "scripted"
        called.append(True)
        return original_load()  # planted regression at the actual consumer

    monkeypatch.setattr(composition, "load", wrongly_read_process_environment)
    with pytest.raises(ConfigurationError):
        served(tmp_path / "runtime")
    assert called == [True]


def test_an_explicit_empty_environment_is_not_the_default_environment(monkeypatch):
    monkeypatch.setattr(composition, "load_dotenv", _dotenv_forbidden)
    with pytest.raises(ConfigurationError, match="NM_MODEL_PROVIDER is not set"):
        composition.Application(environment={})
