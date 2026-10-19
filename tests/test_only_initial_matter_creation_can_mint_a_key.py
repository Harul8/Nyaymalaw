"""Lost custody never becomes permission to mint a replacement matter key."""
from __future__ import annotations

import ast
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from nm.shared.store_documents import SealedDocumentStore
from nm.shared.store_envelope import KeyUnavailable
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_uploads import SealedUploadStore
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a


def _created(root):
    store = FileMatterStore(root, key="controlled-custody-key-" + "k" * 24)
    saved = store.commit(Matter(id="m_custody", advocate_id="owner@example.test",
                                title="Custody control", version=1), expected_version=0)
    return store, saved, root / "keys" / f"{saved.id}.key"


def test_existing_writers_keep_one_actual_key_and_readable_ciphertext(tmp_path):
    store, saved, key = _created(tmp_path)
    original = key.read_bytes()
    updated = store.commit(replace(saved, title="Updated"), expected_version=saved.version)
    store.record_turn({"turn_id": "t_custody", "matter_id": saved.id,
                       "advocate_said": "Privileged words"})
    uploads = SealedUploadStore(tmp_path, store._sealer)
    documents = SealedDocumentStore(tmp_path, store._sealer)
    uploads.put(saved.id, "u_custody", b"original")
    documents.put(saved.id, "d_custody", b"derivative")
    assert key.read_bytes() == original
    assert store.load(saved.id) == updated
    assert uploads.read(saved.id, "u_custody") == b"original"
    assert documents.read(saved.id, "d_custody",
                          hashlib.sha256(b"derivative").hexdigest()) == b"derivative"


@pytest.mark.parametrize("writer", ["transcript", "upload", "document"])
def test_derivative_writers_do_not_recreate_erased_custody(tmp_path, writer):
    store, saved, key = _created(tmp_path)
    existing = (tmp_path / "matters" / f"{saved.id}.nm").read_bytes()
    key.unlink()  # This test's own controlled temporary key, not product data.
    with pytest.raises(KeyUnavailable):
        if writer == "transcript":
            store.record_turn({"turn_id": "t_lost", "matter_id": saved.id})
        elif writer == "upload":
            SealedUploadStore(tmp_path, store._sealer).put(saved.id, "u_lost", b"original")
        else:
            SealedDocumentStore(tmp_path, store._sealer).put(saved.id, "d_lost", b"derivative")
    assert not key.exists()
    assert (tmp_path / "matters" / f"{saved.id}.nm").read_bytes() == existing
    assert len(list(tmp_path.rglob("*.nm"))) == 1


def test_key_lost_between_load_and_commit_refuses_without_replacing_matter(tmp_path, monkeypatch):
    store, saved, key = _created(tmp_path)
    existing = (tmp_path / "matters" / f"{saved.id}.nm").read_bytes()
    real_seal = store._seal

    def lose_key(matter_id, data, *, create_key=False):
        assert create_key is False
        key.unlink()
        return real_seal(matter_id, data, create_key=create_key)

    monkeypatch.setattr(store, "_seal", lose_key)
    with pytest.raises(KeyUnavailable):
        store.commit(replace(saved, title="Must not land"), expected_version=saved.version)
    assert not key.exists()
    assert (tmp_path / "matters" / f"{saved.id}.nm").read_bytes() == existing
    assert not list((tmp_path / "matters").glob("*.tmp"))


class _StatementRecorder:
    """A SQL boundary control, not a PostgreSQL durability substitute."""
    rowcount = 1

    def __init__(self, *, rowcount=1):
        self.statements = []
        self.rowcount = rowcount

    def execute(self, statement, values):
        self.statements.append((statement, values))


def test_every_product_sealing_writer_declares_its_creation_authority():
    """Enumerate the entire backend so a fifth sibling cannot hide."""
    backend = Path(__file__).resolve().parents[1] / "nm"
    calls = {}
    for path in backend.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "seal"):
                continue
            relative = path.relative_to(backend).as_posix()
            declared = [part.value for part in node.keywords if part.arg == "create_key"]
            assert len(declared) == 1, (relative, node.lineno, "implicit key creation")
            calls.setdefault(relative, []).append(ast.unparse(declared[0]))
    assert calls == {
        "shared/store_file_store.py": ["create_key"],
        "shared/store_uploads.py": ["False"],
        "shared/store_documents.py": ["False"],
    }, "a changed sealing population needs an explicit custody review"
