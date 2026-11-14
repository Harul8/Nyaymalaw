"""A paper's original is removed, every part of it, by the upload store's one delete (plan AN.53, D244's first piece).

D241: a conversation is erased with everything that belongs to it, its papers as sent among them. D244: a paper is kept in the
advocate's own document space - its original as received, in sealed parts named `<paper>-<n>` - under the space's one key, which
all the advocate's papers share. The upload store had no delete at all. Now it removes every part of one paper by the paper's own
name, and says which parts could not be removed; the space's key is kept, and so is every other paper, in this space or another.
Nothing asks for it yet (the text records' delete, the desk's erasure and their callers are the next pieces).

Offline: a store in a temporary folder; no model call; the words are invented.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from nm.shared.store_file_store import FileMatterStore

pytestmark = pytest.mark.class_a

KEY = "paper-erasure-control-" + "k" * 32
SPACE, OTHER_SPACE = "docs_" + "a" * 40, "docs_" + "b" * 40
PAPER, OTHER_PAPER = "doc_" + "1" * 24, "doc_" + "2" * 24


def _uploads(root):
    store = FileMatterStore(root, key=KEY)
    for space in (SPACE, OTHER_SPACE):
        store.prepare_custody(space)
    uploads = store.upload_storage()
    for space in (SPACE, OTHER_SPACE):
        for paper in (PAPER, OTHER_PAPER):
            for part in range(3):
                uploads.put(space, f"{paper}-{part}", f"{space} {paper} part {part}".encode())
    return uploads


def _parts(root, space):
    return sorted(path.stem for path in (root / "uploads" / space).glob("*.nm"))


def test_every_part_of_the_paper_is_removed_and_nothing_else(tmp_path):
    uploads = _uploads(tmp_path)
    assert uploads.erase(SPACE, PAPER) == ()
    assert _parts(tmp_path, SPACE) == [f"{OTHER_PAPER}-{part}" for part in range(3)], "another paper in the space is kept"
    assert _parts(tmp_path, OTHER_SPACE) == sorted(f"{paper}-{part}" for paper in (PAPER, OTHER_PAPER) for part in range(3)), (
        "the same name in another advocate's space is not theirs to remove")
    assert uploads.read(SPACE, f"{OTHER_PAPER}-1") == f"{SPACE} {OTHER_PAPER} part 1".encode(), "the space's key is kept"
    with pytest.raises(FileNotFoundError):
        uploads.read(SPACE, f"{PAPER}-0")


def test_a_paper_whose_name_begins_anothers_is_not_removed_with_it(tmp_path):
    uploads = _uploads(tmp_path)
    longer = PAPER + "9"
    uploads.put(SPACE, f"{longer}-0", b"a paper of its own")
    uploads.erase(SPACE, PAPER)
    assert uploads.read(SPACE, f"{longer}-0") == b"a paper of its own"


def test_what_is_not_there_is_not_an_error(tmp_path):
    uploads = _uploads(tmp_path)
    uploads.erase(SPACE, PAPER)
    assert uploads.erase(SPACE, PAPER) == (), "a second erasure finds nothing more"
    assert uploads.erase("docs_" + "c" * 40, PAPER) == (), "nor does a space with no papers"


def test_a_part_that_cannot_be_removed_is_named(tmp_path, monkeypatch):
    uploads = _uploads(tmp_path)
    unlinking = Path.unlink

    def refuse_one(self, missing_ok=False):
        if self.stem == f"{PAPER}-1":
            raise PermissionError("the folder refuses")
        return unlinking(self, missing_ok=missing_ok)
    monkeypatch.setattr(Path, "unlink", refuse_one)
    assert uploads.erase(SPACE, PAPER) == (f"{PAPER}-1",)
    monkeypatch.setattr(Path, "unlink", unlinking)
    assert _parts(tmp_path, SPACE) == sorted([f"{PAPER}-1"] + [f"{OTHER_PAPER}-{part}" for part in range(3)])
    assert uploads.erase(SPACE, PAPER) == (), "and is removed when asked again"


@pytest.mark.parametrize("name", ["", f"{PAPER}-0", "doc_*", "../uploads", "doc_1/2", "doc 1", "x" * 100])
def test_only_a_papers_own_name_is_taken(tmp_path, name):
    uploads = _uploads(tmp_path)
    with pytest.raises(ValueError):
        uploads.erase(SPACE, name)
    assert len(_parts(tmp_path, SPACE)) == 6, "nothing was removed"


@pytest.mark.parametrize("space", ["../uploads", "docs_a/b", "", "."])
def test_only_a_space_of_the_store_is_taken(tmp_path, space):
    uploads = _uploads(tmp_path)
    with pytest.raises(ValueError):
        uploads.erase(space, PAPER)


def test_the_upload_port_declares_the_delete_so_the_policed_wrapper_gates_it():
    from nm.open_matter.upload_port import UploadPort
    from nm.shared.policed_port_adapter import port_methods
    assert "erase" in port_methods(UploadPort)


def test_the_delete_goes_through_the_policed_wrapper_and_a_refused_destination_removes_nothing(tmp_path):
    from nm.open_matter.upload_port import UploadPort
    from nm.shared.egress_contracts import DataClass, EgressRefused, Gatekeeper, Policy, Processor, Sink
    from nm.shared.policed_port_adapter import PolicedPort
    approved = Policy(processors=(Processor(processor_id="local-disk", region="in", purposes=(Sink.STORAGE,),
                                            data_classes=(DataClass.CLIENT_MATTER,), approval_id="IN-PROCESS-NO-EGRESS"),))
    uploads = _uploads(tmp_path)
    policed = PolicedPort(inner=uploads, gate=Gatekeeper(policy=approved), port=UploadPort, sink=Sink.STORAGE,
                          processor_id="local-disk")
    policed.gate.policy = Policy()
    with pytest.raises(EgressRefused):
        policed.erase(SPACE, PAPER)
    assert len(_parts(tmp_path, SPACE)) == 6, "refused before anything was removed"
    policed.gate.policy = approved
    assert policed.erase(SPACE, PAPER) == ()
    assert _parts(tmp_path, SPACE) == [f"{OTHER_PAPER}-{part}" for part in range(3)]
