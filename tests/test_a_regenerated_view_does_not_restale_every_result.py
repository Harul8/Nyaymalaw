"""REGENERATING A GENERATED VIEW MUST NOT RESTALE EVERY RESULT.

THE DEFECT, MEASURED DURING THE P29 TO P36 CLOSE-OUT
------------------------------------------------------
`docs/Nyaymalaw_PRD.docx` is a generated view of `assurance/specification/prd/`. The close-out
step says to regenerate it. Doing so, from source that had not changed by a
byte, moved the tree identity -- and every promoted Class-A and browser result
went stale, including runs with nothing to do with the PRD.

`_docx_semantic` normalised `dcterms:created` and `dcterms:modified` in
`docProps/core.xml`. It did not normalise `w:date`, which OOXML writes into
`word/comments.xml` for each of the PRD's own review comments, stamped at
generation time.

    THE SHAPE, WITHOUT THE MEMBER THAT EXPOSED IT: a normalisation applied to
    the place a volatile value was first noticed rather than to every place
    the format writes it. CLAUDE.md's sweep rule, in the identity function
    that decides whether any evidence in this repository is admissible.

WHY IT MATTERS MORE THAN IT LOOKS
-----------------------------------
`assurance/control_plane/evidence.py` already records the reasoning, two blocks above the bug,
about the feature registry: *fold in the verdict and the fingerprint moves
every time evidence is recorded -- which restales the evidence that just moved
it. That is not a strict check, it is a check that can never be satisfied.*
This was the same sentence about a different input, and the practical effect
was worse: it made a documented close-out step and a passing gate mutually
exclusive.
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import zipfile

import pytest

from assurance.control_plane.evidence import _docx_semantic

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRD = ROOT / "docs" / "Nyaymalaw_PRD.docx"


def _identity(root: pathlib.Path) -> str:
    return hashlib.sha256(_docx_semantic(root)).hexdigest()


def _rewritten(source: pathlib.Path, target: pathlib.Path,
               edit) -> pathlib.Path:
    """A copy of the PRD with one member rewritten by `edit`."""
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w") as new:
        for info in old.infolist():
            new.writestr(info, edit(info.filename, old.read(info)))
    return target


def _fixture_root(tmp_path: pathlib.Path, docx: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "tree"
    (root / "docs").mkdir(parents=True)
    shutil.copy(docx, root / "docs" / "Nyaymalaw_PRD.docx")
    return root


def test_the_package_time_does_not_move_the_identity(tmp_path):
    """THE DEFECT, as a test. Only the generation timestamps differ, and the
    document says exactly the same thing."""
    def restamp(name: str, body: bytes) -> bytes:
        return body.replace(b"2026-09-13T08:15:47", b"2031-01-01T00:00:00")

    same = _fixture_root(tmp_path, PRD)
    later = _fixture_root(
        tmp_path / "later",
        _rewritten(PRD, tmp_path / "later.docx", restamp))
    assert _identity(same) == _identity(later)


def test_a_changed_sentence_does_move_the_identity(tmp_path):
    """THE POSITIVE CONTROL, and the one that matters most here.

    A normalisation that swallowed real content would make the identity unable
    to notice a changed requirement -- which is worse than the defect it was
    written to fix, and invisible in exactly the same way.
    """
    def rewrite(name: str, body: bytes) -> bytes:
        if name == "word/document.xml":
            return body.replace(b"must", b"may", 1)
        return body

    same = _fixture_root(tmp_path, PRD)
    edited = _fixture_root(
        tmp_path / "edited",
        _rewritten(PRD, tmp_path / "edited.docx", rewrite))
    assert _identity(same) != _identity(edited)


def test_a_changed_comment_body_still_moves_the_identity(tmp_path):
    """The normalisation is on the DATE ATTRIBUTE and not on the comment. What
    a reviewer wrote is content; when the package wrote it down is not."""
    def rewrite(name: str, body: bytes) -> bytes:
        if name == "word/comments.xml":
            return body.replace(b"Revision 1.1", b"Revision 9.9", 1)
        return body

    same = _fixture_root(tmp_path, PRD)
    edited = _fixture_root(
        tmp_path / "edited",
        _rewritten(PRD, tmp_path / "edited.docx", rewrite))
    assert _identity(same) != _identity(edited)


def test_an_absent_prd_is_not_silently_the_same_as_an_empty_one(tmp_path):
    """Section 9. A missing generated view must not hash to whatever a broken
    one does."""
    missing = tmp_path / "empty"
    (missing / "docs").mkdir(parents=True)
    broken = _fixture_root(tmp_path / "broken", PRD)
    (broken / "docs" / "Nyaymalaw_PRD.docx").write_bytes(b"not a docx at all")
    assert _identity(missing) != _identity(broken)
    assert _identity(broken) != _identity(_fixture_root(tmp_path / "ok", PRD))
