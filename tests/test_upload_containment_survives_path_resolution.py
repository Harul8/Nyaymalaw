"""Equivalent resolved paths are not escapes; actual link targets still are."""
from __future__ import annotations

import errno
import os
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from nm.adapters.store import uploads
from nm.adapters.store.file_store import FileMatterStore
from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("root,candidate,inside", [
    (r"C:\store\uploads", r"C:\store\uploads\matter\chunk.nm", True),
    (r"C:\store\uploads", r"\\?\C:\store\uploads\matter\chunk.nm", True),
    (r"\\?\C:\store\uploads", r"C:\store\uploads\matter\chunk.nm", True),
    (r"\\?\C:\store\uploads", r"\\?\C:\store\uploads\matter\chunk.nm", True),
    (r"C:\Store\Uploads", r"\\?\c:\store\uploads\matter\chunk.nm", True),
    (r"\\host\share\uploads", r"\\host\share\uploads\matter\chunk.nm", True),
    (r"\\host\share\uploads", r"\\?\UNC\host\share\uploads\matter\chunk.nm", True),
    (r"\\?\UNC\host\share\uploads", r"\\host\share\uploads\matter\chunk.nm", True),
    (r"\\?\UNC\host\share\uploads",
     r"\\?\UNC\host\share\uploads\matter\chunk.nm", True),
    (r"C:\store\uploads", r"\\?\C:\store\uploads-other\chunk.nm", False),
    (r"C:\store\uploads", r"\\?\D:\store\uploads\chunk.nm", False),
    (r"\\host\share\uploads", r"\\?\UNC\other\share\uploads\chunk.nm", False),
    (r"\\host\share\uploads", r"\\?\UNC\host\other\uploads\chunk.nm", False),
    (r"C:\store\uploads", r"\\?\UNC\host\share\uploads\chunk.nm", False),
    (r"\\?\C:\store\uploads.", r"C:\store\uploads\chunk.nm", False),
    (r"C:\store\uploads", r"\\?\C:\store\uploads.\chunk.nm", False),
    (r"C:\store\uploads", r"\\?\C:\store\uploads \chunk.nm", False),
    (r"C:\store\uploads", r"C:store\uploads\chunk.nm", False),
])
def test_windows_identity_keeps_equivalence_and_real_boundaries(root, candidate, inside):
    assert uploads._resolved_is_within(
        PureWindowsPath(candidate), PureWindowsPath(root)) is inside


def test_posix_paths_keep_their_own_semantics_and_cannot_mix_flavours():
    root = PurePosixPath("/store/uploads")
    assert uploads._resolved_is_within(root / "matter/chunk.nm", root)
    assert not uploads._resolved_is_within(PurePosixPath("/store/uploads-other/x"), root)
    assert not uploads._resolved_is_within(PurePosixPath("/Store/uploads/x"), root)
    assert not uploads._resolved_is_within(PurePosixPath("relative/x"), root)
    assert not uploads._resolved_is_within(PureWindowsPath(r"C:\store\uploads\x"), root)


def test_device_namespace_is_not_treated_as_a_filesystem_upload_root():
    with pytest.raises(ValueError, match="device namespace"):
        uploads._resolved_is_within(
            PureWindowsPath(r"\\.\C:\store\uploads\x"), PureWindowsPath(r"C:\store\uploads"))


def test_actual_directory_link_cannot_redirect_original_reads_or_writes(tmp_path):
    objects = FileMatterStore(tmp_path / "store", key=KEY).upload_storage()
    objects.put("m_inside", "chunk_inside", b"synthetic original")
    assert objects.read("m_inside", "chunk_inside") == b"synthetic original"
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "chunk_held.nm"
    sentinel.write_bytes(b"outside sentinel must remain untouched")
    link = objects._root / "m_escape"
    if os.name == "nt":
        from _winapi import CreateJunction

        CreateJunction(str(outside), str(link))
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        assert link.resolve(strict=True) == outside.resolve(strict=True)
        assert link.is_dir(), "the negative control must plant a real filesystem redirect"
        with pytest.raises(ValueError, match="outside its storage root"):
            objects.put("m_escape", "chunk_new", b"must not escape")
        with pytest.raises(ValueError, match="outside its storage root"):
            objects.read("m_escape", "chunk_held")
        assert not (outside / "chunk_new.nm").exists()
        assert sentinel.read_bytes() == b"outside sentinel must remain untouched"
    finally:
        # Remove only the temporary link itself, never its target directory.
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


def test_parent_creation_during_resolution_preserves_one_storage_identity(tmp_path, monkeypatch):
    objects = FileMatterStore(tmp_path / "store", key=KEY).upload_storage()
    candidate = objects._root / "m_race" / "chunk_race.nm"
    assert not candidate.parent.exists()
    errors = []
    compared = []
    containment = uploads._resolved_is_within

    def record_comparison(path, root):
        compared.append((path, root))
        return containment(path, root)

    monkeypatch.setattr(uploads, "_resolved_is_within", record_comparison)
    if os.name == "nt":
        import ntpath

        original = ntpath._getfinalpathname

        def concurrent_parent(path):
            try:
                return original(path)
            except OSError as exc:
                if os.fspath(path) == str(candidate):
                    errors.append(exc.winerror)
                    if len(errors) == 1:
                        assert exc.winerror == 3, "first probe must find a missing parent"
                        candidate.parent.mkdir(parents=True)
                raise

        monkeypatch.setattr(ntpath, "_getfinalpathname", concurrent_parent)
    else:
        original = os.lstat

        def concurrent_parent(path, *args, **kwargs):
            try:
                return original(path, *args, **kwargs)
            except OSError as exc:
                if os.fspath(path) == str(candidate.parent) and not errors:
                    assert exc.errno == errno.ENOENT
                    errors.append(exc.errno)
                    candidate.parent.mkdir(parents=True)
                raise

        monkeypatch.setattr(os, "lstat", concurrent_parent)
    objects.put("m_race", "chunk_race", b"real sealed bytes")
    assert errors and compared, "the real resolution boundary must have been intercepted"
    resolved, root = compared[0]
    if os.name == "nt":
        assert errors[0] == 3 and 2 in errors[1:]
        assert str(resolved).startswith("\\\\?\\")
        assert not str(root).startswith("\\\\?\\")
        assert not resolved.is_relative_to(root), "the old lexical check must reject this probe"
    else:
        assert errors == [errno.ENOENT]
        assert resolved.is_relative_to(root)
    assert containment(resolved, root)
    assert objects.read("m_race", "chunk_race") == b"real sealed bytes"
