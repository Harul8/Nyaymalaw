"""Every record of a paper's text is removed by the document store's one delete (plan AN.53, D244's second piece).

D244: a paper's text is kept in the advocate's document space as immutable sealed records named '<paper>-<its digest>' - the first
reading, and a new record each time pages are read again (scanned pages read by the AI, figures looked at again). The document
store could forget one exact record, never all of one paper's. Now it removes every record of one paper by the paper's own name,
as the upload store removes the paper's original parts (53h3c1), and says which could not be removed; the space's key is kept,
and so is every other paper's text. Nothing asks for it yet.

Offline: a store in a temporary folder; no model call; the words are invented.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from nm.shared.store_file_store import FileMatterStore

pytestmark = pytest.mark.class_a

KEY = "paper-text-erasure-control-" + "k" * 32
SPACE, OTHER_SPACE = "docs_" + "a" * 40, "docs_" + "b" * 40
PAPER, OTHER_PAPER = "doc_" + "1" * 24, "doc_" + "2" * 24


def _record(space, paper, reading):
    body = f'{{"space": "{space}", "paper": "{paper}", "reading": {reading}}}'.encode()
    return f"{paper}-{hashlib.sha256(body).hexdigest()}", body


def _texts(root):
    store = FileMatterStore(root, key=KEY)
    for space in (SPACE, OTHER_SPACE):
        store.prepare_custody(space)
    texts = store.document_storage()
    for space in (SPACE, OTHER_SPACE):
        for paper in (PAPER, OTHER_PAPER):
            for reading in range(3):  # the first reading, and two made since
                texts.put(space, *_record(space, paper, reading))
    return texts


def _records(root, space):
    return sorted(path.stem.split("-")[0] for path in (root / "document-text" / space).glob("*.nm"))


def test_every_record_of_the_papers_text_is_removed_and_nothing_else(tmp_path):
    texts = _texts(tmp_path)
    assert texts.erase(SPACE, PAPER) == ()
    assert _records(tmp_path, SPACE) == [OTHER_PAPER] * 3, "another paper's text in the space is kept"
    assert _records(tmp_path, OTHER_SPACE) == [PAPER] * 3 + [OTHER_PAPER] * 3, "and another advocate's space is not touched"
    name, body = _record(SPACE, OTHER_PAPER, 1)
    assert texts.read(SPACE, name, name.split("-")[1]) == body, "the space's key is kept"
    name, _ = _record(SPACE, PAPER, 0)
    with pytest.raises(FileNotFoundError):
        texts.read(SPACE, name, name.split("-")[1])


def test_a_second_erasure_finds_nothing_more_and_a_record_that_cannot_be_removed_is_named(tmp_path, monkeypatch):
    texts = _texts(tmp_path)
    stuck, _ = _record(SPACE, PAPER, 2)
    unlinking = Path.unlink

    def refuse_one(self, missing_ok=False):
        if self.stem == stuck:
            raise PermissionError("the folder refuses")
        return unlinking(self, missing_ok=missing_ok)
    monkeypatch.setattr(Path, "unlink", refuse_one)
    assert texts.erase(SPACE, PAPER) == (stuck,)
    monkeypatch.setattr(Path, "unlink", unlinking)
    assert texts.erase(SPACE, PAPER) == () and _records(tmp_path, SPACE) == [OTHER_PAPER] * 3


@pytest.mark.parametrize("name", ["", f"{PAPER}-0", "doc_*", "../document-text", "doc_1/2", "x" * 100])
def test_only_a_papers_own_name_is_taken(tmp_path, name):
    texts = _texts(tmp_path)
    with pytest.raises(ValueError):
        texts.erase(SPACE, name)
    assert len(_records(tmp_path, SPACE)) == 6, "nothing was removed"


def test_the_derivative_port_declares_the_delete_so_the_policed_wrapper_gates_it():
    from nm.open_matter.matter_documents_port import DocumentDerivativePort
    from nm.shared.policed_port_adapter import port_methods
    assert "erase" in port_methods(DocumentDerivativePort)


def test_the_delete_goes_through_the_policed_wrapper_and_a_refused_destination_removes_nothing(tmp_path):
    from nm.open_matter.matter_documents_port import DocumentDerivativePort
    from nm.shared.egress_contracts import DataClass, EgressRefused, Gatekeeper, Policy, Processor, Sink
    from nm.shared.policed_port_adapter import PolicedPort
    approved = Policy(processors=(Processor(processor_id="local-disk", region="in", purposes=(Sink.STORAGE,),
                                            data_classes=(DataClass.CLIENT_MATTER,), approval_id="IN-PROCESS-NO-EGRESS"),))
    texts = _texts(tmp_path)
    policed = PolicedPort(inner=texts, gate=Gatekeeper(policy=approved), port=DocumentDerivativePort, sink=Sink.STORAGE,
                          processor_id="local-disk")
    policed.gate.policy = Policy()
    with pytest.raises(EgressRefused):
        policed.erase(SPACE, PAPER)
    assert len(_records(tmp_path, SPACE)) == 6
    policed.gate.policy = approved
    assert policed.erase(SPACE, PAPER) == () and _records(tmp_path, SPACE) == [OTHER_PAPER] * 3
