"""Test helpers live in support modules, and the borrowing of one test file from another does not grow (plan AN.57, piece 57e;
D266; the second review of 17 Nov 2026).

A test file that imports from another test file couples them: the borrower breaks when the lender's tests are changed, and the
lint flags every test that names a fixture it imported. The review found half the test modules doing it. D266 moves the helpers
into support modules one borrowed module a piece, beginning with the most borrowed: tests/test_core_served.py, whose served
application about ninety files imported. Its helpers are now in tests/served_application.py and its fixture is declared once
in tests/conftest.py. These sweeps hold the line - every test file, with planted files to show each sweep counts what it
should - so a moved module is not borrowed again and the number of borrowers only falls. What a file borrows is read from its
imports as Python reads them, by the one reader the journeys job uses (development_environment/developer_tooling).
"""
from __future__ import annotations

from pathlib import Path

from development_environment.developer_tooling.journey_files import borrowed

TESTS = Path(__file__).resolve().parent
#: Test files whose helpers have moved to a support module: nothing may borrow from them again.
MOVED = ("test_core_served",)
#: Test files that import another test file, at most. Lower it when a piece moves helpers; never raise it.
MOST_BORROWERS = 246


def borrowers(folder: Path) -> dict[str, set[str]]:
    """Each test file of the folder that imports another, with the test files it imports."""
    files = sorted(folder.glob("test_*.py"))
    names = {path.stem for path in files}
    found = {}
    for path in files:
        lent = (borrowed(path.read_text(encoding="utf8", errors="replace")) & names) - {path.stem}
        if lent:
            found[path.stem] = lent
    return found


def test_the_sweep_counts_a_file_that_borrows_and_not_one_that_uses_a_support_module(tmp_path):
    (tmp_path / "test_core_served.py").write_text("OWNER = 'x'\n", encoding="utf8")
    (tmp_path / "test_lends.py").write_text("def helper():\n    return 1\n", encoding="utf8")
    (tmp_path / "test_borrows.py").write_text("from tests.test_lends import helper\n", encoding="utf8")
    (tmp_path / "test_borrows_the_moved.py").write_text(
        "def test_late():\n    from tests.test_core_served import OWNER\n", encoding="utf8")
    (tmp_path / "test_supported.py").write_text("from tests.served_application import OWNER\n", encoding="utf8")
    (tmp_path / "served_application.py").write_text("OWNER = 'x'\n", encoding="utf8")
    assert borrowers(tmp_path) == {"test_borrows": {"test_lends"}, "test_borrows_the_moved": {"test_core_served"}}


def test_no_test_file_borrows_from_one_whose_helpers_have_moved():
    found = {name: sorted(lent & set(MOVED)) for name, lent in borrowers(TESTS).items() if lent & set(MOVED)}
    assert not found, f"import these from the support module instead: {found}"


def test_the_number_of_test_files_that_borrow_from_another_does_not_grow():
    count = len(borrowers(TESTS))
    assert count <= MOST_BORROWERS, (
        f"{count} test files import another test file, more than {MOST_BORROWERS}: put the helper in a support module")
