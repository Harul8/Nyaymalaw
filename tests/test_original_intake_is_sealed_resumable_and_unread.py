"""P16 served original receipt. Scanning/transcription remain explicitly unproved."""

from __future__ import annotations


import pytest


pytestmark = pytest.mark.class_a


def test_original_objects_cannot_be_overwritten_or_decrypted_under_another_matter(tmp_path):
    from nm.shared.store_envelope import CrossMatterAccess
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_turn_contract import KEY

    store = FileMatterStore(tmp_path, key=KEY)
    # Custody belongs to an actual initial matter, never to an upload writer.
    from nm.work_the_file.matter_contracts import Matter

    store.commit(Matter(id="m_one", advocate_id="owner", title="Upload custody", version=1),
                 expected_version=0)
    objects = store.upload_storage()
    objects.put("m_one", "chunk_one", b"PRIVILEGED-SYNTHETIC")
    assert objects.read("m_one", "chunk_one") == b"PRIVILEGED-SYNTHETIC"
    with pytest.raises(FileExistsError):
        objects.put("m_one", "chunk_one", b"replacement")
    assert objects.read("m_one", "chunk_one") == b"PRIVILEGED-SYNTHETIC"
    sealed = objects._path("m_one", "chunk_one").read_bytes()
    with pytest.raises(CrossMatterAccess):
        objects._sealer.open("m_two", sealed)
    for invalid in ("../escape", "a/b", "a\\b", "C:", "."):
        with pytest.raises(ValueError):
            objects.put(invalid, "chunk_one", b"x")


